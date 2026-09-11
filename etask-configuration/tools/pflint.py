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
#   1. Oficialna XSD (petriflow.com, v1.1.0, priloz. docs/reference/petriflow.schema.xsd):
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


# Dokumentacia je v roote repozitara (etask-configuration je prikazovy priecinok).
ACTION_API = (Path(__file__).resolve().parent.parent.parent
              / "docs" / "reference" / "action-api.md")
MANIFEST = Path(__file__).resolve().parent.parent / "processes.json"

# Groovy/Java konstrukcie, ktore vyzeraju ako nahe volanie a nie su nim.
CALL_KEYWORDS = {
    "if", "for", "while", "switch", "catch", "return", "new", "def", "it",
    "assert", "throw", "synchronized", "try", "else", "instanceof", "in",
    "println", "print", "printf", "sleep", "sprintf", "use", "with", "each",
}


def delegate_methods():
    """Nazvy metod volatelnych z akcie, z generovaneho docs/reference/action-api.md.

    Ked inventar chyba, kontrola sa preskoci - hadat by znamenalo hlasit
    funkcny kod. Vygenerovat: python3 tools/pfapi.py > docs/reference/action-api.md
    """
    if not ACTION_API.is_file():
        return None
    text = ACTION_API.read_text(encoding="utf-8")
    return set(re.findall(r"^(?:- |### )`([a-zA-Z_]\w*)\(", text, re.M))


def manifest_uri_nodes():
    """Kluce `uriNodes` z processes.json, alebo None ak sa manifest neda precitat.

    None znamena "neviem" - a vtedy sa nekontroluje. Lint, ktory hlasi chybu
    preto, ze si nenasiel konfiguraciu, je horsi nez ziadny.
    """
    try:
        import json
        return set((json.loads(MANIFEST.read_text(encoding="utf-8"))
                    .get("uriNodes") or {}).keys())
    except Exception:
        return None


def close_match(name, known, max_distance=2):
    """Najblizsi znamy nazov, ak je dost blizko. Levenshtein bez zavislosti."""
    best, best_d = None, max_distance + 1
    for candidate in known:
        if abs(len(candidate) - len(name)) > max_distance:
            continue
        prev = list(range(len(candidate) + 1))
        for i, ch in enumerate(name, 1):
            cur = [i]
            for j, cch in enumerate(candidate, 1):
                cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                               prev[j - 1] + (ch != cch)))
            prev = cur
        if prev[-1] < best_d:
            best, best_d = candidate, prev[-1]
    return best if best_d <= max_distance else None


def strip_strings(body):
    """Vymaze obsah retazcovych literalov.

    Bez tohto `"Odoslane parametre (bez obsahu)"` vypada ako volanie
    `parametre(...)`. Slovensky text so slovom a zavorkou je bezny, takze
    kontrola volani sa bez tohto neda pouzit.
    """
    body = re.sub(r'"""(?:[^"\\]|\\.|"(?!""))*"""', '""', body, flags=re.S)
    body = re.sub(r"\'\'\'(?:[^'\\]|\\.|'(?!''))*\'\'\'", "''", body, flags=re.S)
    body = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', body)
    body = re.sub(r"'(?:[^'\\\n]|\\.)*'", "''", body)
    return body


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
    rel = str(path)
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        return [Finding("error", "unreadable", rel, 1, f"subor sa neda precitat: {e.strerror}")]

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return [Finding("error", "xml", rel, getattr(e, "lineno", 1),
                        f"XML sa neda rozparsovat: {e}")]

    # ---- inventar -------------------------------------------------------
    data_els = direct(root, "data")
    data_types, data_immediate = {}, {}
    typing_saved = set()
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
        # `saveWhileTyping` uklada pole uz pri pisani, takze race medzi blur
        # a klikom na tlacidlo (pravidlo `button-reads-text` nizsie) tam nie je.
        for prop in d.iter("property"):
            if (prop.get("key") or "").strip() == "saveWhileTyping" \
                    and (prop.text or "").strip() == "true":
                typing_saved.add(fid)

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
    # ---- 3a. dve polia na tom istom miesto v gride -----------------------
    #
    # Engine to prijme, `pfcheck` prejde a v appke sa uloha uz NIKDY nevykresli:
    # Angular grid vyhodi
    #     "Cannot place element X into the grid layout, because it's space
    #      (x, y) is already occupied by another element (Y)"
    # a formular zostane na nekonecnom spinneri. Chyba je len v konzole
    # prehliadaca, takze zvonku to vyzera na zaseknuty server.
    #
    # Najcastejsie takto vznikne to, ze niekto zvysi `rows` jedneho pola
    # (aby dlhy text netiekol) a nepohne tym, co je pod nim.
    for tid, t in transitions.items():
        for dg in findall(t, "dataGroup"):
            gid = child_text(dg, "id") or "?"
            cols_limit = child_text(dg, "cols")
            occupied = {}
            for dr in findall(dg, "dataRef"):
                fid = child_text(dr, "id")
                # `direct` vracia ZOZNAM - nie prvok. Bez tohto rozbalenia
                # `child_text` hlada <x> medzi <layout> a vracia None, takze
                # kontrola nizsie nikdy nic nenajde a tvari sa, ze je vsetko
                # v poriadku. Presne to sa mi stalo pri pisani tohto pravidla.
                layouts = direct(dr, "layout")
                layout = layouts[0] if layouts else None
                if not fid or layout is None:
                    continue

                def num(name, default=None):
                    raw_val = child_text(layout, name)
                    try:
                        return int(raw_val)
                    except (TypeError, ValueError):
                        return default

                x, y = num("x"), num("y")
                rows, cols = num("rows", 1), num("cols", 1)
                if x is None or y is None:
                    continue
                if cols_limit:
                    try:
                        if x + cols > int(cols_limit):
                            out.append(Finding(
                                "warning", "grid-overflow", rel,
                                line_of(raw, f"<id>{fid}</id>"),
                                f"'{fid}' v '{gid}' konci na x={x + cols}, "
                                f"ale skupina ma cols={cols_limit}",
                                "prebytok grid utne alebo zabali - skontroluj sirku"))
                    except ValueError:
                        pass
                for yy in range(y, y + max(rows, 1)):
                    for xx in range(x, x + max(cols, 1)):
                        other = occupied.get((yy, xx))
                        if other and other != fid:
                            out.append(Finding(
                                "error", "grid-overlap", rel,
                                line_of(raw, f"<id>{fid}</id>"),
                                f"'{fid}' a '{other}' sa v '{gid}' prekryvaju "
                                f"na (x={xx}, y={yy})",
                                "Angular grid ulohu NEVYKRESLI a zostane na spinneri - "
                                "chyba je len v konzole prehliadaca. Posun to, co je nizsie, "
                                "alebo zmensi `rows`"))
                            occupied[(yy, xx)] = fid
                            break
                        occupied[(yy, xx)] = fid

    action_text = " ".join(strip_comments(a.text or "") for a in findall(root, "action"))
    for fid in data_types:
        if fid not in referenced and not re.search(r"\b" + re.escape(fid) + r"\b", action_text):
            out.append(Finding("info", "data-unused", rel, line_of(raw, f"<id>{fid}</id>"),
                               f"pole '{fid}' nie je v ziadnom dataGroup ani v akcii tejto siete",
                               "moze byt v poriadku - hodnotu mu vie zapisat ina siet cez "
                               "setData(transition, case, map); inak je to mrtve pole"))

    # ---- 3b. pole, ktore siet zapisuje, ale nie je v ziadnom dataGroup ---
    # `GET /api/task/{id}/data` vracia LEN polia z dataGroup - aj skryte. Pole,
    # do ktoreho si siet sama pise a ktore v ziadnom dataGroup nie je, teda
    # neuvidi ani test, ani nikto, kto sa pripadu pyta cez API. Stalo to jedno
    # ladenie: akumulator rol vyzeral prazdny, hoci v nom data boli.
    for fid in data_types:
        if fid in referenced:
            continue
        if re.search(r"\bchange\s+" + re.escape(fid) + r"\s+(value|options|choices)\b",
                     action_text):
            out.append(Finding("info", "data-written-not-in-group", rel,
                               line_of(raw, f"<id>{fid}</id>"),
                               f"pole '{fid}' siet zapisuje, ale nie je v ziadnom dataGroup",
                               "cez API sa precitat NEDA - GET /api/task/{id}/data vracia len "
                               "polia z dataGroup, aj skryte. Na cisto vnutorny stav je to "
                               "v poriadku; ked ho ma niekto vidiet alebo testovat, pridaj "
                               "dataRef s <behavior>hidden</behavior>"))

    # ---- 3c. bodka alebo dolar v kluci moznosti --------------------------
    # Moznosti sa ukladaju ako Mongo dokument a Mongo v nazvoch poli zakazuje
    # bodku aj dolar. Plati to na staticke `<option key>` aj na kluce nastavene
    # za behu (`change X options { ... }`) - tie druhe staticky neuvidime, preto
    # je v hlaske aj pripomienka. (petriflow_reference.md, C17.)
    for d in data_els:
        fid = child_text(d, "id") or "?"
        for opts in findall(d, "options"):
            for opt in findall(opts, "option"):
                key = opt.get("key") or ""
                bad = [ch for ch in (".", "$") if ch in key]
                if bad:
                    out.append(Finding("error", "option-key-mongo", rel,
                                       line_of(raw, f'key="{key}"'),
                                       f"'{fid}': kluc moznosti '{key}' obsahuje {' a '.join(bad)}",
                                       "Mongo to v nazve pola zakazuje, ulozenie spadne na "
                                       "\"Map key ... contains dots\" - pouzi slug (napr. 1_0_0)"))

    # ---- 3d. `removeRole` z akcie v 6.3.1 nefunguje ----------------------
    # `AbstractUserService.removeRole(IUser, String roleStringId)` hlada rolu
    # cez `findByImportId`, teda podla importId, hoci parameter je stringId.
    # Nenajde nic, neodoberie nic, ulozi nezmeneny dokument - bez chyby a bez
    # logu. (PETRIFLOW_LEARNINGS.md B18, ENGINE_ISSUES.md E1.)
    for a in findall(root, "action"):
        body = strip_comments(strip_strings(a.text or ""))
        if re.search(r"\bremoveRole\s*\(", body):
            out.append(Finding("error", "engine-remove-role", rel,
                               line_of(raw, "removeRole"),
                               "volanie `removeRole(...)` rolu NEODOBERIE (engine 6.3.1) a mlci",
                               "pouzi `setProcessRole(userId, importId, siet, verzia, false)`"))

    # ---- 3e. URI cesta polozky menu vs. uriNodes v manifeste -------------
    # Karta v menu vznika z `uriNodes` v processes.json. Polozka postavena pod
    # inou cestou existuje, ale nema kartu, na ktorej by sa zobrazila - a nikde
    # sa to neohlasi: bootstrap case hlasi uspech a polozka je cez REST
    # v poriadku. Presne toto stalo jeden cyklus po premenovani appky.
    nodes = manifest_uri_nodes()
    if nodes:
        # POZOR NA PORADIE ARGUMENTOV, lisi sa medzi tymi dvomi funkciami:
        #   createOrUpdateMenuItem(id, uri, type, query, ...)   -> uri je DRUHE
        #   createFilterInMenu(uri, id, nazov, query, ...)      -> uri je PRVE
        # Prvá verzia tohto pravidla brala prvý literál a na
        # `createOrUpdateMenuItem` teda kontrolovala identifikátor položky.
        # Odpoveď vyšla správne len náhodou.
        for fn, idx in (("createOrUpdateMenuItem", 1), ("createFilterInMenu", 0)):
            for a in findall(root, "action"):
                body = strip_comments(a.text or "")
                for m in re.finditer(re.escape(fn) + r"\s*\(([^)]{0,400})", body):
                    # Pocitaju sa ARGUMENTY, nie literaly.
                    #
                    # Povodne sa bral n-ty literal, takze volanie, ktore ma id
                    # v premennej (`createOrUpdateMenuItem(podanie, "it/service_desk",
                    # "Case", ...)`) posunulo poradie a pravidlo hlasilo ako URI
                    # retazec "Case". Ked argument na danom mieste nie je literal,
                    # kontrola sa PRESKOCI - tvrdit nieco o hodnote, ktoru nevidime,
                    # je horsie nez netvrdit nic.
                    args, depth, current = [], 0, ""
                    for ch in m.group(1):
                        if ch in "([{":
                            depth += 1
                        elif ch in ")]}":
                            depth -= 1
                        if ch == "," and depth == 0:
                            args.append(current.strip())
                            current = ""
                        else:
                            current += ch
                    args.append(current.strip())
                    if len(args) <= idx:
                        continue
                    lit = re.fullmatch(r'"([^"\n]*)"', args[idx])
                    if not lit:
                        continue
                    uri = lit.group(1)
                    if not uri or uri in nodes:
                        continue
                    out.append(Finding("warning", "menu-uri-unknown", rel,
                                       line_of(raw, '"%s"' % uri),
                                       f"{fn}: URI cesta '{uri}' nie je medzi `uriNodes` "
                                       f"v processes.json",
                                       f"polozka menu vznikne, ale nebude mat kartu, na ktorej "
                                       f"by bola vidno; zname uzly: {', '.join(sorted(nodes))}"))

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

    # ---- 7. volania, ktore sa nedaju rozresit ---------------------------
    # Delegat je DYNAMICKY: preklep v nazve metody prejde parserom aj importom
    # a spadne az za behu, ked akciu niekto spusti. Nahe volanie (bez tecky
    # pred nim) moze byt len metoda delegata, procesna funkcia tejto siete,
    # alebo lokalna closure - takze zvysok je podozrivy.
    api = delegate_methods()
    if api:
        net_functions = {f.get("name") for f in findall(root, "function") if f.get("name")}
        for aid, body in action_bodies:
            where = f'<action id="{aid}"' if aid else "<action"
            ln = line_of(raw, where)
            code = strip_strings(body)
            local = set(re.findall(r"\bdef\s+([a-zA-Z_]\w*)\s*=", code))
            local |= set(re.findall(r"\b([a-zA-Z_]\w*)\s*=\s*\{", code))
            for m in re.finditer(r"(?<![.\w$])([a-z][A-Za-z0-9_]*)\s*\(", code):
                name = m.group(1)
                if (name in CALL_KEYWORDS or name in api
                        or name in net_functions or name in local
                        or name in data_types):
                    continue
                suggestion = close_match(name, api)
                if suggestion:
                    out.append(Finding("error", "unknown-call-typo", rel, ln,
                                       f"volanie `{name}(...)` nie je ani metoda delegata, ani funkcia "
                                       f"tejto siete - vyzera ako preklep",
                                       f"mysleny bol `{suggestion}(...)`? Delegat je dynamicky, "
                                       "takze toto spadne az za behu"))
                else:
                    out.append(Finding("info", "unknown-call", rel, ln,
                                       f"volanie `{name}(...)` sa neda rozresit",
                                       "ak je to metoda delegata, aktualizuj inventar: "
                                       "python3 tools/pfapi.py > docs/reference/action-api.md"))

    # ---- 8. button cita textove pole v tej istej poziadavke (B2) --------
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
                            and not data_immediate.get(ref)
                            and ref not in typing_saved):
                        out.append(Finding(
                            "warning", "button-reads-text", rel,
                            line_of(raw, f"<id>{fid}</id>"),
                            f"button '{fid}' cita textove pole '{ref}' v tom istom dataGroup, "
                            f"a '{ref}' sa uklada az na blur - blur a klik su jedna "
                            "poziadavka, takze akcia precita hodnotu z pred pisania",
                            f"<property key=\"saveWhileTyping\">true</property> na '{ref}' "
                            f"- pole sa uklada pocas pisania (RUNBOOK 6)"))
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
