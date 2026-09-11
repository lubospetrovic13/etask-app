#!/usr/bin/env python3
"""
pfview - staticke overenie frontendovej vrstvy (Angular) proti sietam.

Vrstva 3 nema ekvivalent `pfsync`: kompilator overi typy, nie zmysel. Tri veci
pretecu buildom aj kazdou existujucou kontrolou a prejavia sa az preklikanim:

  A. Kopie kniznicnych sablon zastarnu. `etask-field-component-resolver` je
     kopia kniznicneho resolvera. Ked kniznica pridá novy typ pola, v kopii
     chyba `*ngSwitchCase` a pole sa vykresli ako PRAZDNE MIESTO. Bez chyby,
     bez warningu. (docs/FRONTEND_LEARNINGS.md, D1.)
  B. Kniznicny komponent obide vlastny. `<nc-task-list>` renderuje kniznicny
     panel, teda kniznicny resolver - vlastne polia sa nezobrazia VOBEC.
     Spravne je `<app-etask-task-list>`. Najdrahsia chyba v historii tohto
     frontendu. (D2.)
  C. Siet si vypyta komponent, ktory frontend nepozna. `<component><name>` je
     volny retazec; kniznica nezname meno TICHO ignoruje a vykresli default.

Ziadna z tychto kontrol nie je zoznam napisany rukou - inventar sa cita
z `node_modules/@netgrif` pri kazdom spusteni, takze po `npm update` sa
odpovede zmenia spolu s kniznicou. To je zamer: rucny zoznam by po prvom
povyseni verzie klamal.

    python3 tools/pfview.py                 # vsetky kontroly
    python3 tools/pfview.py --inventory     # vypis, co sa z kniznice precitalo
    python3 tools/pfview.py --src DIR --nets DIR    # pre pftest.sh, na fixtures

Bez `node_modules` sa A a B preskocia (a povie to). C bezi vzdy, len s uzsim
inventarom.

Exit 0 = ciste, 1 = chyba, 2 = nedalo sa overit.
"""

import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = ROOT.parent
FRONTEND = REPO / "etask-frontend-starter"
NM = FRONTEND / "node_modules" / "@netgrif"
SRC = FRONTEND / "src"
NETS = ROOT / "processes"

# Retazcovy literal v JS vratane escapov - `template: "...."` v ngDeclareComponent.
JS_STR = r'"((?:[^"\\]|\\.)*)"'

errors, warnings, notes = [], [], []


def err(msg):
    errors.append(msg)
    print("CHYBA      " + msg)


def warn(msg):
    warnings.append(msg)
    print("UPOZORNENIE " + msg)


def note(msg):
    notes.append(msg)
    print("poznamka   " + msg)


def strip_html_comments(text):
    """Bez tohto by kontrola B hlasila prave ten subor, ktory tu chybu VYSVETLUJE
    v komentari ('kniznicna sablona ma tu <nc-task-list>'). Falosny poplach na
    dokumentacii opravy je najrychlejsia cesta k tomu, aby sa nastroj prestal
    citat."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


# ---------------------------------------------------------------- kniznica

def library_templates():
    """{selector: template} zo skompilovanych balikov kniznice."""
    out = {}
    for pkg in ("components", "components-core"):
        d = NM / pkg / "fesm2020"
        if not d.is_dir():
            continue
        for bundle in d.glob("*.mjs"):
            text = bundle.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(
                    r"selector: " + JS_STR + r"(.{0,4000}?)template: " + JS_STR,
                    text, re.S):
                sel, tpl = m.group(1), m.group(3)
                if sel in out:
                    continue
                try:
                    out[sel] = json.loads('"' + tpl + '"')
                except ValueError:
                    pass
    return out


# Priecinok zdrojakov kniznice -> typ `<data type=>`. Sluzi na prislusnost mien
# komponentov, ktore sa citaju v kode a nie v sablone.
FOLDER_TO_TYPE = {
    "text-field": "text", "number-field": "number", "enumeration-field": "enumeration",
    "multichoice-field": "multichoice", "boolean-field": "boolean",
    "button-field": "button", "date-field": "date", "date-time-field": "dateTime",
    "user-field": "user", "user-list-field": "userList", "file-field": "file",
    "file-list-field": "fileList", "i18n-field": "i18n", "task-ref-field": "taskRef",
    "filter-field": "filter",
}


def library_component_names(templates):
    """(per_type, any_name) - mena `<component><name>`, na ktore kniznica reaguje.

    Zdroje su tri, lebo kniznica ich nedrzi na jednom mieste:
      * `ngSwitch` na `getComponentType()` v sablone konkretneho typu pola
        (nc-number-field -> currency), co dava aj prislusnost k typu;
      * typovane enumy v .d.ts (TextFieldComponent, TaskRefComponents);
      * pole `textFieldNames` a porovnania `component.name === '...'` v kode.
    """
    per_type, any_name = {}, set()

    sel_to_type = {
        "nc-text-field": "text", "nc-number-field": "number",
        "nc-enumeration-field": "enumeration", "nc-multichoice-field": "multichoice",
        "nc-boolean-field": "boolean", "nc-button-field": "button",
        "nc-date-field": "date", "nc-date-time-field": "dateTime",
        "nc-user-field": "user", "nc-user-list-field": "userList",
        "nc-file-field": "file", "nc-file-list-field": "fileList",
        "nc-i18n-field": "i18n", "nc-task-ref-field": "taskRef",
        "nc-filter-field": "filter",
    }

    def add(t, name):
        any_name.add(name)
        if t:
            per_type.setdefault(t, set()).add(name)

    for sel, tpl in templates.items():
        t = sel_to_type.get(sel)
        if not t:
            continue
        # ngSwitch na getComponentType() aj priame porovnania v ngClass.
        if re.search(r'\[ngSwitch\]="[^"]*omponent[^"]*"', tpl):
            for n in re.findall(r"ngSwitchCase=\"'([^']+)'\"", tpl):
                add(t, n)
        for n in re.findall(r"getComponentType\(\) ?===? ?'([^']+)'", tpl):
            add(t, n)

    # enumeration_map / multichoice_map maju rovnaky renderer ako bezmapove verzie.
    for base, mapped in (("enumeration", "enumeration_map"),
                         ("multichoice", "multichoice_map")):
        if base in per_type:
            per_type[mapped] = set(per_type[base])

    enum_to_type = {"TextFieldComponent": "text", "TaskRefComponents": "taskRef"}
    for dts in NM.rglob("*.d.ts"):
        src = dts.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"declare enum (\w*Component\w*) \{(.*?)\}", src, re.S):
            t = enum_to_type.get(m.group(1))
            for n in re.findall(r'=\s*"([^"]+)"', m.group(2)):
                add(t, n)

    for pkg in ("components", "components-core"):
        d = NM / pkg / "fesm2020"
        for bundle in (d.glob("*.mjs") if d.is_dir() else []):
            text = bundle.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"textFieldNames = \[([^\]]*)\]", text)
            if m:
                for n in re.findall(r"'([^']+)'", m.group(1)):
                    add("text", n)
            for n in re.findall(r"component\??\.name ?===? ?'([^']+)'", text):
                add(None, n)

    # Stvrty zdroj: porovnanie `component.name === KONSTANTA` v zdrojaku
    # konkretneho field komponentu.
    #
    # Bez neho tento nastroj tvrdil, ze `<component><name>preview</name></component>
    # na `file` poli nikto nerenderuje - a pritom `abstract-file-field.component`
    # ma `const preview = 'preview'` a porovnava sa s tou premennou, nie
    # s literalom. Regex vyssie hlada len literal, takze cele meno prepadlo.
    # Prislusnost k typu sa tu na rozdiel od zbaleneho balika ZISTIT DA -
    # zdrojaky su po jednom v priecinku podla typu pola.
    for pkg in ("components", "components-core"):
        base = NM / pkg / "esm2020" / "lib" / "data-fields"
        if not base.is_dir():
            continue
        for folder in base.iterdir():
            if not folder.is_dir():
                continue
            t = FOLDER_TO_TYPE.get(folder.name)
            for src in folder.rglob("*.mjs"):
                text = src.read_text(encoding="utf-8", errors="replace")
                consts = dict(re.findall(r"const (\w+) = '([^']+)'", text))
                for n in re.findall(r"component\??\.name ?===? ?'([^']+)'", text):
                    add(t, n)
                for var in re.findall(r"component\??\.name ?===? ?([A-Za-z_]\w*)", text):
                    if var in consts:
                        add(t, consts[var])
    return per_type, any_name


def library_field_types():
    """Hodnoty FieldTypeResource - typy `<data type=>`, ktore frontend vobec pozna."""
    for dts in NM.rglob("field-type-resource.d.ts"):
        body = re.search(r"declare enum FieldTypeResource \{(.*?)\}",
                         dts.read_text(encoding="utf-8", errors="replace"), re.S)
        if body:
            return dict(re.findall(r"(\w+) = \"([^\"]+)\"", body.group(1)))
    return {}


PROP_RE = (r"properties(?:\?)?\.([A-Za-z_][A-Za-z0-9_]*)"
           r"|properties(?:\?)?\[['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\]")


def prop_keys(text):
    return {a or b for a, b in re.findall(PROP_RE, text)}


def library_property_keys():
    """Kluce `<property key=>`, ktore kniznica vobec cita.

    Bez prislusnosti k typu pola - v zbalenom balike sa citanie properties
    nedá spolahlivo priradit ku konkretnemu field komponentu, a tvrdit to
    napolovicu by bolo horsie ako netvrdit nic. Priradenie k typu mame len
    pre projektove komponenty, ktore su v samostatnych suboroch.
    """
    keys = set()
    for pkg in ("components", "components-core"):
        d = NM / pkg / "fesm2020"
        for bundle in (d.glob("*.mjs") if d.is_dir() else []):
            keys |= prop_keys(bundle.read_text(encoding="utf-8", errors="replace"))
    return keys


def resolver_property_keys():
    """Kluce `<property key=>`, ktore cita nas resolver poli.

    Resolver (`app-etask-field-component-resolver`) renderuje KAZDY typ pola,
    takze property, ktoru cita on, je platna na kazdom type - na rozdiel od
    komponentu jedneho typu. Bez tejto vynimky by `pfview` hlasil
    `saveWhileTyping` ako "property, ktoru nikto necita", hoci ju cita.

    Zamerne sa scanuje LEN resolver, nie cely `src/`: keby stacilo, ze sa
    `properties.x` niekde v appke vyskytuje, kontrola by prestala chytat
    preklepy - a to je jediny dovod, preco existuje.
    """
    for ts in SRC.rglob("*.ts"):
        if ts.name.endswith(".spec.ts"):
            continue
        text = ts.read_text(encoding="utf-8", errors="replace")
        if "selector: 'app-etask-field-component-resolver'" not in text:
            continue
        html = ts.parent / (ts.name[:-3] + ".html")
        tpl = html.read_text(encoding="utf-8", errors="replace") if html.exists() else ""
        return prop_keys(text) | prop_keys(tpl)
    return set()


def project_field_components():
    """{typ pola: {"keys": kluce properties, "names": mena komponentov, "file": cesta}}

    Ktory typ pola komponent renderuje, sa cita z jeho selektora:
    `app-etask-boolean-field` -> `boolean`. Preto ta konvencia stoji za drzanie.
    """
    out = {}
    for ts in SRC.rglob("*.ts"):
        if ts.name.endswith(".spec.ts"):
            continue
        text = ts.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"selector: 'app-etask-([a-z0-9-]+)-field'", text)
        if not m:
            continue
        slug = m.group(1)
        # date-time -> dateTime, file-list -> fileList
        parts = slug.split("-")
        ftype = parts[0] + "".join(w.capitalize() for w in parts[1:])
        html = ts.with_suffix("").with_suffix("")
        html = ts.parent / (ts.name[:-3] + ".html")
        tpl = html.read_text(encoding="utf-8", errors="replace") if html.exists() else ""
        names = set(re.findall(r"getComponentType\(\) ?===? ?'([^']+)'", text + tpl))
        if re.search(r"component(?:\?)?\.name", text + tpl):
            names |= set(re.findall(r"component(?:\?)?\.name ?===? ?'([^']+)'", text + tpl))
            reads_name = True
        else:
            reads_name = bool(names)
        out[ftype] = {
            "keys": prop_keys(text) | prop_keys(tpl),
            "names": names,
            "reads_name": reads_name,
            "file": rel(ts),
        }
    return out


# ------------------------------------------------- A. drift kopii sablon

def rel(path):
    """Cesta na vypis. Fixture moze lezat mimo repozitara, potom relative_to padne."""
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def check_copies(templates):
    """Kazdy projektovy subor, ktory o sebe hovori, ze je kopiou kniznicneho,
    sa porovna s originalom vytiahnutym z baliku."""
    print("\n== A. Kopie kniznicnych sablon")
    copies = []
    for p in sorted(SRC.rglob("*.html")):
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"[Cc]opy of @netgrif/components ([\w.-]+)\.component\.html", text)
        if m:
            copies.append((p, "nc-" + m.group(1), text))
    if not copies:
        note("ziadny subor sa nehlasi ako kopia kniznicnej sablony")
        return

    for path, selector, text in copies:
        label = rel(path)
        orig = templates.get(selector)
        if orig is None:
            warn(f"{label}: original <{selector}> sa v baliku nenasiel "
                 f"- kniznica ho premenovala alebo zrusila")
            continue
        lib_cases = set(re.findall(r'\*?ngSwitchCase="([^"]+)"', orig))
        our_cases = set(re.findall(r'\*?ngSwitchCase="([^"]+)"', text))
        missing = sorted(lib_cases - our_cases)
        extra = sorted(our_cases - lib_cases)
        if missing:
            err(f"{label}: kopia zaostala za <{selector}> - chyba "
                f"{', '.join(missing)}. Take pole sa vykresli ako prazdne miesto.")
        if extra:
            note(f"{label}: navyse oproti kniznici: {', '.join(extra)} (vlastne rozsirenie)")
        if not missing:
            print(f"  [OK] {label:70s} {len(lib_cases)} vetiev sedi s <{selector}>")


# ------------------------------------- B. kniznicny komponent obchadza vlastny

def check_overrides():
    print("\n== B. Obidene vlastne komponenty")
    owned = {}      # nc-x -> app-etask-x
    home = {}       # app-etask-x -> priecinok, kde smie pouzit nc-x (obalenie)
    for ts in SRC.rglob("*.ts"):
        for sel in re.findall(r"selector: '(app-etask-[a-z0-9-]+)'",
                              ts.read_text(encoding="utf-8", errors="replace")):
            owned["nc-" + sel[len("app-etask-"):]] = sel
            home[sel] = ts.parent
    if not owned:
        note("projekt nema vlastne app-etask-* komponenty")
        return

    hit = False
    for p in sorted(SRC.rglob("*.html")):
        # Komentare prec: subor, ktory chybu vysvetluje, nie je chyba.
        text = strip_html_comments(p.read_text(encoding="utf-8", errors="replace"))
        for nc in sorted(set(re.findall(r"<(nc-[a-z0-9-]+)", text))):
            if nc not in owned:
                continue
            # Vlastny komponent smie kniznicny obalit vo svojej vlastnej sablone.
            if p.parent == home.get(owned[nc]):
                continue
            hit = True
            err(f"{rel(p)}: <{nc}> obchadza vlastny "
                f"<{owned[nc]}> - v tejto vetve sa vlastne polia nevykreslia")
    if not hit:
        print(f"  [OK] ziadna sablona neobchadza {len(owned)} vlastnych komponentov "
              f"({', '.join(sorted(owned.values()))})")


# --------------------------------------------- C. siete proti frontendu

def check_nets(per_type, any_name, field_types, resolver_types,
               lib_prop_keys, project, resolver_keys=frozenset()):
    """Siet si vypyta komponent alebo property, ktoru nikto nerenderuje.

    Kto typ pola vlastni, urcuje, co sa da overit:

      * kniznicny typ - `<component><name>` sa porovna s inventarom kniznice.
      * projektovy typ (existuje `app-etask-<typ>-field`) - meno moze byt lubovolne,
        ak komponent `component.name` vobec necita. Tak to je pri `boolean`:
        variantu berie z `<properties><property key="variant">`, takze `<name>`
        je len navestie a kontrola mena by hlasila 15 falosnych chyb.
        Zato kluce properties sa overit DAJU, a prave tam je ta ticha chyba -
        preklep v `key` komponent ignoruje a pole sa vykresli ako default.
    """
    print("\n== C. Siete proti frontendu")
    known_types = set(field_types.values())
    skipped_names = set()
    bad = False
    for xml in sorted(NETS.glob("*.xml")):
        label = rel(xml)
        try:
            root = ET.parse(xml).getroot()
        except ET.ParseError as e:
            err(f"{label}: XML sa neda rozparsovat ({e})")
            bad = True
            continue
        for data in root.iter("data"):
            t = data.get("type")
            fid = (data.findtext("id") or "?").strip()
            where = f"{label}: pole '{fid}' (type={t})"
            if t not in known_types:
                err(f"{where}: taky typ pola frontend nepozna")
                bad = True
                continue
            if resolver_types and t not in resolver_types:
                err(f"{where}: resolver appky tento typ nerenderuje "
                    f"- pole ostane prazdne miesto")
                bad = True
            comp = data.find("component")
            if comp is None:
                continue
            own = project.get(t)
            name = (comp.findtext("name") or "").strip()
            allowed = set(per_type.get(t, ())) | set((own or {}).get("names", ()))
            if name and own and not own["reads_name"]:
                skipped_names.add(t)
            elif name and name not in (any_name | set((own or {}).get("names", ()))):
                err(f"{where}: komponent '{name}' nepozna kniznica ani appka "
                    f"- ticho sa vykresli default. Zname pre {t}: "
                    f"{', '.join(sorted(allowed)) or '(ziadne)'}")
                bad = True
            elif name and allowed and name not in allowed:
                warn(f"{where}: komponent '{name}' existuje, ale nie pre typ {t} "
                     f"- zname pre {t}: {', '.join(sorted(allowed))}")

            for prop in comp.iter("property"):
                key = (prop.get("key") or "").strip()
                if not key:
                    continue
                if key in resolver_keys:
                    # Property cita resolver, ktory renderuje kazdy typ.
                    continue
                if own is not None:
                    if key not in own["keys"]:
                        err(f"{where}: property '{key}' nikde v {own['file']} "
                            f"necita - ticho sa zahodi. Zname: "
                            f"{', '.join(sorted(own['keys'])) or '(ziadne)'}")
                        bad = True
                elif key not in lib_prop_keys:
                    err(f"{where}: property '{key}' kniznica necita "
                        f"- ticho sa zahodi")
                    bad = True

    for t in sorted(skipped_names):
        note(f"typ '{t}' renderuje {project[t]['file']}, ktory `component.name` "
             f"necita - meno komponentu sa pri tomto type neoveruje, "
             f"kontroluju sa len properties")
    if not bad:
        print("  [OK] vsetky polia maju typ, komponent aj properties, "
              "ktore niekto naozaj renderuje")


def resolver_field_types(field_types):
    """Typy, ktore renderuje resolver TEJTO appky (nie kniznicny)."""
    for p in SRC.rglob("*field-component-resolver*.html"):
        text = p.read_text(encoding="utf-8", errors="replace")
        keys = re.findall(r'ngSwitchCase="fieldTypeEnum\.(\w+)"', text)
        if keys:
            return {field_types[k] for k in keys if k in field_types}
    return set()


def main():
    global SRC, NETS
    argv = sys.argv[1:]
    for flag, target in (("--src", "SRC"), ("--nets", "NETS")):
        if flag in argv:
            globals()[target] = pathlib.Path(argv[argv.index(flag) + 1]).resolve()
    if not NETS.is_dir():
        print("pfview: priecinok processes/ neexistuje")
        return 2

    have_lib = NM.is_dir()
    if not have_lib:
        print("pfview: node_modules/@netgrif chyba - A a B sa preskocia.")
        print("        Inventar komponentov bude prazdny, takze C nema s cim porovnavat.")
        print("        Spusti `npm ci` v etask-frontend-starter/.")
        return 2

    templates = library_templates()
    per_type, any_name = library_component_names(templates)
    field_types = library_field_types()
    res_types = resolver_field_types(field_types)
    lib_prop_keys = library_property_keys()
    resolver_keys = resolver_property_keys()
    project = project_field_components()

    if "--inventory" in sys.argv:
        print(f"kniznicne sablony: {len(templates)}")
        print(f"typy poli (FieldTypeResource): {', '.join(sorted(field_types.values()))}")
        print(f"resolver appky renderuje: {', '.join(sorted(res_types))}")
        print("mena komponentov podla typu:")
        for t in sorted(per_type):
            print(f"  {t:16s} {', '.join(sorted(per_type[t]))}")
        others = sorted(any_name - set().union(*per_type.values()) if per_type else any_name)
        if others:
            print(f"  {'(bez typu)':16s} {', '.join(others)}")
        print("vlastne field komponenty appky:")
        for t in sorted(project):
            d = project[t]
            print(f"  {t:16s} properties: {', '.join(sorted(d['keys'])) or '-'}"
                  f"   cita component.name: {'ano' if d['reads_name'] else 'NE'}")
        print(f"properties, ktore cita kniznica: {', '.join(sorted(lib_prop_keys))}")
        return 0

    print(f"pfview: kniznica {len(templates)} sablon, "
          f"{len(any_name)} mien komponentov, resolver appky {len(res_types)} typov poli")
    check_copies(templates)
    check_overrides()
    check_nets(per_type, any_name, field_types, res_types, lib_prop_keys, project,
               resolver_keys)

    print(f"\npfview: {len(errors)} chyb, {len(warnings)} upozorneni, {len(notes)} poznamok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
