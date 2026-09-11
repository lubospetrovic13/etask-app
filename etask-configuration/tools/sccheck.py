#!/usr/bin/env python3
"""
sccheck - akceptacny test appky Schvalovanie faktur a objednavok proti
BEZIACEMU enginu.

Preco to existuje samostatne od pflint/pfgroovy/pfcheck:

  pflint a pfgroovy citaju XML. pfcheck overi, ze siet engine PRIJME. Ani jeden
  z nich nepovie, ci appka robi to, co ma - ci sa faktura nad limit naozaj
  dostane riaditelovi, ci ju smie schvalit ten, kto ju zapisal, a ci sa
  "zauctovane" da odklikat bez cisla dokladu. To sa da zistit iba tak, ze sa
  cely priebeh preklika cez API.

Veci, na ktore sa v tomto repozitari naletelo a preto su tu napisane:

  1. Telo `POST /api/task/{id}/data` je {taskId: {fieldId: {...}}}, NIE
     {fieldId: {...}}. Ploche telo vrati HTTP 200 a ticho nezapise nic.
  2. Engine odmietnutie NEHLASI HTTP kodom. `finish` ani `assign` na ulohe,
     ktoru zablokuje akcia v phase="pre", nevrati chybovy status - vrati
     HTTP 200 a dovod da do tela ako `error`. Test na status taky blok
     prehliadne, a prave na tom stoji cela kontrola styroch oci.
  3. `GET /api/task/case/{id}` NEFILTRUJE podla opravneni - vrati vsetky ulohy
     casu kazdemu, kto pozna id. Zoznamy v UI stavia `POST /api/task/search`,
     ktory filtruje. Preto `tasks_of` pouziva /search a `tasks_raw` to druhe.
  4. `GET /api/auth/login` vrati 405, ale token uz je v hlavicke -
     autentifikacny filter bezi pred handlerom.
  5. Bez hlavicky `Accept-Language: zz` pouzije Spring locale JVM (tu `en`)
     a test porovnava slovenske ocakavania s anglickymi odpovedami.

Predpoklad: bezi stack (tools/up.sh), siete su naimportovane (tools/pfcheck.sh
alebo pfsync --sync) a role pridelene (tools/pfseed.py). Bootstrap case menu
zaklada runtime pri starte; ked bezi engine, ktory ho este nevidel, test si ho
zalozi sam a povie to.

    python3 tools/sccheck.py
    python3 tools/sccheck.py --wipe      # zmaze casy appky (zmes starych verzii)
    PF_URL=http://host:8080 ETASK_TEST_PASSWORD=xyz python3 tools/sccheck.py

Test ZAKLADA CASY - nespustat proti produkcii.

Exit 0 = vsetko preslo, 1 = nieco zlyhalo.
"""

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

URL = os.environ.get("PF_URL", "http://127.0.0.1:8080")
TEST_PASS = os.environ.get("ETASK_TEST_PASSWORD", "test1234")
SUPER_PASS = os.environ.get("PF_PASS", "password")

FAKTURA = "financie/faktury/fa_faktura"
OBJEDNAVKA = "financie/objednavky/ob_objednavka"
MENU = "financie/sc_menu"
NASTAVENIA = "admin/nastavenia/sc_nastavenia"

# Zobrazenia, ktore ma `sc_menu` postavit. Nazvy su tie, ktore vidi clovek -
# ked sa v sieti prepisu, prepisu sa aj tu, a to je zamer: nazov zobrazenia je
# sucast appky, nie detail.
VIEWS_FA = ["Došlé faktúry", "Rozpísané faktúry", "Faktúry na schválenie",
            "Na zaúčtovanie", "Uzavreté faktúry"]
VIEWS_OB = ["Objednávky", "Objednávky na schválenie", "Schválené na objednanie"]

HEADERS_FA = ("meta-title,financie/faktury/fa_faktura-fa_stav_label"
              ",financie/faktury/fa_faktura-fa_ceka_na"
              ",financie/faktury/fa_faktura-fa_dodavatel"
              ",financie/faktury/fa_faktura-fa_suma"
              ",financie/faktury/fa_faktura-fa_datum_splatnosti")
HEADERS_OB = ("meta-title,financie/objednavky/ob_objednavka-ob_stav_label"
              ",financie/objednavky/ob_objednavka-ob_ceka_na"
              ",financie/objednavky/ob_objednavka-ob_suma"
              ",financie/objednavky/ob_objednavka-ob_termin")

OK, FAIL = [], []


class Client:
    def __init__(self, email, password, lang="zz"):
        self.email = email
        # `zz` je jazyk, ktory engine NEPOZNA, takze `getTranslation` spadne na
        # `defaultValue` - teda na to, co je v XML (PETRIFLOW_LEARNINGS B24).
        # Na overenie prekladu sa pouzije `en`.
        self.lang = lang
        req = urllib.request.Request(
            URL + "/api/auth/login", method="GET",
            headers={"Authorization": "Basic " + base64.b64encode(
                f"{email}:{password}".encode()).decode()})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                self.token = r.headers.get("X-Auth-Token")
        except urllib.error.HTTPError as e:
            # 405, ale token uz je v hlavicke - filter bezi pred handlerom.
            self.token = e.headers.get("X-Auth-Token")
        if not self.token:
            sys.exit(f"sccheck: prihlasenie {email} zlyhalo")

    def call(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"X-Auth-Token": self.token,
                   # Bez hal+json vracaju HATEOAS endpointy 406.
                   "Accept": "application/hal+json, application/json;q=0.9, */*;q=0.8",
                   # Locale, ktore engine NEPOZNA => `getTranslation` spadne na
                   # `defaultValue`, teda na to, co je v XML (PETRIFLOW_LEARNINGS B24).
                   "Accept-Language": self.lang}
        if data:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(URL + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                text = r.read().decode("utf-8")
                return r.status, (json.loads(text) if text else None)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def get(self, p):
        return self.call("GET", p)

    def post(self, p, body=None):
        return self.call("POST", p, body)


def check(label, cond, detail=""):
    (OK if cond else FAIL).append(label)
    print(("  [OK]   " if cond else "  [ZLE] ") + label + ((" -- " + str(detail)) if detail else ""))


def newest_net(cl, identifier):
    st, r = cl.post("/api/petrinet/search?size=100", {"identifier": identifier})
    refs = [x for x in r["_embedded"]["petriNetReferences"] if x["identifier"] == identifier]
    if not refs:
        sys.exit(f"sccheck: siet {identifier} nie je naimportovana")
    refs.sort(key=lambda x: [int(n) for n in x["version"].split(".")])
    return refs[-1]


def new_case(cl, net_id):
    """(caseId, case). Odpoved nesie id len v texte `success` - `outcome.aCase`
    ma `_id` ako objekt, nie stringId."""
    st, r = cl.post("/api/workflow/case", {"netId": net_id, "title": None, "color": ""})
    m = re.search(r"Case with id ([0-9a-f]{24})", r.get("success", "") if isinstance(r, dict) else "")
    if not m:
        sys.exit(f"sccheck: zalozenie casu zlyhalo: {st} {str(r)[:300]}")
    st, c = cl.get(f"/api/workflow/case/{m.group(1)}")
    return m.group(1), c


def tasks_of(cl, case_id):
    """Ulohy, ktore uzivatel NAOZAJ vidi - to iste, z coho stavia zoznam UI."""
    st, r = cl.post("/api/task/search?size=100", {"case": [{"id": case_id}]})
    tl = (r.get("_embedded") or {}).get("tasks", []) if isinstance(r, dict) else []
    return {t["transitionId"]: t["stringId"] for t in tl}


def tasks_raw(cl, case_id):
    """Vsetky ulohy casu, nefiltrovane - na overenie, ze `assign` odmietne."""
    st, r = cl.get(f"/api/task/case/{case_id}")
    return {t["transitionId"]: t["stringId"] for t in (r or [])} if isinstance(r, list) else {}


def fields(cl, task_id):
    st, d = cl.get(f"/api/task/{task_id}/data")
    groups = (d.get("data") or d.get("outcome", {}).get("data") or []) if isinstance(d, dict) else []
    out = {}
    for grp in groups:
        for _, lst in grp.get("fields", {}).get("_embedded", {}).items():
            for f in lst:
                out[f["stringId"]] = f.get("value")
    return out


def options(cl, task_id, field_id):
    st, d = cl.get(f"/api/task/{task_id}/data")
    groups = (d.get("data") or d.get("outcome", {}).get("data") or []) if isinstance(d, dict) else []
    for grp in groups:
        for _, lst in grp.get("fields", {}).get("_embedded", {}).items():
            for f in lst:
                if f["stringId"] == field_id:
                    return list((f.get("options") or {}).keys())
    return []


def assign(cl, task_id):
    """(status, telo). Odmietnutie z akcie v `assign` prichadza ako HTTP 200
    s `error` v tele, nie ako chybovy status."""
    return cl.get(f"/api/task/assign/{task_id}")


def upload(cl, task_id, field_id, file_name, content):
    """Nahra subor do `file` pola. Telo je multipart s dvoma castami: `file`
    a `data` - presne to, co posiela frontend.

    POZOR na obsah `data`: je to mapa {taskId: fieldId}, nie prazdny objekt.
    S `{}` engine spadne na NullPointerException v `getMainOutcome`, ale
    klientovi vrati HTTP 200 s prazdnym telom - subor sa neulozi a nikde sa to
    nedozvies. Stalo sa to pri pisani tohto testu."""
    cl.get(f"/api/task/assign/{task_id}")
    boundary = "----sccheck7d91"
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += (f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
             f"Content-Type: application/octet-stream\r\n\r\n").encode()
    body += content + b"\r\n"
    body += f"--{boundary}\r\n".encode()
    body += ('Content-Disposition: form-data; name="data"\r\n'
             "Content-Type: application/json\r\n\r\n").encode()
    body += json.dumps({task_id: field_id}).encode() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        URL + f"/api/task/{task_id}/file/{field_id}", data=body, method="POST",
        headers={"X-Auth-Token": cl.token,
                 "Accept": "application/hal+json, application/json;q=0.9, */*;q=0.8",
                 "Accept-Language": "zz",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8")
            return r.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def text_pdf(lines):
    """Najmensie platne PDF s textovou vrstvou. Vyrabame ho tu a nie ako binarny
    fixture v gite: takto je v teste vidno, co presne v tom PDF stoji, a da sa
    to zmenit bez binarneho diffu.

    Zamerne BEZ diakritiky - Helvetica vo WinAnsi ju nema a bola by to
    nechcena skuska encodingu namiesto skusky citania. Popisky bez diakritiky
    su pritom presne to, co vrati OCR, takze sa tym overi aj `deaccent`."""
    content = "BT /F1 11 Tf 40 800 Td 14 TL\n"
    for line in lines:
        esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content += f"({esc}) Tj T*\n"
    content += "ET"
    cstream = content.encode("latin-1", "replace")

    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]"
        b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>",
        b"<</Length " + str(len(cstream)).encode() + b">>\nstream\n" + cstream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += (b"trailer\n<</Size " + str(len(objs) + 1).encode() + b"/Root 1 0 R>>\nstartxref\n"
            + str(xref_at).encode() + b"\n%%EOF\n")
    return out


def tiny_png():
    """1x1 biely PNG - staci na overenie, ze obrazok ide cestou OCR."""
    import struct
    import zlib

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\xff\xff")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def set_data(cl, task_id, values):
    """Telo je {taskId: {fieldId: {...}}}, nie {fieldId: {...}} - viz hlavicka."""
    cl.get(f"/api/task/assign/{task_id}")
    return cl.post(f"/api/task/{task_id}/data", {task_id: values})


def finish(cl, task_id):
    return cl.get(f"/api/task/finish/{task_id}")


def ok_body(r):
    return isinstance(r, dict) and "success" in r


def err_body(r):
    return isinstance(r, dict) and "error" in r


def as_date(value):
    """`date` pole sa cez REST vracia ako [rok, mesiac, den], nie ako retazec.
    Test, ktory porovnava s "2026-09-15", by preto zlyhal na spravnej hodnote."""
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return "%04d-%02d-%02d" % (value[0], value[1], value[2])
    return str(value or "")


PREHLADY = ("t_fa_prehlad", "t_ob_prehlad")


def bez_prehladu(tasks):
    """Ulohy bez stavoveho pohladu, utriedene.

    `t_fa_prehlad` / `t_ob_prehlad` su read-only pohlady na read arcu z miesta,
    ktore ma zeton cely zivot pripadu - su teda povolene VZDY a vidi ich kazdy,
    kto ma na pripad `view`. Kontroly typu "kto ma teraz co robit" ich preto
    musia odfiltrovat, inak by merali "kolko obrazoviek clovek vidi" namiesto
    "kolko roboty ma".

    Ze ten pohlad naozaj JE, sa overuje zvlast - je to funkcia, nie sum.
    """
    return sorted(t for t in (tasks or {}) if t not in PREHLADY)


def uri_node(cl, cesta):
    """URI uzol podla cesty. Id je z ELASTICU, nie z Monga - preto sa meni pri
    kazdej vymene indexu, kym polozky menu v Mongu drzia stare."""
    st, n = cl.get("/api/v2/uri/" + base64.b64encode(cesta.encode()).decode())
    return n if isinstance(n, dict) else None


MAILPIT = os.environ.get("PF_MAILPIT", "http://localhost:8025")


def mailpit_count():
    """Kolko mailov Mailpit zachytil, alebo None ked nebezi.

    Mailpit je SMTP server z compose stacku - maily nikam neposiela a ma na ne
    REST API. Bez neho sa notifikacie overit nedaju (lokalny beh bez Dockera),
    preto None a nie zlyhanie: appka je spravna aj tam, len sa to nema kde
    zmerat.
    """
    try:
        req = urllib.request.Request(MAILPIT + "/api/v1/messages")
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d.get("messages_count", d.get("total", 0))
    except Exception:
        return None


def mailpit_subjects(limit=10):
    try:
        req = urllib.request.Request(MAILPIT + "/api/v1/messages?limit=%d" % limit)
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read().decode("utf-8"))
        return [m.get("Subject") for m in (d.get("messages") or [])]
    except Exception:
        return []


def stav_of(cl, case_id, field):
    """Kod stavu pripadu.

    Stav je `enumeration_map` (aby sa dal prelozit), takze hodnota je KLUC -
    "zauctovana", nie "Zaúčtovaná". A nie je v nazve pripadu: `Case.title` je
    v engine `String`, ktory sa prelozit neda, takze stav nesie pole a stlpec.
    """
    st, c = cl.get(f"/api/workflow/case/{case_id}")
    for d in ((c or {}).get("immediateData") or []):
        if d.get("importId") == field:
            v = d.get("value")
            if isinstance(v, list):
                return v[0] if v else ""
            return v or ""
    return ""


def title_of(cl, case_id):
    st, c = cl.get(f"/api/workflow/case/{case_id}")
    return (c or {}).get("title", "") if isinstance(c, dict) else ""


def color_of(cl, case_id):
    st, c = cl.get(f"/api/workflow/case/{case_id}")
    return (c or {}).get("color") if isinstance(c, dict) else None


def stale_cases(cl, ident, net):
    """Casy, ktore nebezia na najnovsej verzii siete.

    `POST /api/workflow/case/search` pole `version` NEVRACIA (je None), takze
    porovnanie podla nej je vzdy prazdne - presne tak sa tu roky hlasilo
    "na starsej verzii 0". Case ale nesie `petriNetId`, teda stringId TEJ
    verzie, z ktorej vznikol; to porovnat ide."""
    st, r = cl.post("/api/workflow/case/search?size=500", {"process": [{"identifier": ident}]})
    out = []
    for c in (r.get("_embedded") or {}).get("cases", []):
        st, full = cl.get(f"/api/workflow/case/{c['stringId']}")
        if isinstance(full, dict) and full.get("petriNetId") not in (None, net["stringId"]):
            out.append(c)
    return out


def wipe(cl):
    """Zmaze casy oboch sieti appky. Case si drzi verziu siete, v ktorej
    vznikol, takze po viacerych re-importoch je v databaze zmes modelov."""
    # Aj stare identifikatory: appka sa presunula do priecinkov
    # (`schvalovanie/fa_faktura` -> `financie/faktury/fa_faktura`), takze
    # casy pod starym identifikatorom uz do ziadneho zobrazenia nepatria
    # a v databaze by zostali navzdy.
    for ident in (FAKTURA, OBJEDNAVKA,
                  "schvalovanie/fa_faktura", "schvalovanie/ob_objednavka",
                  "schvalovanie/faktury/fa_faktura",
                  "schvalovanie/objednavky/ob_objednavka"):
        st, r = cl.post("/api/workflow/case/search?size=500", {"process": [{"identifier": ident}]})
        cases = (r.get("_embedded") or {}).get("cases", [])
        for c in cases:
            cl.call("DELETE", f"/api/workflow/case/{c['stringId']}")
        print(f"sccheck: zmazanych {len(cases)} casov {ident}")


def ensure_menu(su, menu_net):
    """Bootstrap case menu zaklada runtime pri starte (processes.json ->
    bootstrapCase, rebuildOnNewVersion). Ked bezi engine, ktory novu verziu
    siete este nevidel, zalozime ho tu - inak by test hlasil chybajuce
    zobrazenia, hoci siet je v poriadku."""
    st, r = su.post("/api/workflow/case/search?size=50", {"process": [{"identifier": MENU}]})
    cases = (r.get("_embedded") or {}).get("cases", [])
    for c in cases:
        if c.get("version") == menu_net["version"]:
            return False
    new_case(su, menu_net["stringId"])
    return True


def uri_paths_deep(cl):
    """Vsetky karty, ktore ucet vidi - vratane tych v kategoriach.

    `/api/v2/uri/root` vracia len PRIAME deti korena, a odkedy appka zije
    v kategorii (`financie/faktury`), je dietatom korena uz len `financie`.
    Test hladajuci kartu medzi detmi korena by preto zlyhal bez ohladu na to,
    ci appka funguje. Endpoint filtruje podla opravneni, takze vysledok je
    naozaj to, co ten ucet vidi.
    """
    st, root = cl.get("/api/v2/uri/root")
    fronta = [c["uriPath"] for c in (root or {}).get("children", [])]
    videne = []
    while fronta:
        path = fronta.pop(0)
        if path in videne:
            continue
        videne.append(path)
        kluc = base64.b64encode(path.encode("utf-8")).decode()
        st, node = cl.get("/api/v2/uri/" + kluc)
        fronta.extend(c["uriPath"] for c in (node or {}).get("children", []))
    return videne


def main():
    su = Client("super@netgrif.com", SUPER_PASS)

    if "--wipe" in sys.argv:
        wipe(su)
        return 0

    print("=== 1. prihlasenie ===")
    zad = Client("operator@test.local", TEST_PASS)   # zadavatel + uctovnik
    zad2 = Client("druhy@test.local", TEST_PASS)     # len zadavatel
    sch = Client("admin@test.local", TEST_PASS)      # schvalovatel + uctovnik
    riad = su                                        # riaditel
    viewer = Client("viewer@test.local", TEST_PASS)  # bez roli na sieti
    print("  operator (zadavatel+uctovnik+schv_wellness) / druhy (zadavatel)")
    print("  admin (schvalovatel+riaditel+uctovnik, ROLE_ADMIN) / super (vsetko)")
    print("  super (riaditel) / viewer (bez roli)")

    net_fa = newest_net(su, FAKTURA)
    net_ob = newest_net(su, OBJEDNAVKA)
    net_menu = newest_net(su, MENU)

    print("\n=== 2. karta v bocnom menu ===")
    # /api/v2/uri je nas filtrujuci controller; engine `/api/uri` nefiltruje.
    for name, cl, expected in [("zadavatel", zad, True), ("schvalovatel", sch, True),
                               ("riaditel", riad, True), ("bez roli", viewer, False)]:
        paths = uri_paths_deep(cl)
        check(f"{name} {'vidi' if expected else 'nevidi'} kartu 'financie'",
              ("financie" in paths) == expected, paths)
    st, node = zad.get("/api/v2/uri/" + base64.b64encode(b"financie").decode())
    check("karta ma ikonu request_quote", node.get("icon") == "request_quote", node.get("icon"))
    # Pod kartou su DVA priecinky. Uzol vznika importom siete, ktorej
    # identifikator tu cestu nesie - `financie/faktury/fa_faktura`.
    deti = {c["uriPath"]: c for c in (node.get("children") or [])}
    check("priecinok 'financie/faktury' existuje", "financie/faktury" in deti,
          sorted(deti))
    check("priecinok 'schvalovanie/objednavky' existuje",
          "financie/objednavky" in deti, sorted(deti))
    check("priecinok faktur ma vlastnu ikonu",
          (deti.get("financie/faktury") or {}).get("icon") == "receipt_long",
          (deti.get("financie/faktury") or {}).get("icon"))
    check("priecinok objednavok ma vlastnu ikonu",
          (deti.get("financie/objednavky") or {}).get("icon") == "shopping_cart",
          (deti.get("financie/objednavky") or {}).get("icon"))

    print("\n=== 3. zobrazenia pod kartou ===")
    if ensure_menu(su, net_menu):
        print("  (bootstrap case menu chybal pre tuto verziu siete - zalozeny testom)")
    st, mi = su.post("/api/workflow/case/search?size=300",
                     {"process": [{"identifier": "preference_filter_item"}]})
    items = {c["title"]: c["stringId"] for c in mi.get("_embedded", {}).get("cases", [])}
    for want in VIEWS_FA + VIEWS_OB:
        check(f"zobrazenie '{want}' existuje", want in items, sorted(items))

    # A visia na AKTUALNOM URI uzle. Toto nie je detail: URI uzly zije
    # Elasticsearch, polozky menu Mongo. Ked sa ES index vymeni (--fresh, novy
    # stroj, cisty volume v Dockeri), uzly sa vytvoria znova a s novymi id -
    # polozky v Mongu drzia stare. Frontend hlada polozky dopytom
    # `uriNodeId: <id uzla>` (UriService.getCasesOfNode), takze priecinok
    # v bocnom paneli je PRAZDNY: existuje, da sa na nom kliknut, a nic v nom
    # nie je. Ziadna chyba, ziadny log, cez API sa vsetko najde.
    for cesta, kolko, kto in (("financie/faktury", len(VIEWS_FA), "faktur"),
                              ("financie/objednavky", len(VIEWS_OB), "objednavok")):
        uzol = uri_node(su, cesta)
        check(f"uzol {cesta} existuje", bool(uzol and uzol.get("id")), uzol)
        if not (uzol and uzol.get("id")):
            continue
        st, r = su.post("/api/workflow/case/search?size=50",
                        {"uriNodeId": uzol["id"],
                         "process": [{"identifier": "preference_filter_item"}]})
        pod_uzlom = [c["title"] for c in (r.get("_embedded") or {}).get("cases", [])]
        check(f"priecinok {kto} ma pod sebou zobrazenia ({kolko})",
              len(pod_uzlom) >= kolko, pod_uzlom)

    def view_task_fields(title):
        st, tl = su.get(f"/api/task/case/{items[title]}")
        vt = [t for t in (tl or []) if t["transitionId"] == "view"]
        return fields(su, vt[0]["stringId"]) if vt else {}

    if "Došlé faktúry" in items:
        # Bez `enable_case_title = false` vyskoci pri "+" dialog na nazov pripadu
        # a nazov si vymysla clovek - hoci ho sklada `create` akcia siete.
        vf = view_task_fields("Došlé faktúry")
        check("zakladanie faktury sa nepyta na nazov pripadu",
              vf.get("enable_case_title") is False, vf.get("enable_case_title"))

    for title in VIEWS_FA:
        if title in items:
            got = view_task_fields(title).get("default_headers")
            check(f"'{title}' ma stlpce Nazov/Stav/UKohoLezi/Dodavatel/Suma/Splatnost",
                  got == HEADERS_FA, got)
    for title in VIEWS_OB:
        if title in items:
            got = view_task_fields(title).get("default_headers")
            check(f"'{title}' ma stlpce Nazov/Stav/UKohoLezi/Suma/Termin",
                  got == HEADERS_OB, got)

    # Stlpec z DATOVEHO pola sa vykresli len na zobrazeni, ktore ma ten net
    # v `allowedNets`. `CaseHeaderService` sklada ponuku stlpcov z povolenych
    # sieti a `default_headers` v nej `uniqueId` iba VYHLADA - co nenajde,
    # nechá prazdne a NIC nezaloguje. Bez tejto kontroly to vyzera v poriadku:
    # hodnota je ulozena spravne a v appke su vidno len `meta-*` stlpce.
    def allowed_nets_of(title):
        fcid = view_task_fields(title).get("filter_case_id")
        if not fcid:
            return None
        st, fc = su.get(f"/api/workflow/case/{fcid}")
        for d in (fc.get("immediateData") or []):
            if d.get("allowedNets"):
                return list(d["allowedNets"])
        return []

    for title in VIEWS_FA + VIEWS_OB:
        if title not in items:
            continue
        headers = (view_task_fields(title).get("default_headers") or "").split(",")
        need = {h.rsplit("-", 1)[0] for h in headers if h and not h.startswith("meta-")}
        have = set(allowed_nets_of(title) or [])
        check(f"'{title}' ma v allowedNets siete svojich stlpcov",
              need <= have, f"treba {sorted(need)}, ma {sorted(have)}")

    def roles_of(title):
        st, full = su.get(f"/api/workflow/case/{items[title]}")
        for d in (full.get("immediateData") or []):
            if d.get("importId") == "allowed_roles":
                return sorted((d.get("options") or {}).keys())
        return []

    if "Faktúry na schválenie" in items:
        # Case zoznam sa filtruje `view` na case, a zadavatel `view` na svoju
        # fakturu ma - bez allowed_roles by si vlastnu videl aj v tejto fronte.
        check("'Faktúry na schválenie' je obmedzene na schvalovatela a riaditela",
              roles_of("Faktúry na schválenie") ==
              [f"riaditel:{FAKTURA}", f"schvalovatel:{FAKTURA}"],
              roles_of("Faktúry na schválenie"))
    if "Na zaúčtovanie" in items:
        check("'Na zaúčtovanie' je obmedzene na uctovnika",
              roles_of("Na zaúčtovanie") == [f"uctovnik:{FAKTURA}"],
              roles_of("Na zaúčtovanie"))
    if "Došlé faktúry" in items:
        check("'Došlé faktúry' nie su obmedzene na rolu", roles_of("Došlé faktúry") == [])

    st, mc = su.post("/api/workflow/case/search?size=10", {"process": [{"identifier": MENU}]})
    mt = [c["title"] for c in mc.get("_embedded", {}).get("cases", [])]
    check("bootstrap case menu hlasi 8/8", any("8/8" in t for t in mt), mt)

    print("\n=== 4. zadavatel zapisuje fakturu do limitu ===")
    fa1, c = new_case(zad, net_fa["stringId"])
    t = tasks_of(zad, fa1)
    check("zadavatel ma PRESNE jednu ulohu (Zapisat fakturu)",
          bez_prehladu(t) == ["t_fa_zapis"], list(t))
    check("a k tomu stavovy pohlad na fakturu", "t_fa_prehlad" in t, list(t))
    check("stav rozpisanej faktury je 'koncept'", stav_of(zad, fa1, "fa_stav_label") == "koncept",
          stav_of(zad, fa1, "fa_stav_label"))
    check("nazov casu nesie dodavatela, nie stav (Case.title sa neprekladá)",
          "Došlá faktúra" not in title_of(zad, fa1), title_of(zad, fa1))
    check("farba casu je 'nic sa nedeje'", color_of(zad, fa1) == "grey", color_of(zad, fa1))
    check("schvalovatel na rozpisanej fakture nema co robit",
          bez_prehladu(tasks_of(sch, fa1)) == [], list(tasks_of(sch, fa1)))

    # Prazdne `required` polia: engine finish odmietne a dovod da do tela.
    # Priradit treba explicitne. `assignPolicy=auto` ulohu povolenu ZALOZENIM
    # CASU nepriradi (zmerane: `user: null`), takze bez tohto by `finish`
    # odmietol engine s "not assigned" a kontrola by merila nieco ine.
    st, r = assign(zad, t["t_fa_zapis"])
    check("zadavatel si rozpisanu fakturu vie priradit", ok_body(r) or st == 200,
          f"HTTP {st} {str(r)[:120]}")
    st, r = finish(zad, t["t_fa_zapis"])
    check("prazdna faktura sa poslat neda", not ok_body(r), str(r)[:140])
    check("token zostal v p_koncept", "t_fa_zapis" in tasks_of(zad, fa1))

    set_data(zad, t["t_fa_zapis"], {
        "fa_dodavatel": {"type": "text", "value": "Gastro Trade s.r.o."},
        "fa_cislo": {"type": "text", "value": "2026041"},
        "fa_suma": {"type": "number", "value": 240.50},
        "fa_datum_splatnosti": {"type": "date", "value": "2026-10-15"},
        "fa_stredisko": {"type": "enumeration_map", "value": "restauracia"},
        "fa_predmet": {"type": "text", "value": "Dodávka mäsa a mliečnych výrobkov, september."}})
    d = fields(zad, t["t_fa_zapis"])
    check("suma do limitu nehlasi upozornenie na riaditela",
          not (d.get("fa_kontrola") or ""), d.get("fa_kontrola"))
    st, r = finish(zad, t["t_fa_zapis"])
    check("faktura podana", ok_body(r), str(r)[:140])
    check("stav je 'na_schvalenie'", stav_of(zad, fa1, "fa_stav_label") == "na_schvalenie",
          stav_of(zad, fa1, "fa_stav_label"))
    check("farba casu je 'v obehu'", color_of(zad, fa1) == "blue", color_of(zad, fa1))
    check("zadavatel po podani nema co robit",
          bez_prehladu(tasks_of(zad, fa1)) == [], list(tasks_of(zad, fa1)))
    # ...ale MA kde zistit, ako to stoji. Presne toto chybalo: zadavatel po
    # podani nevidel nic a vyzeralo to, ze sa podanie nepodarilo.
    check("zadavatel po podani vidi stavovy pohlad",
          "t_fa_prehlad" in tasks_of(zad, fa1), list(tasks_of(zad, fa1)))
    ts = tasks_of(sch, fa1)
    check("schvalovatel ma PRESNE jednu ulohu (Schvalit)",
          bez_prehladu(ts) == ["t_fa_schvalenie"], list(ts))

    print("\n=== 5. cudziu fakturu iny zadavatel nevidi ===")
    st, srch = zad2.post("/api/workflow/case/search?size=100",
                         {"process": [{"identifier": FAKTURA}]})
    seen = [x["stringId"] for x in (srch.get("_embedded") or {}).get("cases", [])]
    check("iny zadavatel ju nema vo vyhladavani (odtial stavia UI zoznamy)",
          fa1 not in seen, f"{len(seen)} casov")
    check("iny zadavatel na nej nema ulohu", not tasks_of(zad2, fa1), list(tasks_of(zad2, fa1)))
    # `GET /api/task/case/{id}` opravnenia neoveruje, takze id uloh sa da ziskat
    # aj bez pristupu. Hranicou je `assign`.
    for tid in tasks_raw(zad2, fa1).values():
        st, r = assign(zad2, tid)
        check("iny zadavatel si ulohu nevie priradit", st == 403 or err_body(r),
              f"HTTP {st} {str(r)[:80]}")
    st, srch = viewer.post("/api/workflow/case/search?size=100",
                           {"process": [{"identifier": FAKTURA}]})
    check("uzivatel bez roli nevidi ziadnu fakturu",
          not (srch.get("_embedded") or {}).get("cases", []))

    print("\n=== 6. styri oci: kto fakturu zapisal, tomu sa neposle ===")
    # `operator` je zadavatel A schvalovatel strediska Wellness - presne ta
    # kombinacia rol, ktora je v hoteli s tromi uzivatelmi bezna, a ucet BEZ
    # ROLE_ADMIN, takze hranica opravneni na nom naozaj plati.
    #
    # Odkedy sa schvalovanie smeruje na stredisko, styri oci nezacinaju
    # odmietnutim, ale SMEROVANIM: zadavatel sa do `fa_schvalovatelia`
    # nedostane, takze ulohu ani neuvidi. Guard vo `finish` zostal ako druha
    # linia - zoznam sa da prepisat akciou alebo cez API.
    fa_self, _ = new_case(zad, net_fa["stringId"])
    tself = tasks_of(zad, fa_self)["t_fa_zapis"]
    set_data(zad, tself, {
        "fa_dodavatel": {"type": "text", "value": "Vlastná s.r.o."},
        "fa_cislo": {"type": "text", "value": "2026099"},
        "fa_suma": {"type": "number", "value": 120.0},
        "fa_datum_splatnosti": {"type": "date", "value": "2026-10-20"},
        "fa_stredisko": {"type": "enumeration_map", "value": "wellness"},
        "fa_predmet": {"type": "text", "value": "Vlastná faktúra na svoje stredisko."}})
    st, r = finish(zad, tself)
    check("vlastna faktura na svoje stredisko podana", ok_body(r), str(r)[:140])
    check("zadavatel ju NEMA v zozname uloh na schvalenie",
          "t_fa_schvalenie" not in tasks_of(zad, fa_self), list(tasks_of(zad, fa_self)))
    raw = tasks_raw(zad, fa_self)
    check("uloha na schvalenie vsak existuje", "t_fa_schvalenie" in raw, sorted(raw))
    st, r = assign(zad, raw["t_fa_schvalenie"])
    check("a zadavatel si ju nevie priradit", st == 403 or err_body(r),
          f"HTTP {st} {str(r)[:100]}")
    check("iny schvalovatel toho strediska ju ma",
          "t_fa_schvalenie" in tasks_of(riad, fa_self), list(tasks_of(riad, fa_self)))

    print("\n=== 7. schvalovatel vracia na doplnenie ===")
    rozh = tasks_of(sch, fa1)["t_fa_schvalenie"]
    check("select ma tri moznosti",
          sorted(options(sch, rozh, "fa_rozhodnutie")) == ["schvalit", "vratit", "zamietnut"],
          sorted(options(sch, rozh, "fa_rozhodnutie")))
    set_data(sch, rozh, {"fa_rozhodnutie": {"type": "enumeration_map", "value": "vratit"}})
    st, r = finish(sch, rozh)
    check("vratenie bez dovodu je odmietnute", err_body(r), str(r)[:160])
    check("odmietnutie povie preco", "Napíšte dôvod" in str(r), str(r)[:200])
    # Regresia na B8b: odmietnute `finish` maze ulohy povolene vstupnym miestom.
    check("odmietnute DOKONCIT nikomu neubralo ulohu",
          bez_prehladu(tasks_raw(sch, fa1)) == ["t_fa_schvalenie"],
          sorted(tasks_raw(sch, fa1)))
    # A to iste pre stavovy pohlad: ten visi na read arcu z `p_info`, ktore
    # NIKTO nekonzumuje - preto ho odmietnute DOKONCIT na inom prechode nesmie
    # zmazat (B8b je presne o tom, ze z konzumovaneho miesta by ho zmazalo).
    check("odmietnute DOKONCIT nezmazalo ani stavovy pohlad",
          "t_fa_prehlad" in tasks_raw(sch, fa1), sorted(tasks_raw(sch, fa1)))
    set_data(sch, rozh, {"fa_poznamka": {"type": "text",
                                         "value": "Chýba skan a číslo objednávky."}})
    st, r = finish(sch, rozh)
    check("vratenie preslo", ok_body(r), str(r)[:140])
    tz = tasks_of(zad, fa1)
    check("zadavatel ma zase PRESNE jednu ulohu (Zapisat fakturu)",
          bez_prehladu(tz) == ["t_fa_zapis"], list(tz))
    check("schvalovatel po vrateni nema co robit",
          bez_prehladu(tasks_of(sch, fa1)) == [], list(tasks_of(sch, fa1)))
    d = fields(zad, tz["t_fa_zapis"])
    check("stav je 'vratena'", d.get("fa_stav_label") == "vratena", d.get("fa_stav_label"))
    check("zadavatel vidi dovod priamo vo formulari", "skan" in (d.get("fa_poznamka") or ""),
          d.get("fa_poznamka"))
    check("povodne hodnoty zostali vyplnene", str(d.get("fa_suma")) in ("240.5", "240.50"),
          d.get("fa_suma"))
    check("farba casu hlasi, ze zadavatel ma nieco spravit",
          color_of(zad, fa1) == "orange", color_of(zad, fa1))

    print("\n=== 8. zadavatel doplni a poda znova, stredisko schvali ===")
    set_data(zad, tz["t_fa_zapis"], {"fa_objednavka": {"type": "text", "value": "OBJ-2026-118"}})
    st, r = finish(zad, tz["t_fa_zapis"])
    check("doplnena faktura podana znova", ok_body(r), str(r)[:140])
    rozh = tasks_of(sch, fa1)["t_fa_schvalenie"]
    set_data(sch, rozh, {"fa_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
    st, r = finish(sch, rozh)
    check("schvalenie do limitu preslo", ok_body(r), str(r)[:140])
    check("stav je 'Schvalena na zauctovanie'",
          stav_of(zad, fa1, "fa_stav_label") == "na_zauctovanie",
          stav_of(zad, fa1, "fa_stav_label"))
    check("faktura do limitu k riaditelovi NEIDE",
          "t_fa_riaditel" not in tasks_raw(su, fa1), sorted(tasks_raw(su, fa1)))
    tu = tasks_of(zad, fa1)   # operator je aj uctovnik
    check("uctovnik ma ulohu Zauctovat", bez_prehladu(tu) == ["t_fa_zauctovanie"], list(tu))

    print("\n=== 9. zauctovanie bez cisla dokladu neprejde ===")
    uct = tu["t_fa_zauctovanie"]
    set_data(zad, uct, {"fa_uctovanie": {"type": "enumeration_map", "value": "zauctovat"}})
    st, r = finish(zad, uct)
    check("zauctovanie bez cisla dokladu je odmietnute", err_body(r), str(r)[:160])
    check("odmietnutie povie preco", "číslo dokladu" in str(r), str(r)[:200])
    set_data(zad, uct, {"fa_doklad": {"type": "text", "value": "DF-2026-00412"}})
    st, r = finish(zad, uct)
    check("zauctovanie preslo", ok_body(r), str(r)[:140])
    check("stav je 'zauctovana'", stav_of(zad, fa1, "fa_stav_label") == "zauctovana",
          stav_of(zad, fa1, "fa_stav_label"))
    check("farba casu je 'hotovo'", color_of(zad, fa1) == "green", color_of(zad, fa1))
    tp = tasks_of(zad, fa1)
    check("po uzavreti je otvoreny len read-only pohlad",
          list(tp) == ["t_fa_prehlad"], list(tp))
    d = fields(zad, tp["t_fa_prehlad"])
    check("prehlad drzi, kto schvalil za stredisko",
          (d.get("fa_schvalil_stredisko") or "") != "", d.get("fa_schvalil_stredisko"))
    check("prehlad drzi cislo dokladu", d.get("fa_doklad") == "DF-2026-00412", d.get("fa_doklad"))
    check("prehlad drzi cislo objednavky", d.get("fa_objednavka") == "OBJ-2026-118",
          d.get("fa_objednavka"))
    hist = d.get("fa_historia") or ""
    check("priebeh drzi vsetky kola, nie len posledne",
          "vrátené na doplnenie" in hist and "podané znova" in hist and "zaúčtované" in hist,
          hist.replace("\n", " | ")[:300])
    check("prehlad vidi aj schvalovatel", "t_fa_prehlad" in tasks_of(sch, fa1),
          list(tasks_of(sch, fa1)))

    print("\n=== 10. faktura nad limit ide aj riaditelovi ===")
    fa2, _ = new_case(zad, net_fa["stringId"])
    t2 = tasks_of(zad, fa2)["t_fa_zapis"]
    set_data(zad, t2, {
        "fa_dodavatel": {"type": "text", "value": "Wellness Technik a.s."},
        "fa_cislo": {"type": "text", "value": "2026042"},
        "fa_suma": {"type": "number", "value": 2500.0},
        "fa_datum_splatnosti": {"type": "date", "value": "2026-11-05"},
        "fa_stredisko": {"type": "enumeration_map", "value": "wellness"},
        "fa_predmet": {"type": "text", "value": "Oprava filtrácie v bazéne."}})
    d = fields(zad, t2)
    check("suma nad limit upozorni uz pri pisani",
          "riaditeľ" in (d.get("fa_kontrola") or ""), d.get("fa_kontrola"))
    st, r = finish(zad, t2)
    check("faktura nad limit podana", ok_body(r), str(r)[:140])
    rozh2 = tasks_of(sch, fa2)["t_fa_schvalenie"]
    set_data(sch, rozh2, {"fa_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
    st, r = finish(sch, rozh2)
    check("schvalenie strediskom preslo", ok_body(r), str(r)[:140])
    check("stav je 'u_riaditela'", stav_of(zad, fa2, "fa_stav_label") == "u_riaditela",
          stav_of(zad, fa2, "fa_stav_label"))
    # `admin@test.local` je schvalovatel A riaditel (v hoteli s tromi uzivatelmi
    # bezna kombinacia), takze uloha na fakture mu nezmizne - zmizne mu tá
    # schvalovacia za stredisko a nastupi riaditelska. Kontrola preto mieri na
    # konkretny prechod, nie na "nema nic".
    check("schvalovatel uz za stredisko neschvaluje",
          "t_fa_schvalenie" not in tasks_of(sch, fa2), list(tasks_of(sch, fa2)))
    check("uctovnik ju k zauctovaniu NEDOSTAL",
          "t_fa_zauctovanie" not in tasks_raw(su, fa2), sorted(tasks_raw(su, fa2)))
    tr = tasks_of(riad, fa2)
    check("riaditel ma ulohu Schvalenie riaditelom", "t_fa_riaditel" in tr, list(tr))
    set_data(riad, tr["t_fa_riaditel"], {
        "fa_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
    st, r = finish(riad, tr["t_fa_riaditel"])
    check("schvalenie riaditelom preslo", ok_body(r), str(r)[:140])
    check("stav je 'Schvalena na zauctovanie'",
          stav_of(zad, fa2, "fa_stav_label") == "na_zauctovanie",
          stav_of(zad, fa2, "fa_stav_label"))
    tu2 = tasks_of(sch, fa2)
    check("az teraz ju ma uctovnik", bez_prehladu(tu2) == ["t_fa_zauctovanie"], list(tu2))
    set_data(sch, tu2["t_fa_zauctovanie"], {
        "fa_uctovanie": {"type": "enumeration_map", "value": "zauctovat"},
        "fa_doklad": {"type": "text", "value": "DF-2026-00413"}})
    st, r = finish(sch, tu2["t_fa_zauctovanie"])
    check("zauctovanie preslo", ok_body(r), str(r)[:140])
    d = fields(zad, tasks_of(zad, fa2)["t_fa_prehlad"])
    check("prehlad drzi obe urovne schvalenia",
          (d.get("fa_schvalil_stredisko") or "") != "" and
          (d.get("fa_schvalil_riaditel") or "") != "",
          [d.get("fa_schvalil_stredisko"), d.get("fa_schvalil_riaditel")])

    print("\n=== 11. zamietnutie faktury ===")
    fa3, _ = new_case(zad, net_fa["stringId"])
    t3 = tasks_of(zad, fa3)["t_fa_zapis"]
    set_data(zad, t3, {
        "fa_dodavatel": {"type": "text", "value": "Neznámy dodávateľ"},
        "fa_cislo": {"type": "text", "value": "2026043"},
        "fa_suma": {"type": "number", "value": 90.0},
        "fa_datum_splatnosti": {"type": "date", "value": "2026-10-30"},
        # Stredisko musi byt take, ktoreho schvalovatelom `sch` naozaj je -
        # odkedy sa schvalovanie smeruje podla strediska, faktura na `hotel` by
        # mu vobec neprisla.
        "fa_stredisko": {"type": "enumeration_map", "value": "restauracia"},
        "fa_predmet": {"type": "text", "value": "Fakturácia bez objednávky."}})
    finish(zad, t3)
    rozh3 = tasks_of(sch, fa3)["t_fa_schvalenie"]
    set_data(sch, rozh3, {
        "fa_rozhodnutie": {"type": "enumeration_map", "value": "zamietnut"},
        "fa_poznamka": {"type": "text", "value": "Nič sme si u nich neobjednali."}})
    st, r = finish(sch, rozh3)
    check("zamietnutie preslo", ok_body(r), str(r)[:140])
    check("stav je 'zamietnuta'", stav_of(zad, fa3, "fa_stav_label") == "zamietnuta",
          stav_of(zad, fa3, "fa_stav_label"))
    check("farba casu je 'zamietnute'", color_of(zad, fa3) == "red", color_of(zad, fa3))
    t3p = tasks_of(zad, fa3)
    check("zamietnuta faktura konci v prehlade, nie na zauctovani",
          list(t3p) == ["t_fa_prehlad"], list(t3p))
    d = fields(zad, t3p["t_fa_prehlad"])
    check("zadavatel vidi dovod zamietnutia",
          "neobjednali" in (d.get("fa_poznamka") or ""), d.get("fa_poznamka"))

    print("\n=== 12. objednavka do limitu, so zoznamom poziadaviek ===")
    ob1, _ = new_case(zad2, net_ob["stringId"])
    to1 = tasks_of(zad2, ob1)
    check("zadavatel ma PRESNE jednu ulohu (Poziadat o objednavku)",
          bez_prehladu(to1) == ["t_ob_ziadost"], list(to1))
    check("a k tomu stavovy pohlad na objednavku", "t_ob_prehlad" in to1, list(to1))
    ziadost = to1["t_ob_ziadost"]
    set_data(zad2, ziadost, {
        "ob_predmet": {"type": "text", "value": "Vybavenie wellness"},
        "ob_dodavatel": {"type": "text", "value": "Textil Hotel s.r.o."},
        "ob_termin": {"type": "date", "value": "2026-10-31"},
        "ob_stredisko": {"type": "enumeration_map", "value": "wellness"},
        "ob_zdovodnenie": {"type": "text", "value": "Staré sú po troch rokoch nepoužiteľné."}})

    # Bez poziadaviek nie je co objednat - `required` to nepokryje, su to riadky
    # v JSONe, nie pole na formulari.
    st, r = finish(zad2, ziadost)
    check("objednavka bez poziadaviek sa podat neda", err_body(r), str(r)[:160])
    check("odmietnutie povie preco", "aspoň jednu požiadavku" in str(r), str(r)[:200])

    # Pridanie poziadavky: hodnoty do riadku a stlacenie buttonu. Button sa
    # "stlaci" zapisom hodnoty do jeho pola - je to `set` udalost.
    def pridaj(nazov, mnozstvo, jednotka, cena):
        set_data(zad2, ziadost, {
            "ob_p_nazov": {"type": "text", "value": nazov},
            "ob_p_mnozstvo": {"type": "number", "value": mnozstvo},
            "ob_p_jednotka": {"type": "text", "value": jednotka},
            "ob_p_cena": {"type": "number", "value": cena}})
        return set_data(zad2, ziadost, {"btn_ob_pridat": {"type": "button", "value": 0}})

    pridaj("Uteráky 70×140", 200, "ks", 3.50)
    d = fields(zad2, ziadost)
    check("poziadavka je v citatelnom zozname",
          "Uteráky 70×140" in (d.get("ob_polozky") or ""), d.get("ob_polozky"))
    check("suma je sucet, nie to, co niekto natypoval",
          float(d.get("ob_suma") or 0) == 700.0, d.get("ob_suma"))
    check("riadok na pridanie sa vyprazdnil", not (d.get("ob_p_nazov") or ""),
          d.get("ob_p_nazov"))

    pridaj("Župany", 40, "ks", 24.90)
    d = fields(zad2, ziadost)
    check("druha poziadavka pribudla k prvej",
          "Župany" in (d.get("ob_polozky") or "") and
          "Uteráky" in (d.get("ob_polozky") or ""), d.get("ob_polozky"))
    check("suma je 700 + 996", float(d.get("ob_suma") or 0) == 1696.0, d.get("ob_suma"))
    check("nad limit upozorni uz v zozname",
          "riaditeľ" in (d.get("ob_kontrola") or ""), d.get("ob_kontrola"))

    # Odobranie: zaskrtnut id v `ob_polozky_vyber` a stlacit druhy button.
    # Id je pocitadlo (p1, p2...), nie index - po odobrani sa nepreciluje.
    st, dd = zad2.get(f"/api/task/{ziadost}/data")
    opts = options(zad2, ziadost, "ob_polozky_vyber")
    check("kazda poziadavka ma vlastny kluc na odobranie", sorted(opts) == ["p1", "p2"], opts)
    set_data(zad2, ziadost, {"ob_polozky_vyber": {"type": "multichoice_map", "value": ["p2"]}})
    set_data(zad2, ziadost, {"btn_ob_odobrat": {"type": "button", "value": 0}})
    d = fields(zad2, ziadost)
    check("odobrana poziadavka zo zoznamu zmizla",
          "Župany" not in (d.get("ob_polozky") or ""), d.get("ob_polozky"))
    check("suma sa po odobrani vratila na 700",
          float(d.get("ob_suma") or 0) == 700.0, d.get("ob_suma"))
    check("upozornenie na riaditela zmizlo s nim", not (d.get("ob_kontrola") or ""),
          d.get("ob_kontrola"))

    pridaj("Prostěradla", 100, "ks", 0.80)
    d = fields(zad2, ziadost)
    check("suma je 700 + 80", float(d.get("ob_suma") or 0) == 780.0, d.get("ob_suma"))

    st, r = finish(zad2, ziadost)
    check("objednavka podana", ok_body(r), str(r)[:140])
    st, c = zad2.get(f"/api/workflow/case/{ob1}")
    check("stav je 'na_schvalenie'", stav_of(zad2, ob1, "ob_stav_label") == "na_schvalenie",
          stav_of(zad2, ob1, "ob_stav_label"))
    tos = tasks_of(sch, ob1)
    check("schvalovatel ma ulohu Schvalit", bez_prehladu(tos) == ["t_ob_schvalenie"], list(tos))
    ds = fields(sch, tos["t_ob_schvalenie"])
    check("schvalovatel vidi, co presne sa objednava",
          "Uteráky" in (ds.get("ob_polozky") or "") and
          "Prostěradla" in (ds.get("ob_polozky") or ""), ds.get("ob_polozky"))
    check("priebeh hlasi pocet poziadaviek aj sumu",
          "2 požiadavky za 780.00" in (ds.get("ob_historia") or ""),
          (ds.get("ob_historia") or "").replace("\n", " | ")[:200])
    set_data(sch, tos["t_ob_schvalenie"],
             {"ob_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
    st, r = finish(sch, tos["t_ob_schvalenie"])
    check("schvalenie objednavky do limitu preslo", ok_body(r), str(r)[:140])
    check("stav je 'Schvalena na objednanie'",
          stav_of(zad2, ob1, "ob_stav_label") == "na_objednanie",
          stav_of(zad2, ob1, "ob_stav_label"))
    too = tasks_of(zad2, ob1)
    check("objednava ten, kto o to poziadal",
          bez_prehladu(too) == ["t_ob_objednanie"], list(too))
    check("schvalovatel objednanie nepotvrdzuje",
          "t_ob_objednanie" not in tasks_of(sch, ob1), list(tasks_of(sch, ob1)))
    assign(zad2, too["t_ob_objednanie"])
    st, r = finish(zad2, too["t_ob_objednanie"])
    check("potvrdenie bez cisla objednavky je odmietnute", err_body(r), str(r)[:160])
    # Tu zabere najprv `required` na dataRefe a engine povie meno pola sam;
    # guard v `phase="pre"` je druha linia (drzi aj pri zapise cez API, ktory
    # formular obchadza). Kontrola je preto case-insensitive.
    check("odmietnutie povie preco", "číslo objednávky" in str(r).lower(), str(r)[:200])
    set_data(zad2, too["t_ob_objednanie"], {"ob_cislo": {"type": "text", "value": "OBJ-2026-119"}})
    st, r = finish(zad2, too["t_ob_objednanie"])
    check("objednanie potvrdene", ok_body(r), str(r)[:140])
    check("stav je 'objednana'", stav_of(zad2, ob1, "ob_stav_label") == "objednana",
          stav_of(zad2, ob1, "ob_stav_label"))
    top = tasks_of(zad2, ob1)
    check("po uzavreti je otvoreny len read-only pohlad",
          list(top) == ["t_ob_prehlad"], list(top))
    d = fields(zad2, top["t_ob_prehlad"])
    check("prehlad drzi cislo objednavky, na ktore sa odvola faktura",
          d.get("ob_cislo") == "OBJ-2026-119", d.get("ob_cislo"))
    check("prehlad drzi, kto objednal", (d.get("ob_objednal") or "") != "",
          d.get("ob_objednal"))

    print("\n=== 13. objednavka nad limit ide aj riaditelovi ===")
    ob2, _ = new_case(zad2, net_ob["stringId"])
    to2 = tasks_of(zad2, ob2)["t_ob_ziadost"]
    set_data(zad2, to2, {
        "ob_predmet": {"type": "text", "value": "Konvektomat do kuchyne"},
        "ob_stredisko": {"type": "enumeration_map", "value": "restauracia"},
        "ob_zdovodnenie": {"type": "text", "value": "Súčasný je 12 rokov starý a dvakrát ročne sa kazí."}})
    set_data(zad2, to2, {
        "ob_p_nazov": {"type": "text", "value": "Konvektomat 10× GN 1/1"},
        "ob_p_mnozstvo": {"type": "number", "value": 1},
        "ob_p_jednotka": {"type": "text", "value": "ks"},
        "ob_p_cena": {"type": "number", "value": 6400.0}})
    set_data(zad2, to2, {"btn_ob_pridat": {"type": "button", "value": 0}})
    check("smerovanie riadi SUCET poziadaviek, nie natypovana suma",
          float(fields(zad2, to2).get("ob_suma") or 0) == 6400.0,
          fields(zad2, to2).get("ob_suma"))
    st, r = finish(zad2, to2)
    check("objednavka nad limit podana", ok_body(r), str(r)[:140])
    tos2 = tasks_of(sch, ob2)["t_ob_schvalenie"]
    set_data(sch, tos2, {"ob_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
    st, r = finish(sch, tos2)
    check("schvalenie strediskom preslo", ok_body(r), str(r)[:140])
    check("stav je 'u_riaditela'", stav_of(zad2, ob2, "ob_stav_label") == "u_riaditela",
          stav_of(zad2, ob2, "ob_stav_label"))
    check("objednanie sa este nepovolilo",
          "t_ob_objednanie" not in tasks_raw(su, ob2), sorted(tasks_raw(su, ob2)))
    tor = tasks_of(riad, ob2)
    check("riaditel ma ulohu Schvalenie riaditelom", "t_ob_riaditel" in tor, list(tor))
    set_data(riad, tor["t_ob_riaditel"],
             {"ob_rozhodnutie": {"type": "enumeration_map", "value": "zamietnut"},
              "ob_poznamka": {"type": "text", "value": "Do rozpočtu tohto roka sa to nevojde."}})
    st, r = finish(riad, tor["t_ob_riaditel"])
    check("zamietnutie riaditelom preslo", ok_body(r), str(r)[:140])
    check("stav je 'zamietnuta'", stav_of(zad2, ob2, "ob_stav_label") == "zamietnuta",
          stav_of(zad2, ob2, "ob_stav_label"))
    d = fields(zad2, tasks_of(zad2, ob2)["t_ob_prehlad"])
    check("zadavatel vidi dovod zamietnutia",
          "rozpočtu" in (d.get("ob_poznamka") or ""), d.get("ob_poznamka"))

    print("\n=== 14. citanie faktury z prilohy: XML e-faktura ===")
    # XML e-faktura sa CITA, nehada. Toto je cesta, ktora bude s povinnou
    # e-fakturaciou prevladat, takze je otestovana ako prva.
    fa_x, _ = new_case(zad, net_fa["stringId"])
    tx = tasks_of(zad, fa_x)["t_fa_zapis"]
    ubl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "faktura-ubl.xml")
    with open(ubl, "rb") as fh:
        st, r = upload(zad, tx, "fa_skan", "faktura-ubl.xml", fh.read())
    check("XML e-faktura sa nahrala do prilohy", st == 200 and not err_body(r),
          f"HTTP {st} {str(r)[:120]}")
    set_data(zad, tx, {"btn_fa_nacitat": {"type": "button", "value": 0}})
    d = fields(zad, tx)
    check("zdroj je oznaceny ako citany, nie hadany",
          "XML" in (d.get("fa_zdroj") or ""), d.get("fa_zdroj"))
    check("cislo faktury precitane", d.get("fa_cislo") == "2026-0457", d.get("fa_cislo"))
    check("suma precitana z PayableAmount", float(d.get("fa_suma") or 0) == 1452.60,
          d.get("fa_suma"))
    check("splatnost precitana", as_date(d.get("fa_datum_splatnosti")).startswith("2026-09-15"),
          d.get("fa_datum_splatnosti"))
    check("datum vystavenia precitany",
          as_date(d.get("fa_datum_vystavenia")).startswith("2026-09-01"),
          d.get("fa_datum_vystavenia"))
    check("dodavatel precitany", "Kaskády Gastro" in (d.get("fa_dodavatel") or ""),
          d.get("fa_dodavatel"))
    # Toto je ta pasca: `cbc:CompanyID` je v XML dvakrat - u dodavatela
    # aj u odberatela. Parser, ktory hlada po celom dokumente, vytiahne cudzie
    # IcO a nikto si toho nevsimne, lebo hodnota tam JE.
    check("IcO je dodavatelovo, nie odberatelovo", d.get("fa_ico") == "36123456",
          d.get("fa_ico"))
    check("IBAN precitany", d.get("fa_iban") == "SK3112000000198742637541", d.get("fa_iban"))
    check("suma nad limit rovno upozorni na riaditela",
          "riaditeľ" in (d.get("fa_kontrola") or ""), d.get("fa_kontrola"))
    check("vysledok nacitania povie, co doplnil",
          "Doplnené" in (d.get("fa_nacitanie") or ""), d.get("fa_nacitanie"))

    # Prectane cislo sa da poslat dalej bez toho, aby ho niekto prepisoval.
    set_data(zad, tx, {"fa_stredisko": {"type": "enumeration_map", "value": "restauracia"},
                       "fa_predmet": {"type": "text", "value": "Dodávka podľa e-faktúry."}})
    st, r = finish(zad, tx)
    check("faktura z e-faktury sa poda bez rucneho prepisovania", ok_body(r), str(r)[:140])
    check("v priebehu je zapisane, odkial udaje su",
          "údaje z: XML" in (fields(sch, tasks_of(sch, fa_x)["t_fa_schvalenie"])
                             .get("fa_historia") or ""),
          (fields(sch, tasks_of(sch, fa_x)["t_fa_schvalenie"]).get("fa_historia") or "")[:200])

    print("\n=== 15. citanie faktury z prilohy: PDF s textovou vrstvou ===")
    fa_p, _ = new_case(zad, net_fa["stringId"])
    tp = tasks_of(zad, fa_p)["t_fa_zapis"]
    pdf = text_pdf([
        "Ubytovacie sluzby s.r.o.",
        "Hlavna 5, 974 01 Banska Bystrica",
        "ICO: 44556677    IC DPH: SK2023445566",
        "",
        "FAKTURA c. 2026114",
        "",
        "Odberatel: Hotel Kaskady, s.r.o.",
        "ICO: 31999888",
        "",
        "Datum vystavenia: 2.9.2026",
        "Datum splatnosti: 16.9.2026",
        "IBAN: SK6807200002891987426353",
        "",
        "Pranie a zehlenie bielizne za august",
        "Celkom k uhrade: 342,80 EUR",
    ])
    st, r = upload(zad, tp, "fa_skan", "faktura.pdf", pdf)
    check("PDF sa nahralo do prilohy", st == 200 and not err_body(r), f"HTTP {st} {str(r)[:120]}")
    set_data(zad, tp, {"btn_fa_nacitat": {"type": "button", "value": 0}})
    d = fields(zad, tp)
    check("zdroj je textova vrstva PDF, nie OCR",
          "textová vrstva" in (d.get("fa_zdroj") or ""), d.get("fa_zdroj"))
    check("suma s desatinnou ciarkou precitana spravne",
          float(d.get("fa_suma") or 0) == 342.80, d.get("fa_suma"))
    check("cislo faktury z popisku 'FAKTURA c.'", d.get("fa_cislo") == "2026114",
          d.get("fa_cislo"))
    check("splatnost z popisku bez diakritiky",
          as_date(d.get("fa_datum_splatnosti")).startswith("2026-09-16"),
          d.get("fa_datum_splatnosti"))
    check("datum vystavenia sa nezamenil so splatnostou",
          as_date(d.get("fa_datum_vystavenia")).startswith("2026-09-02"),
          d.get("fa_datum_vystavenia"))
    check("dodavatel je z hlavicky, nie odberatel z prostriedku",
          "Ubytovacie" in (d.get("fa_dodavatel") or ""), d.get("fa_dodavatel"))
    check("IcO je dodavatelovo aj v texte", d.get("fa_ico") == "44556677", d.get("fa_ico"))
    check("IBAN precitany", d.get("fa_iban") == "SK6807200002891987426353", d.get("fa_iban"))

    # Druhe stlacenie uz nesmie nic prepisat - a rozdiel ma ohlasit.
    set_data(zad, tp, {"fa_suma": {"type": "number", "value": 300.0}})
    set_data(zad, tp, {"btn_fa_nacitat": {"type": "button", "value": 0}})
    d = fields(zad, tp)
    check("rucne prepisanu sumu nacitanie NEPREPISE", float(d.get("fa_suma") or 0) == 300.0,
          d.get("fa_suma"))
    check("rozdiel oproti prilohe ale ohlasi",
          "POZOR" in (d.get("fa_nacitanie") or "") and "342.8" in (d.get("fa_nacitanie") or ""),
          d.get("fa_nacitanie"))

    print("\n=== 16. sken bez textovej vrstvy ide na OCR ===")
    fa_o, _ = new_case(zad, net_fa["stringId"])
    to = tasks_of(zad, fa_o)["t_fa_zapis"]
    st, r = upload(zad, to, "fa_skan", "sken.png", tiny_png())
    check("obrazok sa nahral do prilohy", st == 200 and not err_body(r), f"HTTP {st} {str(r)[:120]}")
    set_data(zad, to, {"btn_fa_nacitat": {"type": "button", "value": 0}})
    d = fields(zad, to)
    sprava = d.get("fa_nacitanie") or ""
    if "nie je v PATH" in sprava:
        # Ocakavany stav na stroji bez tesseractu. Podstatne je, ze to appka
        # POVIE a nespadne - a ze povie, co s tym.
        check("bez tesseractu to appka povie zrozumitelne a nespadne",
              "OCR" in sprava and "tesseract" in sprava, sprava)
        print("  (poznamka: tesseract na tomto stroji nie je - OCR vetva sa tu")
        print("   overit neda. Po instalacii ju overi tento isty krok.)")
    else:
        check("OCR prebehlo a appka povedala zdroj",
              "OCR" in (d.get("fa_zdroj") or "") or "OCR" in sprava,
              [d.get("fa_zdroj"), sprava])

    print("\n=== 16b. zadavatel vidi stav a u koho to lezi ===")
    # Toto je kontrola presne toho, na co sa clovek pytal: podal fakturu za
    # stredisko, ktoreho je sam schvalovatelom, a nevidel ziadnu ulohu. Je to
    # spravne (styri oci ho vylucia), ale bez read-only pohladu na to nemal
    # ako prist - vyzeralo to ako porucha.
    mail_pred = mailpit_count()
    fa_s, _ = new_case(zad, net_fa["stringId"])
    ts = tasks_of(zad, fa_s)["t_fa_zapis"]
    assign(zad, ts)
    set_data(zad, ts, {
        "fa_dodavatel": {"type": "text", "value": "Stavovy Test s.r.o."},
        "fa_cislo": {"type": "text", "value": "2026400"},
        "fa_suma": {"type": "number", "value": 120.0},
        # `as_date` je CITAC ([rok, mesiac, den] -> "2026-10-25"), nie generator
        # datumu. `as_date(30)` vrati "30", engine to ulozi ako null a `finish`
        # skonci na "Field Splatnosť has null value".
        "fa_datum_splatnosti": {"type": "date", "value": "2026-10-25"},
        "fa_stredisko": {"type": "enumeration_map", "value": "wellness"},
        "fa_predmet": {"type": "text", "value": "stavovy pohlad"},
    })
    st, r = finish(zad, ts)
    check("faktura podana", not err_body(r), str(r)[:120])

    # 1. Uloha na schvalenie zadavatelovi NEPATRI (styri oci).
    st, tl = zad.post("/api/task/search?size=20", {"case": [{"id": fa_s}]})
    moje = [t["transitionId"] for t in (tl.get("_embedded") or {}).get("tasks", [])]
    check("zadavatel NEVIDI ulohu na schvalenie vlastnej faktury",
          "t_fa_schvalenie" not in moje, moje)

    # 2. Ale stavovy pohlad ANO - a to je novy prvok.
    check("zadavatel vidi stavovy pohlad t_fa_prehlad", "t_fa_prehlad" in moje, moje)

    # 3. A ten pohlad mu povie stav aj to, u koho faktura lezi. Mena, nie roly:
    #    pole je `text`, teda String, ktory sa neprekladá (RUNBOOK 9).
    if "t_fa_prehlad" in moje:
        tp = tasks_of(zad, fa_s)["t_fa_prehlad"]
        assign(zad, tp)
        dp = fields(zad, tp)
        check("stavovy pohlad ukazuje stav", dp.get("fa_stav_label") == "na_schvalenie",
              dp.get("fa_stav_label"))
        ceka = dp.get("fa_ceka_na") or ""
        check("stavovy pohlad povie, u koho to lezi", len(ceka) > 3 and ceka != "—", ceka)
        check("u koho to lezi su mena, nie rola",
              "riadite" not in ceka.lower() and "schvalovate" not in ceka.lower(), ceka)

    print("\n=== 16c. notifikacia odisla na SMTP ===")
    posta = mailpit_count()
    if posta is None:
        print("  (poznamka: Mailpit nebezi - notifikacie sa tu overit nedaju.")
        print("   V compose stacku bezi na :8025, potom ich overi tento krok.)")
    else:
        check("po podani prisiel aspon jeden mail", posta > (mail_pred or 0),
              f"{mail_pred} -> {posta}")
        predmety = mailpit_subjects()
        check("mail hovori o tej fakture",
              any("Stavovy Test" in (x or "") for x in predmety), predmety[:3])

    print("\n=== 17. tlacidla maju vlastne nazvy, nie DOKONCIT ===")
    # Titulok udalosti sa posiela klientovi (`finishTitle` a spol.) a prazdny
    # titulok tlacidlo SKRYJE - to je jediny sposob, ako z panela odobrat
    # `delegate` bez zasahu do opravneni (PETRIFLOW_LEARNINGS B23).
    fa_t, _ = new_case(zad, net_fa["stringId"])
    tt = tasks_of(zad, fa_t)["t_fa_zapis"]
    st, tl = zad.post("/api/task/search?size=20", {"case": [{"id": fa_t}]})
    task = [t for t in (tl.get("_embedded") or {}).get("tasks", [])
            if t["transitionId"] == "t_fa_zapis"][0]
    check("zapis ma na DOKONCIT vlastny nazov",
          task.get("finishTitle") == "Podať na schválenie", task.get("finishTitle"))
    check("zapis ma vlastny nazov aj na prevzatie",
          task.get("assignTitle") == "Prevziať", task.get("assignTitle"))
    check("delegovanie je skryte prazdnym titulkom",
          task.get("delegateTitle") == "", repr(task.get("delegateTitle")))
    check("zrusenie je na osobnej ulohe skryte",
          task.get("cancelTitle") == "", repr(task.get("cancelTitle")))

    print("\n=== 18. schvaluje stredisko, nie kazdy schvalovatel ===")
    # `operator` ma schv_wellness, nie schv_marketing - a nema ROLE_ADMIN,
    # takze na nom je vidno skutocnu hranicu. `druhy` je len zadavatel.
    def podaj(cl, stredisko, suma, cislo):
        cid, _ = new_case(cl, net_fa["stringId"])
        t = tasks_of(cl, cid)["t_fa_zapis"]
        set_data(cl, t, {
            "fa_dodavatel": {"type": "text", "value": "Dodávateľ " + stredisko},
            "fa_cislo": {"type": "text", "value": cislo},
            "fa_suma": {"type": "number", "value": suma},
            "fa_datum_splatnosti": {"type": "date", "value": "2026-11-30"},
            "fa_stredisko": {"type": "enumeration_map", "value": stredisko},
            "fa_predmet": {"type": "text", "value": "Test smerovania na stredisko."}})
        st, r = finish(cl, t)
        return cid, r

    fa_mkt, r = podaj(zad2, "marketing", 120.0, "2026201")
    check("faktura na marketing podana", ok_body(r), str(r)[:140])
    check("schvalovatel ineho strediska ju v ulohach nema",
          "t_fa_schvalenie" not in tasks_of(zad, fa_mkt), list(tasks_of(zad, fa_mkt)))
    st, r = assign(zad, tasks_raw(zad, fa_mkt)["t_fa_schvalenie"])
    check("a ani si ju nevie priradit", st == 403 or err_body(r),
          f"HTTP {st} {str(r)[:100]}")
    check("schvalovatel marketingu ju ma", "t_fa_schvalenie" in tasks_of(riad, fa_mkt),
          list(tasks_of(riad, fa_mkt)))

    fa_wel, r = podaj(zad2, "wellness", 130.0, "2026202")
    check("faktura na wellness podana", ok_body(r), str(r)[:140])
    check("schvalovatel wellness ju ma", "t_fa_schvalenie" in tasks_of(zad, fa_wel),
          list(tasks_of(zad, fa_wel)))
    st, r = assign(zad, tasks_of(zad, fa_wel)["t_fa_schvalenie"])
    check("a vie si ju priradit", ok_body(r) or st == 200, f"HTTP {st} {str(r)[:100]}")
    d = fields(zad, tasks_of(zad, fa_wel)["t_fa_schvalenie"])
    check("v priebehu nie je hlaska o zalozi - stredisko ma svojho schvalovatela",
          "smerovanie:" not in (d.get("fa_historia") or ""),
          (d.get("fa_historia") or "")[:160])

    print("\n=== 19. faktura na zaklade objednavky ===")
    # Objednavka z kroku 12 je uzavreta ako "Objednaná" - da sa na nu fakturovat.
    fa_ob, _ = new_case(zad, net_fa["stringId"])
    tfo = tasks_of(zad, fa_ob)["t_fa_zapis"]
    assign(zad, tfo)
    moznosti = options(zad, tfo, "fa_objednavka_vyber")
    check("vyber ponuka schvalene objednavky", ob1 in moznosti,
          f"{len(moznosti)} moznosti")
    set_data(zad, tfo, {"fa_suma": {"type": "number", "value": 900.0}})
    set_data(zad, tfo, {"fa_objednavka_vyber": {"type": "enumeration_map", "value": ob1}})
    d = fields(zad, tfo)
    check("cislo objednavky sa doplnilo z nej", d.get("fa_objednavka") == "OBJ-2026-119",
          d.get("fa_objednavka"))
    check("dodavatel sa doplnil z objednavky",
          "Textil Hotel" in (d.get("fa_dodavatel") or ""), d.get("fa_dodavatel"))
    check("appka upozorni, ze faktura je vyssia nez objednavka",
          "viac" in (d.get("fa_objednavka_info") or ""), d.get("fa_objednavka_info"))
    check("v informacii je aj objednana suma",
          "780.00" in (d.get("fa_objednavka_info") or ""), d.get("fa_objednavka_info"))

    print("\n=== 20. konfiguracia: limit a schvalovatelia z appky ===")
    # Karta konfiguracie ma v `uriNodes` ROLE_ADMIN, takze ju nevidi ani
    # zadavatel, ani schvalovatel bez tej autority.
    for name, cl, expected in [("spravca (super)", riad, True),
                               ("zadavatel", zad2, False),
                               ("bez roli", viewer, False)]:
        paths = uri_paths_deep(cl)
        check(f"kartu 'admin/nastavenia' {name} {'vidi' if expected else 'nevidi'}",
              ("admin/nastavenia" in paths) == expected, paths)

    st, mi = riad.post("/api/workflow/case/search?size=300",
                       {"process": [{"identifier": "preference_filter_item"}]})
    items = {c["title"]: c["stringId"] for c in mi.get("_embedded", {}).get("cases", [])}
    check("zobrazenie 'Konfigurácia schvaľovania' existuje",
          "Konfigurácia schvaľovania" in items, sorted(items)[:6])

    # Case musi existovat pre NAJNOVSIU verziu siete, nie "nejaky".
    #
    # Preco takto presne: `bootstrapCase` s `rebuildOnNewVersion` zaklada case
    # per verziu a akcia v jeho `create` udalosti raz spadla (delegat porovnaval
    # verzie ako ArrayList). Case pre starsiu verziu pritom existoval, takze
    # kontrola "existuje nejaky" presla - a konfiguracia v appke nebola.
    net_cfg = newest_net(riad, NASTAVENIA)
    st, cfgs = riad.post("/api/workflow/case/search?size=50",
                         {"process": [{"identifier": NASTAVENIA}]})
    cfg_cases = (cfgs.get("_embedded") or {}).get("cases", [])
    najnovsie = []
    for c in cfg_cases:
        st, full = riad.get(f"/api/workflow/case/{c['stringId']}")
        if isinstance(full, dict) and full.get("petriNetId") == net_cfg["stringId"]:
            najnovsie.append(c)
    check(f"konfiguracny case existuje pre najnovsiu verziu (v{net_cfg['version']})",
          len(najnovsie) >= 1, f"{len(cfg_cases)} casov, z nich {len(najnovsie)} z najnovsej")
    cfg_id = najnovsie[-1]["stringId"] if najnovsie else None

    # A zobrazenie v menu ho musi NAJST. Toto je kontrola, ktora chybala:
    # polozka menu existovala, ale jej dopyt bol postaveny na `processIdentifier`,
    # ktore task dokument v indexe NEMA (nesie `processId`) - takze obrazovka
    # nastaveni bola prazdna, hoci case aj uloha existovali.
    if "Konfigurácia schvaľovania" in items:
        st, tl = riad.get(f"/api/task/case/{items['Konfigurácia schvaľovania']}")
        vt = [t["stringId"] for t in (tl or []) if t["transitionId"] == "view"]
        vf = fields(riad, vt[0]) if vt else {}
        fcid = vf.get("filter_case_id")
        dopyt = None
        if fcid:
            st, fc = riad.get(f"/api/workflow/case/{fcid}")
            for d in ((fc or {}).get("immediateData") or []):
                if d.get("importId") == "filter":
                    dopyt = d.get("value")
        check("zobrazenie konfiguracie ma dopyt", bool(dopyt), dopyt)
        if dopyt:
            check("dopyt nestoji na `processIdentifier` (task dokument ho nema)",
                  "processIdentifier" not in dopyt, dopyt)
            found = 0
            for _ in range(20):
                st, r = riad.post("/api/task/search_es?size=20", {"query": dopyt})
                found = len((r.get("_embedded") or {}).get("tasks", [])) \
                    if isinstance(r, dict) else -1
                if found > 0:
                    break
                time.sleep(3)
            check("zobrazenie konfiguracie naozaj najde ulohu", found >= 1,
                  f"{found} uloh pre dopyt {dopyt}")

    if cfg_id:
        tcfg = tasks_of(riad, cfg_id).get("t_sc_nastavenia")
        check("spravca ma otvorenu konfiguracnu ulohu", bool(tcfg),
              list(tasks_of(riad, cfg_id)))
        # Formular sa naplni zo SKUTOCNEHO stavu roli - `assign` akcia.
        assign(riad, tcfg)
        d = fields(riad, tcfg)
        check("formular ponuka uzivatelov na vyber",
              len(options(riad, tcfg, "sc_wellness")) >= 3,
              len(options(riad, tcfg, "sc_wellness")))
        wellness = set(d.get("sc_wellness") or [])
        check("wellness ukazuje skutocnych drzitelov roly (super aj operator)",
              len(wellness) >= 2, sorted(wellness))
        check("limit je nacitany", float(d.get("sc_limit") or 0) > 0, d.get("sc_limit"))

        # --- limit sa naozaj prejavi v smerovani ------------------------------
        set_data(riad, tcfg, {"sc_limit": {"type": "number", "value": 500.0}})
        st, r = finish(riad, tcfg)
        check("konfiguracia ulozena", ok_body(r), str(r)[:140])
        d = fields(riad, tasks_of(riad, cfg_id)["t_sc_nastavenia"])
        check("uloženie povie, co spravilo", "limit" in (d.get("sc_vysledok") or ""),
              (d.get("sc_vysledok") or "")[:160])

        # Faktura za 700 EUR bola do limitu 1000 pod strediskom; pri limite 500
        # musi ist aj riaditelovi. To je dokaz, ze siet cita konfiguraciu.
        fa_cfg, _ = new_case(zad, net_fa["stringId"])
        tc = tasks_of(zad, fa_cfg)["t_fa_zapis"]
        set_data(zad, tc, {
            "fa_dodavatel": {"type": "text", "value": "Limit Test s.r.o."},
            "fa_cislo": {"type": "text", "value": "2026300"},
            "fa_suma": {"type": "number", "value": 700.0},
            "fa_datum_splatnosti": {"type": "date", "value": "2026-12-01"},
            "fa_stredisko": {"type": "enumeration_map", "value": "wellness"},
            "fa_predmet": {"type": "text", "value": "Kontrola limitu z konfigurácie."}})
        d = fields(zad, tc)
        check("700 € je pri limite 500 nad limitom (upozorni)",
              "riaditeľ" in (d.get("fa_kontrola") or ""), d.get("fa_kontrola"))
        finish(zad, tc)
        rozh = tasks_of(sch, fa_cfg)["t_fa_schvalenie"]
        set_data(sch, rozh, {"fa_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
        st, r = finish(sch, rozh)
        check("schvalenie strediskom preslo", ok_body(r), str(r)[:120])
        check("pri limite 500 ide 700 € aj riaditelovi",
              stav_of(zad, fa_cfg, "fa_stav_label") == "u_riaditela",
              stav_of(zad, fa_cfg, "fa_stav_label"))

        # --- a zmena schvalovatela naozaj prehodi rolu ------------------------
        tcfg = tasks_of(riad, cfg_id)["t_sc_nastavenia"]
        assign(riad, tcfg)
        d = fields(riad, tcfg)
        povodne = list(d.get("sc_marketing") or [])
        st, users = riad.post("/api/user/search?size=20", {"fulltext": "druhy@test.local"})
        druhy_id = [u["id"] for u in (users.get("_embedded") or {}).get("users", [])
                    if u.get("email") == "druhy@test.local"][0]
        set_data(riad, tcfg, {
            "sc_marketing": {"type": "multichoice_map", "value": povodne + [druhy_id]},
            "sc_limit": {"type": "number", "value": 1000.0}})
        st, r = finish(riad, tcfg)
        check("pridanie schvalovatela marketingu ulozene", ok_body(r), str(r)[:120])
        d = fields(riad, tasks_of(riad, cfg_id)["t_sc_nastavenia"])
        check("uloženie ohlasi zmenu roly",
              "schv_marketing" in (d.get("sc_vysledok") or ""),
              (d.get("sc_vysledok") or "")[:200])
        check("limit je zase 1000", float(d.get("sc_limit") or 0) == 1000.0, d.get("sc_limit"))

        # Novy schvalovatel to naozaj ma - overene na NOVEJ fakture marketingu.
        # `druhy` sa musi prihlasit znova: session drzi stare stringId roli.
        zad2b = Client("druhy@test.local", TEST_PASS)
        fa_mk2, _ = new_case(zad, net_fa["stringId"])
        tm2 = tasks_of(zad, fa_mk2)["t_fa_zapis"]
        set_data(zad, tm2, {
            "fa_dodavatel": {"type": "text", "value": "Marketing Test s.r.o."},
            "fa_cislo": {"type": "text", "value": "2026301"},
            "fa_suma": {"type": "number", "value": 90.0},
            "fa_datum_splatnosti": {"type": "date", "value": "2026-12-05"},
            "fa_stredisko": {"type": "enumeration_map", "value": "marketing"},
            "fa_predmet": {"type": "text", "value": "Kontrola nového schvaľovateľa."}})
        finish(zad, tm2)
        check("novy schvalovatel marketingu fakturu vidi",
              "t_fa_schvalenie" in tasks_of(zad2b, fa_mk2), list(tasks_of(zad2b, fa_mk2)))

        # Vratit stav, aby dalsi beh testu zacinal tam, kde tento
        tcfg = tasks_of(riad, cfg_id)["t_sc_nastavenia"]
        assign(riad, tcfg)
        set_data(riad, tcfg, {"sc_marketing": {"type": "multichoice_map", "value": povodne}})
        finish(riad, tcfg)

    # Nazov polozky menu musi byt v celom portali unikatny. Nie kvoli schéme -
    # engine dve rovnake pripusti - ale kvoli dvom veciam, ktore obe mlcia:
    # dashboard ukazuje karty bez priecinka (dve rovnake sa nedaju odlisit)
    # a testy si polozky hladaju podla nazvu, takze jedna prepise druhu.
    st, mi_all = riad.post("/api/workflow/case/search?size=200",
                           {"process": [{"identifier": "preference_filter_item"}]})
    podla_nazvu = {}
    for c in (mi_all.get("_embedded") or {}).get("cases", []):
        podla_nazvu.setdefault(c["title"], []).append(c["stringId"])
    kolizie = {k: v for k, v in podla_nazvu.items() if len(v) > 1}
    check("ziadne dve zobrazenia v menu sa nevolaju rovnako", not kolizie, kolizie)

    print("\n=== 21. anglicky portal: stav je prelozeny ===")
    # `Accept-Language: en` musi vratit anglicke popisky. Stav je preto
    # `enumeration_map` a nie `text`: `TextField` drzi `String`, ktory engine
    # prelozit nevie, takze hodnota zapisana akciou by v anglickom portali
    # zostala slovenska - a bola by to jedina slovenska vec na formulari.
    zad_en = Client("operator@test.local", TEST_PASS, lang="en")
    fa_en, _ = new_case(zad_en, net_fa["stringId"])
    ten = tasks_of(zad_en, fa_en)["t_fa_zapis"]
    assign(zad_en, ten)
    st, d = zad_en.get(f"/api/task/{ten}/data")
    groups = (d.get("data") or d.get("outcome", {}).get("data") or []) if isinstance(d, dict) else []
    stav_opts, titles = {}, {}
    for g in groups:
        for _, lst in g.get("fields", {}).get("_embedded", {}).items():
            for f in lst:
                if f["stringId"] == "fa_stav_label":
                    stav_opts = f.get("options") or {}
                titles[f["stringId"]] = f.get("name") or f.get("title") or ""
    check("stav ma v anglickom portali anglicke moznosti",
          stav_opts.get("koncept") == "Draft" and stav_opts.get("zauctovana") == "Posted",
          {k: stav_opts.get(k) for k in ("koncept", "zauctovana")})
    check("nazvy poli su v anglictine",
          titles.get("fa_dodavatel") == "Supplier"
          and titles.get("fa_suma", "").startswith("Amount"),
          [titles.get("fa_dodavatel"), titles.get("fa_suma")])
    sk_texts = [v for v in titles.values()
                if any(ch in v for ch in "áäčďéíĺľňóôřšťúýž")]
    check("na anglickom formulari nie je ziadny slovensky nazov pola",
          not sk_texts, sk_texts[:5])
    riad.call("DELETE", f"/api/workflow/case/{fa_en}")

    print("\n=== STARE VERZIE ===")
    # Case si drzi verziu siete, v ktorej vznikol - nove prechody a polia do
    # neho NEPRIBUDNU. Kto testuje na case zalozenom pred re-importom, testuje
    # stary model a nevie o tom.
    for ident, net in ((FAKTURA, net_fa), (OBJEDNAVKA, net_ob)):
        stare = stale_cases(su, ident, net)
        st, allc = su.post("/api/workflow/case/search?size=500",
                           {"process": [{"identifier": ident}]})
        cases = (allc.get("_embedded") or {}).get("cases", [])
        print(f"  {ident}: najnovsia v{net['version']}, casov {len(cases)}, "
              f"na starsej verzii {len(stare)}")
        # Nie je to len kozmetika: stary case nesie aj stary LAYOUT formulara.
        # Ked sa v novej verzii posunulo pole, ktore sa predtym prekryvalo,
        # stary case sa v appke NEVYKRESLI - Angular grid vyhodi vynimku
        # a formular zostane na spinneri. Preto to je kontrola, nie hlaska.
        check(f"{ident}: ziadny case nebezi na starsej verzii siete",
              not stare, [c["stringId"] for c in stare][:5])
    print("  Na cistu skusku: python3 tools/sccheck.py --wipe   (zmaze VSETKY casy appky)")

    print(f"\nsccheck: {len(OK)} preslo, {len(FAIL)} zlyhalo")
    for f in FAIL:
        print("  ZLYHALO:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
