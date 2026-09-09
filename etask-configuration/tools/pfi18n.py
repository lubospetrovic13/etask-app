#!/usr/bin/env python3
"""
pfi18n - dvojjazycnost Petriflow sieti: skontroluj ju, alebo ju zaloz.

PRECO TO EXISTUJE

Petriflow prelozit vie a robi to cely server: `Task.java:81` vezme `Accept-Language`
z poziadavky a kazdy titulok, popis, placeholder aj hodnotu moznosti vrati uz
prelozene. Mechanizmus je dvojdielny a to je presne to, co sa neda uhadnut:

  1. Kazdy prelozitelny element (`<title>`, `<label>`, `<placeholder>`, `<desc>`,
     `<option>`, titulok udalosti, `<caseName>`) musi mat atribut `name` - to je
     KLUC prekladu.
  2. Pre kazdy kluc musi existovat riadok v bloku `<i18n locale="...">`.

Chybajuca polovica sa NEPREJAVI NIJAKO. `name` bez bloku `i18n` sa naimportuje
a zobrazi sa povodna hodnota; element bez `name` sa naimportuje a zobrazi sa
povodna hodnota. V oboch pripadoch appka vyzera funkcne a je jednojazycna.
Import nic nepovie, `pflint` nic nepovie, log nic nepovie.

A jedna pasca navyse, ktora stoji cely blok: kluc locale sa uklada VERBATIM
(`Importer.addTranslation`), ale vyhladava sa cez `Locale.getLanguage()`, teda
dvojpismenove. `<i18n locale="en-US">` je preto mrtvy kod - naimportuje sa
a nikdy sa nepouzije. Namerane, ENGINE_ISSUES.md E15.

CO ROBI

  python3 tools/pfi18n.py processes/                    # kontrola
  python3 tools/pfi18n.py --init processes/mojaapp.xml  # doplni name= a blok i18n

`--init` je mechanicka praca, nie preklad: doplni chybajuce atributy `name`
odvodene z id elementu a zalozi blok `<i18n locale="en">`, kde je pri kazdom
kluci **slovenska hodnota s prefixom `TODO `**. Prelozit ich musi clovek. Ten
prefix je zamer - preklad, ktory nikto neprelozil, ma byt v kontrole vidno,
inak sa "dvojjazycna" appka odlisi od jednojazycnej len tym, ze ma dva razy
to iste.

Exit 0 = ciste, 1 = nieco chyba, 2 = zle pouzitie.
"""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Jazyky, v ktorych ma appka byt. Portal ponuka presne tieto dva
# (EtaskLanguageSelectorComponent), takze tretim jazykom v sieti by sa nedalo
# prepnut a naopak.
LOCALES = ("en",)          # `sk` je default value v samotnom elemente
DEFAULT_LOCALE_NAME = "sk"

TODO = "TODO "

# Elementy, ktore engine prekladá. Meno elementu -> pripona kluca.
#
# `<label>` je titulok prechodu (a miesta), `<title>` je vsetko ostatne.
# `<value>` NIE je v zozname: hodnoty `enumeration` su volby, ale ich
# prekladanie ma iny tvar (`<values>`) a tento repozitar ich nepouziva.
TRANSLATABLE = {
    "title": "title",
    "label": "label",
    "placeholder": "placeholder",
    "desc": "desc",
    "option": "opt",
    "caseName": "case_name",
}

# Kde sa `name` NEMA vyzadovat.
#
# `component`/`properties`/`property` - `<name>` v komponente je meno komponentu,
# nie text; tie neprechadzaju cez toI18NString.
#
# `place` - `<label>` miesta je modelovaci popis. Engine ho preklada rovnako ako
# ostatne, ale klientovi ho neposiela ZIADNY endpoint: payload siete je len
# referencia bez uzlov. Vyzadovat pre ne preklad by znamenalo prelozit polovicu
# siete pre nikoho - a hlavne by to zaplnilo vystup kontroly hlaskami, ktore sa
# daju ignorovat, cim by prestala fungovat cela kontrola.
SKIP_PARENTS = {"component", "properties", "property", "place"}


class Finding:
    def __init__(self, level, rule, path, line, message, fix=None):
        self.level = level
        self.rule = rule
        self.path = path
        self.line = line
        self.message = message
        self.fix = fix


def strip_ns(tag):
    return tag.split("}", 1)[-1]


def line_of(raw, needle, occurrence=1):
    """Cislo riadku n-teho vyskytu podstringu. 0 ked nie je."""
    idx = -1
    for _ in range(occurrence):
        idx = raw.find(needle, idx + 1)
        if idx < 0:
            return 0
    return raw.count("\n", 0, idx) + 1


def visible_strings(root):
    """
    Vsetky prelozitelne elementy siete s odvodenym klucom.

    Vracia (element, navrhovany_kluc, cesta_pre_hlasku). Kluc je odvodeny od id
    najblizsieho rodica, ktory id ma - takze `pu_meno` + `title` -> `pu_meno_title`.
    To je citatelne v bloku i18n a stabilne pri preusporiadani suboru.
    """
    out = []
    seen = {}

    def owner_id(stack):
        for el in reversed(stack):
            for child in el:
                if strip_ns(child.tag) == "id" and (child.text or "").strip():
                    return re.sub(r"[^A-Za-z0-9_]", "_", child.text.strip())
        return None

    def walk(el, stack):
        tag = strip_ns(el.tag)
        parent_tag = strip_ns(stack[-1].tag) if stack else ""
        if tag in TRANSLATABLE and parent_tag not in SKIP_PARENTS:
            suffix = TRANSLATABLE[tag]
            if tag == "option":
                key_attr = el.get("key") or ""
                suffix = f"opt_{re.sub(r'[^A-Za-z0-9_]', '_', key_attr)}"
            base = owner_id(stack) or "net"
            if tag == "caseName":
                key = "case_name"
            elif tag == "title" and parent_tag == "document":
                key = "net_title"
            else:
                key = f"{base}_{suffix}"
            # Kolizie: dva rovnake kluce v jednej sieti by v engine ukazovali
            # na TEN ISTY I18nString (Importer.toI18NString ich zdiela podla
            # mena) a prvy vyskyt by prepisal defaultValue pre oba.
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                key = f"{key}_{seen[key]}"
            out.append((el, key, f"<{tag}> v <{parent_tag}>"))
        for child in el:
            walk(child, stack + [el])

    walk(root, [])
    return out


def declared_i18n(root):
    """{locale: {name: hodnota}} z blokov <i18n> na urovni dokumentu."""
    blocks = {}
    for el in root:
        if strip_ns(el.tag) != "i18n":
            continue
        loc = el.get("locale") or ""
        blocks.setdefault(loc, {})
        for s in el:
            if strip_ns(s.tag) == "i18nString":
                blocks[loc][s.get("name") or ""] = (s.text or "")
    return blocks


def check(path):
    raw = path.read_text(encoding="utf-8")
    out = []
    rel = str(path)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return [Finding("error", "xml", rel, 0, f"nevalidne XML: {e}")]

    blocks = declared_i18n(root)

    # ---- 1. locale musi byt dvojpismenovy jazyk --------------------------
    for loc in blocks:
        if not re.fullmatch(r"[a-z]{2}", loc):
            out.append(Finding(
                "error", "i18n-locale-not-language", rel,
                line_of(raw, f'locale="{loc}"'),
                f'<i18n locale="{loc}"> sa naimportuje a NIKDY sa nepouzije',
                "kluc sa uklada verbatim, ale hlada sa cez Locale.getLanguage() "
                "- pouzi dvojpismenovy kod (ENGINE_ISSUES E15)"))

    strings = visible_strings(root)

    # ---- 2. kazdy viditelny text ma mat `name` --------------------------
    for el, suggested, where in strings:
        text = (el.text or "").strip()
        if not text:
            continue                      # prazdny titulok je zamer (skryje tlacidlo)
        if not el.get("name"):
            out.append(Finding(
                "error", "i18n-no-key", rel,
                line_of(raw, f">{text}<"),
                f'{where} "{text}" nema atribut `name`, takze sa neda prelozit',
                f'pridaj name="{suggested}" a riadok do bloku <i18n>'))

    # ---- 3. kazdy kluc ma mat preklad v kazdom jazyku -------------------
    used = {el.get("name"): (el.text or "").strip()
            for el, _, _ in strings if el.get("name")}
    for loc in LOCALES:
        have = blocks.get(loc, {})
        if not have and used:
            out.append(Finding(
                "error", "i18n-locale-missing", rel, 1,
                f'siet nema blok <i18n locale="{loc}"> - je jednojazycna',
                "spusti `pfi18n.py --init` a prelozi doplnene TODO riadky"))
            continue
        for name in sorted(used):
            if name not in have:
                out.append(Finding(
                    "error", "i18n-key-untranslated", rel,
                    line_of(raw, f'name="{name}"'),
                    f'kluc `{name}` nema preklad pre `{loc}`',
                    f'<i18nString name="{name}">...</i18nString>'))
            elif have[name].startswith(TODO):
                out.append(Finding(
                    "warning", "i18n-todo", rel,
                    line_of(raw, f'name="{name}"', 2) or line_of(raw, f'name="{name}"'),
                    f'kluc `{name}` ma pre `{loc}` len TODO, nie preklad',
                    f'prelozi: {have[name][len(TODO):]!r}'))

    # ---- 4. preklad na kluc, ktory nikto nepouziva ----------------------
    for loc, have in blocks.items():
        for name in sorted(have):
            if name not in used:
                out.append(Finding(
                    "warning", "i18n-key-unused", rel,
                    line_of(raw, f'name="{name}"'),
                    f'`{loc}` preklada kluc `{name}`, ktory v sieti nikto nema',
                    "premenovane pole, alebo preklep v `name`"))
    return out


def init(path):
    """
    Doplni chybajuce `name=` a blok `<i18n locale="en">` s TODO hodnotami.

    Pracuje na TEXTE, nie na strome. Zapisom `ElementTree.write` by sa prepisalo
    formatovanie celeho suboru - odsadenie, poradie atributov, komentare - a diff
    by bol necitatelny; pritom prave diff je to, co na tomto kroku niekto kontroluje.
    """
    raw = path.read_text(encoding="utf-8")
    root = ET.fromstring(raw)
    strings = visible_strings(root)
    added_names = 0

    for el, suggested, _ in strings:
        text = (el.text or "").strip()
        if not text or el.get("name"):
            continue
        tag = strip_ns(el.tag)
        # Najdi presne ten vyskyt v texte. Zaciatocna znacka moze mat atributy
        # (napr. <option key="a">), takze berieme ich a vlozime `name` za ne.
        #
        # Preskakujeme vyskyty, ktore uz `name` maju. Bez toho sa nastroj
        # rozbije na sieti, kde ma dva rozne elementy ten isty text - napr.
        # `<title>Popis</title>` na dvoch poliach. Prvy priechod prvemu doplni
        # `name`, druhy priechod hlada od zaciatku, trafi TEN ISTY element
        # (vzor mu sedi aj s doplnenym atributom) a vlozi `name` druhy raz.
        # Vysledok je `duplicate attribute` z parsera - co je este stastie;
        # keby XML prezilo, druhy element by zostal neprelozeny a prvy by mal
        # cudzi kluc, a to uz nic nenahlasi.
        pattern = re.compile(
            r"<" + re.escape(tag) + r"((?:\s+[a-zA-Z_:][-\w:.]*\s*=\s*\"[^\"]*\")*)\s*>"
            + re.escape(text) + r"</" + re.escape(tag) + r">")
        m = next((x for x in pattern.finditer(raw)
                  if not re.search(r"\bname\s*=", x.group(1))), None)
        if not m:
            print(f"  ! nenasiel som v texte <{tag}>{text}</{tag}> - preskakujem",
                  file=sys.stderr)
            continue
        attrs = m.group(1)
        raw = (raw[:m.start()]
               + f"<{tag}{attrs} name=\"{suggested}\">{text}</{tag}>"
               + raw[m.end():])
        el.set("name", suggested)
        added_names += 1

    # Preklady, ktore este nie sú.
    root = ET.fromstring(raw)
    strings = visible_strings(root)
    used = [(el.get("name"), (el.text or "").strip())
            for el, _, _ in strings if el.get("name") and (el.text or "").strip()]
    blocks = declared_i18n(root)

    added_rows = 0
    for loc in LOCALES:
        have = blocks.get(loc, {})
        missing = [(n, v) for n, v in used if n not in have]
        if not missing:
            continue
        rows = "\n".join(
            f"\t\t<i18nString name=\"{n}\">{TODO}{v}</i18nString>" for n, v in missing)
        added_rows += len(missing)
        if loc in blocks:
            # doplni do existujuceho bloku, pred jeho zatvaraciu znacku
            m = re.search(r"(<i18n\s+locale=\"" + loc + r"\"\s*>)(.*?)(</i18n>)",
                          raw, re.S)
            raw = raw[:m.end(2)] + "\n" + rows + "\n\t" + raw[m.end(2):]
        else:
            block = (f"\n\t<!--\n"
                     f"\t\tPreklady. Kluc je atribut `name` na prelozitelnom elemente;\n"
                     f"\t\tbez oboch polovic sa zobrazi povodna hodnota a nic to nepovie.\n"
                     f"\t\tKod jazyka musi byt DVOJPISMENOVY - `en-US` sa naimportuje\n"
                     f"\t\ta nikdy sa nepouzije (ENGINE_ISSUES E15).\n"
                     f"\t-->\n"
                     f"\t<i18n locale=\"{loc}\">\n{rows}\n\t</i18n>\n")
            # Za `<caseName>`, inak za `<title>` dokumentu - blok i18n moze byt
            # kdekolvek na urovni dokumentu, XSD ho neviaze na poziciu.
            anchor = re.search(r"</caseName>\s*\n", raw) or \
                re.search(r"</title>\s*\n", raw)
            raw = raw[:anchor.end()] + block + raw[anchor.end():]

    path.write_text(raw, encoding="utf-8")
    return added_names, added_rows


def collect(args):
    paths = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            paths.extend(sorted(p.glob("*.xml")))
        elif p.exists():
            paths.append(p)
        else:
            print(f"pfi18n: {a} neexistuje", file=sys.stderr)
            return None
    return paths


def main(argv):
    do_init = "--init" in argv
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__.strip())
        return 2
    paths = collect(args)
    if paths is None:
        return 2

    if do_init:
        for p in paths:
            names, rows = init(p)
            print(f"{p}: doplnene {names} `name=`, {rows} TODO prekladov")
        print("\npfi18n: TODO riadky treba prelozit - `pfi18n.py` ich hlasi ako warning")
        return 0

    findings = []
    for p in paths:
        findings.extend(check(p))

    errors = [f for f in findings if f.level == "error"]
    warns = [f for f in findings if f.level == "warning"]
    for f in sorted(findings, key=lambda x: (x.path, x.line)):
        print(f"{f.level:9}  {f.path}:{f.line}  [{f.rule}] {f.message}")
        if f.fix:
            print(f"           -> {f.fix}")
    print(f"\npfi18n: {len(paths)} sieti, {len(errors)} chyb, {len(warns)} upozorneni")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
