#!/usr/bin/env python3
"""
Petriflow linter - staticka kontrola sieti pred importom.

Preco to existuje: Petriflow akcie su Groovy v CDATA vnutri XML. Nic ich pred
behom neskontroluje - ani XSD, ani kompilator. Chyba sa preto prejavi az za behu,
casto ticho: akcia spadne v strede, cast zmien je zapisana, zvysok nie, a
v odpovedi nie je nic. Tento nastroj hlada presne tie tichosti, ktore su
zdokumentovane v docs/PETRIFLOW_LEARNINGS.md a kazda z nich stala aspon jedno
kolo ladenia.

Nie je to typovy kontrolor. Je to zoznam znamych sposobov, ako sa Petriflow
rozbije bez toho, aby to povedal.

    python3 tools/pflint.py processes/*.xml
    python3 tools/pflint.py --strict processes/    # warning tiez konci nenulovo

Exit 0 = ciste, 1 = chyba, 2 = zle pouzitie.
"""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Role, ktore engine deklaruje sam - nemusia byt v <role>.
BUILTIN_ROLES = {"anonymous", "default"}

# Typy, ktore Petriflow pozna. `textarea` medzi nimi NIE je - je to komponent.
KNOWN_TYPES = {
    "text", "number", "enumeration", "enumeration_map", "multichoice",
    "multichoice_map", "boolean", "date", "dateTime", "file", "fileList",
    "user", "userList", "button", "taskRef", "caseRef", "i18n", "filter",
    "dateTimeInterval",
}

# Poradie podelementov <data> tu ZAMERNE nekontrolujeme. Existuju tri zdroje
# pravdy a odporuju si:
#
#   1. Oficialna XSD (petriflow.com, v1.1.0, priloz. reference/petriflow.schema.xsd):
#      id → title → placeholder → desc → options → valid → init → format → view
#      → component → encryption → action|event → ...
#   2. NAE 6.3.1 za behu: prijme aj <component> pred <init>. Vsetky siete v tomto
#      repozitari to tak maju a importuju sa.
#   3. docs/PETRIFLOW_LEARNINGS B5 tvrdi desc hned za title, teda pred placeholder.
#
# Linter, ktory oznackuje funkcny kod, naucí agenta ignorovat linter. Poradie
# preto patri do reference knowledge, nie do kontroly - a jedina spolahliva
# kontrola dialektu je import do beziaceho enginu (tools/pfcheck.sh).


class Finding:
    def __init__(self, level, rule, path, line, message, fix=None):
        self.level = level
        self.rule = rule
        self.path = path
        self.line = line
        self.message = message
        self.fix = fix

    def render(self):
        head = f"{self.path}:{self.line}: {self.level.upper()} [{self.rule}] {self.message}"
        return head + (f"\n    → {self.fix}" if self.fix else "")


def line_of(raw, needle, occurrence=1):
    """Cislo riadku, na ktorom sa needle vyskytuje. Best effort - ElementTree
    v standardnej kniznici cisla riadkov nedava a lxml nechceme ako zavislost."""
    idx = -1
    for _ in range(occurrence):
        idx = raw.find(needle, idx + 1)
        if idx < 0:
            return 1
    return raw.count("\n", 0, idx) + 1


def strip_comments(body):
    """Bez tohto linter hlasi vzory, ktore su v komentari - vratane komentarov,
    ktore pred tym istym vzorom varuju."""
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    return re.sub(r"//[^\n]*", " ", body)


def strip_ns(tag):
    return tag.split("}", 1)[-1]


def child_text(el, name):
    for c in el:
        if strip_ns(c.tag) == name:
            return (c.text or "").strip()
    return None


def findall(el, name):
    return [c for c in el.iter() if strip_ns(c.tag) == name]


def direct(el, name):
    return [c for c in el if strip_ns(c.tag) == name]


def lint(path):
    out = []
    raw = Path(path).read_text(encoding="utf-8")
    rel = str(path)

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return [Finding("error", "xml", rel, getattr(e, "lineno", 1),
                        f"XML sa neda rozparsovat: {e}")]

    # ---- inventar -------------------------------------------------------
    data_els = direct(root, "data")
    data_types, data_immediate = {}, {}
    for d in data_els:
        fid = child_text(d, "id")
        if not fid:
            out.append(Finding("error", "data-no-id", rel, line_of(raw, "<data"),
                               "<data> bez <id>"))
            continue
        if fid in data_types:
            out.append(Finding("error", "data-dup", rel, line_of(raw, f"<id>{fid}</id>"),
                               f"pole '{fid}' je deklarovane viackrat"))
        data_types[fid] = d.get("type")
        data_immediate[fid] = d.get("immediate") == "true"

    roles = {child_text(r, "id") for r in direct(root, "role")}
    transitions = {}
    for t in direct(root, "transition"):
        tid = child_text(t, "id")
        if tid:
            transitions[tid] = t
    places = {child_text(p, "id") for p in direct(root, "place")}

    # ---- 1. typy polí ---------------------------------------------------
    for fid, typ in data_types.items():
        if typ is None:
            out.append(Finding("error", "data-no-type", rel, line_of(raw, f"<id>{fid}</id>"),
                               f"pole '{fid}' nema atribut type"))
        elif typ == "textarea":
            out.append(Finding("error", "type-textarea", rel, line_of(raw, f"<id>{fid}</id>"),
                               f"'{fid}': type=\"textarea\" neexistuje, import spadne na NullPointerException",
                               "<data type=\"text\"> + <component><name>textarea</name></component>"))
        elif typ not in KNOWN_TYPES:
            out.append(Finding("warning", "type-unknown", rel, line_of(raw, f"<id>{fid}</id>"),
                               f"'{fid}': neznamy typ '{typ}'"))

    # ---- 3. dataRef bez deklaracie a mrtve polia ------------------------
    referenced = set()
    for tid, t in transitions.items():
        for dr in findall(t, "dataRef"):
            fid = child_text(dr, "id")
            if not fid:
                continue
            referenced.add(fid)
            if fid not in data_types:
                out.append(Finding("error", "dataref-undeclared", rel,
                                   line_of(raw, f"<id>{fid}</id>"),
                                   f"transition '{tid}' odkazuje na pole '{fid}', ktore nie je deklarovane"))
    action_text = " ".join(strip_comments(a.text or "") for a in findall(root, "action"))
    for fid in data_types:
        if fid not in referenced and not re.search(r"\b" + re.escape(fid) + r"\b", action_text):
            out.append(Finding("info", "data-unused", rel, line_of(raw, f"<id>{fid}</id>"),
                               f"pole '{fid}' nie je v ziadnom dataGroup ani v akcii tejto siete",
                               "moze byt v poriadku - hodnotu mu vie zapisat ina siet cez "
                               "setData(transition, case, map); inak je to mrtve pole"))

    # ---- 4. role ---------------------------------------------------------
    for tid, t in transitions.items():
        for rr in findall(t, "roleRef"):
            rid = child_text(rr, "id")
            if rid and rid not in roles and rid not in BUILTIN_ROLES:
                out.append(Finding("error", "role-undeclared", rel,
                                   line_of(raw, f"<id>{rid}</id>"),
                                   f"transition '{tid}': rola '{rid}' nie je deklarovana ako <role>",
                                   f"import spadne na IllegalArgumentException: Role {rid} not found"))
        for ur in findall(t, "userRef"):
            uid = child_text(ur, "id")
            if uid and uid not in data_types:
                out.append(Finding("error", "userref-undeclared", rel,
                                   line_of(raw, f"<id>{uid}</id>"),
                                   f"transition '{tid}': userRef '{uid}' nie je datove pole"))
            elif uid and data_types.get(uid) not in ("userList", "user"):
                out.append(Finding("error", "userref-type", rel,
                                   line_of(raw, f"<id>{uid}</id>"),
                                   f"userRef '{uid}' je typu '{data_types.get(uid)}', musi byt userList alebo user"))

    # ---- 5. arcs ---------------------------------------------------------
    nodes = set(transitions) | places
    for a in direct(root, "arc"):
        aid = child_text(a, "id") or "?"
        for end in ("sourceId", "destinationId"):
            ref = child_text(a, end)
            if ref and ref not in nodes:
                out.append(Finding("error", "arc-dangling", rel,
                                   line_of(raw, f"<{end}>{ref}</{end}>"),
                                   f"arc '{aid}': {end} '{ref}' nie je place ani transition"))

    # ---- 6. akcie: id-cka a znamé tichosti ------------------------------
    action_ids, action_bodies = {}, []
    for act in findall(root, "action"):
        aid = act.get("id")
        body = strip_comments(act.text or "")
        action_bodies.append((aid, body))
        if aid is None:
            continue
        if aid in action_ids:
            out.append(Finding("warning", "action-dup-id", rel,
                               line_of(raw, f'<action id="{aid}"'),
                               f"action id=\"{aid}\" je pouzite viackrat"))
        action_ids[aid] = True

    for aid, body in action_bodies:
        where = f'<action id="{aid}"' if aid else "<action"
        ln = line_of(raw, where)

        if re.search(r"\?\._id\b", body):
            out.append(Finding("error", "unsafe-nav-property", rel, ln,
                               "`?._id` - Groovy `?.` chrani pred null, NIE pred chybajucou property. "
                               "Na UserFieldValue to vyhodi MissingPropertyException a zhodi celu akciu",
                               "pouzi `u instanceof Map ? u[\"_id\"] : (u.hasProperty(\"id\") ? u.id : null)`"))

        if re.search(r"findCases?\s*\{[^}]*\bit\.stringId\b", body):
            out.append(Finding("error", "findcase-stringid", rel, ln,
                               "`findCase { it.stringId... }` vrati vzdy null - Case v mongo dokumente "
                               "pole stringId nema, query sa nezmapuje a v logu je len INFO",
                               "`it._id.eq(new org.bson.types.ObjectId(id))`, alebo najdi task cez it.caseId"))

        if re.search(r"async\.run\s*\{", body) and re.search(r"\b(setData|createCase|assignTask)\b", body):
            out.append(Finding("warning", "async-swallows", rel, ln,
                               "`async.run` vynimku spolkne - prenos dat medzi casmi sa potom prejavi "
                               "len tym, ze cielovy case je prazdny, bez akejkolvek stopy",
                               "synchronne v try/catch, a chybu zapis do datoveho pola"))

        if re.search(r"\bmake\b[^\n]*\bon transition\b(?!s)", body):
            out.append(Finding("error", "make-singular", rel, ln,
                               "`on transition` - spravne je mnozne cislo `on transitions`"))

        if re.search(r"\.getFieldValue\s*\(", body):
            out.append(Finding("error", "getfieldvalue", rel, ln,
                               "`getFieldValue(...)` na Case pada",
                               "`caseObj.dataSet[\"id\"]?.value`"))

        # setData na transition, ktory v sieti nie je
        # Trojargumentova forma setData("t_x", caseObj, map) mieri do INEJ siete,
        # tam transition overit nevieme. Kontrolujeme len setData("t_x", map).
        for m in re.finditer(r'setData\s*\(\s*"([^"]+)"\s*,\s*\[', body):
            tid = m.group(1)
            if tid not in transitions:
                out.append(Finding("error", "setdata-unknown-transition", rel, ln,
                                   f"setData(\"{tid}\", ...) - taky transition v tejto sieti nie je",
                                   "ak mieri do inej siete, over id tam; preklep tu spadne az za behu"))

        # polia v hlavicke akcie (`x: f.x, ...`) musia existovat
        head = body.split(";", 1)[0] if ";" in body else ""
        for m in re.finditer(r"\bf\.([A-Za-z_][A-Za-z0-9_]*)", head):
            fid = m.group(1)
            if fid not in data_types:
                out.append(Finding("error", "action-unknown-field", rel, ln,
                                   f"akcia berie `f.{fid}`, ale take pole v sieti nie je"))

        # bodka/dolar v kluci mapy (B1)
        # Pozor na ternary `cond ? "veta." : ...` - to nie je kluc mapy.
        for m in re.finditer(r'[\[,]\s*"([^"\s]*[.$][^"\s]*)"\s*:', body):
            key = m.group(1)
            if not key.startswith("$") and "(" not in key:
                out.append(Finding("warning", "mongo-map-key", rel, ln,
                                   f"kluc mapy '{key}' obsahuje . alebo $ - mongo to odmietne",
                                   "sluggifikuj kluc"))

    # ---- 7. button cita textove pole v tej istej poziadavke (B2) --------
    for tid, t in transitions.items():
        group_fields = {child_text(dr, "id") for dr in findall(t, "dataRef")}
        # Pasca plati len na pole, do ktoreho user v tom okamihu pise. Pole
        # oznacene `visible` ziadny blur nevyvola, takze ho button cita bezpecne.
        editable = set()
        for dr in findall(t, "dataRef"):
            drid = child_text(dr, "id")
            behaviors = {(b.text or "").strip() for b in findall(dr, "behavior")}
            if drid and "editable" in behaviors:
                editable.add(drid)
        for d in data_els:
            fid = child_text(d, "id")
            if data_types.get(fid) != "button" or fid not in group_fields:
                continue
            for act in findall(d, "action"):
                body = act.text or ""
                for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\.value\b", body):
                    ref = m.group(1)
                    if (data_types.get(ref) == "text"
                            and ref in editable
                            and not data_immediate.get(ref)):
                        out.append(Finding(
                            "warning", "button-reads-text", rel,
                            line_of(raw, f"<id>{fid}</id>"),
                            f"button '{fid}' cita textove pole '{ref}' v tom istom dataGroup, "
                            f"a '{ref}' nema immediate=\"true\" - blur a klik su jedna poziadavka, "
                            "takze akcia precita prazdno",
                            f"<data type=\"text\" immediate=\"true\"> na '{ref}'"))
                        break
    return out


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    strict = "--strict" in argv
    if not args:
        print(__doc__.strip())
        return 2

    files = []
    for a in args:
        p = Path(a)
        files.extend(sorted(p.glob("*.xml")) if p.is_dir() else [p])
    if not files:
        print("pflint: ziadne .xml na kontrolu", file=sys.stderr)
        return 2

    findings = []
    for f in files:
        findings.extend(lint(f))

    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    infos = [f for f in findings if f.level == "info"]

    for f in sorted(findings, key=lambda x: (x.path, x.line)):
        print(f.render())

    print(f"\npflint: {len(files)} sieti, {len(errors)} chyb, {len(warnings)} upozorneni, "
          f"{len(infos)} poznamok")
    if errors:
        return 1
    return 1 if (strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
