#!/usr/bin/env python3
"""
dvcheck - akceptacny test appky Dovolenky proti BEZIACEMU enginu.

Preco to existuje samostatne od pflint/pfgroovy/pfcheck:

  pflint a pfgroovy citaju XML. pfcheck overi, ze siet engine PRIJME. Ani jeden
  z nich nepovie, ci appka robi to, co ma - ci zamestnanec vidi svoju ziadost
  a cudziu nie, ci sa da schvalit ziadost, ktora este nebola podana, a ci sa
  v prehlade naozaj objavi poznamka veduceho. To sa da zistit iba tak, ze sa
  cely priebeh preklika cez API.

Tri veci, na ktore sa tu naletelo a preto su v kode napisane:

  1. Telo `POST /api/task/{id}/data` je {taskId: {fieldId: {...}}}, NIE
     {fieldId: {...}}. Ploche telo vrati HTTP 200 s hlaskou "Could not find
     task with id [<fieldId>]" a ticho nezapise nic.
  2. Engine odmietnutie NEHLASI HTTP kodom. `finish` na ulohe, ktoru zablokuje
     akcia v phase="pre", vrati HTTP 200 a dovod da do tela ako `error`.
     Test, ktory sa pozera na status, taky blok prehliadne.
  3. `GET /api/auth/login` vrati 405, ale token uz je v hlavicke - autentifikacny
     filter bezi pred handlerom. To iste robi pfcheck.sh.
  4. Odmietnute `finish` (required pole alebo vynimka z phase="pre") ZMAZE
     ostatne ulohy povolene vstupnym miestom toho prechodu a uz ich neobnovi -
     token sa nepohol, takze nie je co ich znova povolit. Preto tu je kontrola
     "odmietnute DOKONCIT nikomu neubralo ulohu": kym na p_na_schvalenie visel
     read-only pohlad ziadatela, jedno nepodarene kliknutie veduceho mu case
     navzdy zavrelo. Podrobne v docs/PETRIFLOW_LEARNINGS.md, B8b.
  5. `GET /api/task/case/{id}` NEFILTRUJE podla opravneni - vrati vsetky ulohy
     casu kazdemu, kto pozna id. Zoznam uloh v UI stavia `POST /api/task/search`,
     ktory filtruje. Test na tom prvom by tvrdil, ze zamestnanec vidi
     Rozhodnut o ziadosti, a naopak by prehliadol, keby filtrovanie prestalo
     fungovat. Preto `tasks_of` pouziva /search a `tasks_raw` to druhe.

Predpoklad: bezi stack (tools/up.sh), siete su naimportovane a role pridelene
(tools/pfseed.py). Testovacie ucty vznikaju len s ETASK_TEST_PASSWORD.

    python3 tools/dvcheck.py
    python3 tools/dvcheck.py --wipe      # zmaze casy appky (zmes starych verzii)
    PF_URL=http://host:8080 ETASK_TEST_PASSWORD=xyz python3 tools/dvcheck.py

Test ZAKLADA CASY - nespustat proti produkcii.

Exit 0 = vsetko preslo, 1 = nieco zlyhalo.
"""

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

URL = os.environ.get("PF_URL", "http://127.0.0.1:8080")
TEST_PASS = os.environ.get("ETASK_TEST_PASSWORD", "test1234")

OK, FAIL = [], []


class Client:
    def __init__(self, email, password):
        self.email = email
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
            sys.exit(f"dvcheck: prihlasenie {email} zlyhalo")

    def call(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"X-Auth-Token": self.token,
                   # Bez hal+json vracaju HATEOAS endpointy 406.
                   "Accept": "application/hal+json, application/json;q=0.9, */*;q=0.8"}
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
        sys.exit(f"dvcheck: siet {identifier} nie je naimportovana")
    refs.sort(key=lambda x: [int(n) for n in x["version"].split(".")])
    return refs[-1]


def new_case(cl, net_id):
    """(caseId, case). Odpoved nesie id len v texte `success` - `outcome.aCase`
    ma `_id` ako objekt, nie stringId."""
    st, r = cl.post("/api/workflow/case", {"netId": net_id, "title": None, "color": ""})
    m = re.search(r"Case with id ([0-9a-f]{24})", r.get("success", "") if isinstance(r, dict) else "")
    if not m:
        sys.exit(f"dvcheck: zalozenie casu zlyhalo: {st} {str(r)[:300]}")
    st, c = cl.get(f"/api/workflow/case/{m.group(1)}")
    return m.group(1), c


def tasks_of(cl, case_id):
    """Ulohy, ktore uzivatel NAOZAJ vidi - to iste, z coho stavia zoznam UI.

    NIE `GET /api/task/case/{id}`: ten vrati vsetky ulohy casu bez ohladu na
    opravnenia, takze zamestnanec v nom "vidi" aj Rozhodnut o ziadosti.
    Test postaveny na nom tvrdi, ze filtrovanie funguje, aj ked nefunguje."""
    st, r = cl.post(f"/api/task/search?size=100", {"case": [{"id": case_id}]})
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
    """Kluce moznosti enumeration_map pola."""
    st, d = cl.get(f"/api/task/{task_id}/data")
    groups = (d.get("data") or d.get("outcome", {}).get("data") or []) if isinstance(d, dict) else []
    for grp in groups:
        for _, lst in grp.get("fields", {}).get("_embedded", {}).items():
            for f in lst:
                if f["stringId"] == field_id:
                    return list((f.get("options") or {}).keys())
    return []


def behavior(cl, task_id, field_id):
    """Aktualne `behavior` pola na danom tasku - `make ... visible/hidden`
    sa v odpovedi prejavi tu, nie na hodnote."""
    st, d = cl.get(f"/api/task/{task_id}/data")
    groups = (d.get("data") or d.get("outcome", {}).get("data") or []) if isinstance(d, dict) else []
    for grp in groups:
        for _, lst in grp.get("fields", {}).get("_embedded", {}).items():
            for f in lst:
                if f["stringId"] == field_id:
                    return f.get("behavior") or {}
    return {}


def set_data(cl, task_id, values):
    """Telo je {taskId: {fieldId: {...}}}, nie {fieldId: {...}} - viz hlavicka."""
    cl.get(f"/api/task/assign/{task_id}")
    return cl.post(f"/api/task/{task_id}/data", {task_id: values})


def wipe(cl):
    """Zmaze vsetky casy appky. Case si drzi verziu siete, v ktorej vznikol,
    takze po viacerych re-importoch je v databaze zmes modelov."""
    st, r = cl.post("/api/workflow/case/search?size=500",
                    {"process": [{"identifier": "dovolenky/dv_ziadost"}]})
    cases = (r.get("_embedded") or {}).get("cases", [])
    for c in cases:
        cl.call("DELETE", f"/api/workflow/case/{c['stringId']}")
    print(f"dvcheck: zmazanych {len(cases)} casov dovolenky/dv_ziadost")


def main():
    if "--wipe" in sys.argv:
        wipe(Client("super@netgrif.com", os.environ.get("PF_PASS", "password")))
        return 0

    print("=== 1. prihlasenie ===")
    emp = Client("operator@test.local", TEST_PASS)       # zamestnanec
    emp2 = Client("druhy@test.local", TEST_PASS)         # iny zamestnanec
    boss = Client("admin@test.local", TEST_PASS)         # veduci
    viewer = Client("viewer@test.local", TEST_PASS)      # bez roli na sieti
    print("  operator / druhy / admin / viewer")

    print("\n=== 2. karta v bocnom menu ===")
    # /api/v2/uri je nas filtrujuci controller; engine `/api/uri` nefiltruje.
    for name, cl, expected in [("zamestnanec", emp, True), ("veduci", boss, True),
                               ("bez roli", viewer, False)]:
        st, root = cl.get("/api/v2/uri/root")
        paths = [c["uriPath"] for c in root.get("children", [])]
        check(f"{name} {'vidi' if expected else 'nevidi'} kartu 'dovolenky'",
              ("dovolenky" in paths) == expected, paths)
    st, node = emp.get("/api/v2/uri/" + base64.b64encode(b"dovolenky").decode())
    check("karta ma ikonu beach_access", node.get("icon") == "beach_access", node.get("icon"))

    print("\n=== 3. zobrazenia pod kartou ===")
    st, mi = boss.post("/api/workflow/case/search?size=200",
                       {"process": [{"identifier": "preference_filter_item"}]})
    items = {c["title"]: c["stringId"] for c in mi.get("_embedded", {}).get("cases", [])}
    for want in ["Žiadosti o dovolenku", "Na schválenie", "Rozpísané a vrátené", "Vybavené"]:
        check(f"zobrazenie '{want}' existuje", want in items, sorted(items))

    def view_task_fields(title):
        st, tl = boss.get(f"/api/task/case/{items[title]}")
        vt = [t for t in (tl or []) if t["transitionId"] == "view"]
        return fields(boss, vt[0]["stringId"]) if vt else {}

    if "Žiadosti o dovolenku" in items:
        # Bez `enable_case_title = false` vyskoci pri "+" dialog na nazov pripadu.
        vf = view_task_fields("Žiadosti o dovolenku")
        check("zakladanie sa nepyta na nazov pripadu",
              vf.get("enable_case_title") is False, vf.get("enable_case_title"))

    def roles_of(title):
        st, full = boss.get(f"/api/workflow/case/{items[title]}")
        for d in (full.get("immediateData") or []):
            if d.get("importId") == "allowed_roles":
                return sorted((d.get("options") or {}).keys())
        return []

    if "Na schválenie" in items:
        # Drawer aj UriCountService filtruju polozku podla allowed_roles
        # zakodovanych ako "importId:identifikator siete".
        check("'Na schválenie' je obmedzene na rolu veduci",
              roles_of("Na schválenie") == ["veduci:dovolenky/dv_ziadost"],
              roles_of("Na schválenie"))
    if "Žiadosti o dovolenku" in items:
        check("'Žiadosti o dovolenku' vidia obe roly", roles_of("Žiadosti o dovolenku") == [])

    st, mc = boss.post("/api/workflow/case/search?size=10",
                       {"process": [{"identifier": "dovolenky/dv_menu"}]})
    mt = [c["title"] for c in mc.get("_embedded", {}).get("cases", [])]
    check("bootstrap case menu hlasi 4/4", any("4/4" in t for t in mt), mt)

    print("\n=== 4. zamestnanec zaklada ziadost ===")
    net = newest_net(emp, "dovolenky/dv_ziadost")
    print(f"  siet {net['identifier']} v{net['version']}")
    case_id, case = new_case(emp, net["stringId"])
    check("create akcia dala casu systemovy nazov bez zasahu uzivatela",
          case["title"] == "Rozpísaná · Žiadosť o dovolenku · Operator Testovaci", case["title"])
    check("stav je na zaciatku nazvu (prezije skratenie stlpca)",
          case["title"].startswith("Rozpísaná"), case["title"])
    check("case ma farbu podla stavu", case.get("color") == "grey", case.get("color"))
    t = tasks_of(emp, case_id)
    check("zamestnanec vidi 'Podať žiadosť'", "t_dv_podanie" in t, list(t))
    check("rozpisana ziadost ma pre zamestnanca PRESNE jednu ulohu",
          list(t) == ["t_dv_podanie"], list(t))
    check("veduci pri rozpisanej nema nic", not tasks_of(boss, case_id),
          list(tasks_of(boss, case_id)))

    podanie = t["t_dv_podanie"]

    print("\n=== 5. obrateny termin (do < od) ===")
    st, r = set_data(emp, podanie, {
        "dv_od": {"type": "date", "value": "2026-10-10"},
        "dv_do": {"type": "date", "value": "2026-10-05"},
        "dv_dovod": {"type": "text", "value": "Test obrateneho terminu"}})
    check("zapis datumov presiel", "success" in str(r), str(r)[:120])
    d = fields(emp, podanie)
    check("set event varuje hned", "skôr ako dátum od" in (d.get("dv_kontrola") or ""),
          d.get("dv_kontrola"))
    check("pocet dni sa nepocita", not d.get("dv_dni"), d.get("dv_dni"))
    check("Kontrola je pri obratenom termine viditelna",
          behavior(emp, podanie, "dv_kontrola").get("visible") is True,
          behavior(emp, podanie, "dv_kontrola"))
    st, r = emp.get(f"/api/task/finish/{podanie}")
    check("DOKONCIT je odmietnute", isinstance(r, dict) and "error" in r, f"HTTP {st} {str(r)[:120]}")
    check("odmietnutie povie preco", "Dátum do nemôže byť skôr" in str(r), str(r)[:200])
    check("token zostal v p_koncept", "t_dv_podanie" in tasks_of(emp, case_id))
    check("ziadost sa NEDOSTALA veducemu", "t_dv_rozhodnutie" not in tasks_of(boss, case_id))

    print("\n=== 6. spravne podanie ===")
    set_data(emp, podanie, {
        "dv_od": {"type": "date", "value": "2026-10-05"},
        "dv_do": {"type": "date", "value": "2026-10-09"},
        "dv_dovod": {"type": "text", "value": "Rodinná dovolenka pri mori."}})
    d = fields(emp, podanie)
    check("pocet dni je 5 (vratane oboch dni)", str(d.get("dv_dni")) in ("5", "5.0"), d.get("dv_dni"))
    check("varovanie zmizlo", not (d.get("dv_kontrola") or ""), d.get("dv_kontrola"))
    check("Kontrola je pri poriadnom termine skryta",
          behavior(emp, podanie, "dv_kontrola").get("hidden") is True,
          behavior(emp, podanie, "dv_kontrola"))
    st, r = emp.get(f"/api/task/finish/{podanie}")
    check("DOKONCIT presiel", isinstance(r, dict) and "success" in r, str(r)[:150])
    st, c = emp.get(f"/api/workflow/case/{case_id}")
    check("nazov casu nesie termin", "5.10.2026" in c["title"] and "9.10.2026" in c["title"], c["title"])
    check("historia zaznamenala podanie",
          "podané:" in (fields(boss, tasks_of(boss, case_id)["t_dv_rozhodnutie"])
                        .get("dv_historia") or ""))
    te = tasks_of(emp, case_id)
    check("po podani nema zamestnanec ziadnu ulohu (nema co robit)", not te, list(te))
    check("veduci ma PRESNE jednu ulohu (Rozhodnúť)",
          list(tasks_of(boss, case_id)) == ["t_dv_rozhodnutie"], list(tasks_of(boss, case_id)))
    check("stav si zamestnanec precita z nazvu casu",
          c["title"].startswith("Čaká na schválenie"), c["title"])
    check("farba casu je 'v obehu'", c.get("color") == "blue", c.get("color"))

    print("\n=== 7. cudzia ziadost nie je vidiet ===")
    st, srch = emp2.post("/api/workflow/case/search?size=50",
                         {"process": [{"identifier": "dovolenky/dv_ziadost"}]})
    seen = [c["stringId"] for c in srch.get("_embedded", {}).get("cases", [])]
    check("iny zamestnanec ju nema vo vyhladavani (odtial stavia UI zoznamy)",
          case_id not in seen, f"{len(seen)} casov")
    st, srch = viewer.post("/api/workflow/case/search?size=50",
                           {"process": [{"identifier": "dovolenky/dv_ziadost"}]})
    check("uzivatel bez roli nevidi ziadnu", not srch.get("_embedded", {}).get("cases", []))
    check("iny zamestnanec nema v zozname uloh nic", not tasks_of(emp2, case_id),
          list(tasks_of(emp2, case_id)))
    check("iny zamestnanec ju nema ani v case liste",
          case_id not in [c["stringId"] for c in
                          (srch.get("_embedded") or {}).get("cases", [])])
    # `GET /api/task/case/{id}` opravnenia neoveruje, takze id uloh sa da ziskat
    # aj bez pristupu. Hranicou je `assign`.
    for t_id in tasks_raw(emp2, case_id).values():
        st, _ = emp2.get(f"/api/task/assign/{t_id}")
        check("iny zamestnanec si ulohu nevie priradit (403)", st == 403, f"HTTP {st}")

    print("\n=== 7b. veduci vracia na prerobenie (tretia moznost v rozhodnuti) ===")
    tb = tasks_of(boss, case_id)
    check("vratenie je v tom istom tasku, nie vo vlastnom",
          list(tb) == ["t_dv_rozhodnutie"], list(tb))
    rozh = tb["t_dv_rozhodnutie"]
    opts = options(boss, rozh, "dv_rozhodnutie")
    check("select ma tri moznosti",
          sorted(opts) == ["schvalena", "vratena", "zamietnuta"], sorted(opts))
    set_data(boss, rozh, {"dv_rozhodnutie": {"type": "enumeration_map", "value": "vratena"}})
    st, r = boss.get(f"/api/task/finish/{rozh}")
    check("vratenie bez dovodu je odmietnute", isinstance(r, dict) and "error" in r, str(r)[:150])
    check("odmietnutie povie preco", "má žiadateľ doplniť" in str(r), str(r)[:200])
    # Regresia na B8b: odmietnute `finish` maze ulohy povolene vstupnym miestom
    # a uz ich neobnovi. Kym tu visel read-only pohlad na p_na_schvalenie,
    # zamestnanec o svoj case po jednom nepodarenom kliknuti veduceho navzdy
    # prisiel. Tato kontrola drzi, ze v strede toku ziadny taky pohlad nie je.
    check("odmietnute DOKONCIT nikomu neubralo ulohu",
          sorted(tasks_raw(boss, case_id)) == ["t_dv_rozhodnutie"],
          sorted(tasks_raw(boss, case_id)))
    set_data(boss, rozh, {"dv_poznamka": {"type": "text",
                                          "value": "Doplň, kto ťa zastúpi na projekte Orion."}})
    st, r = boss.get(f"/api/task/finish/{rozh}")
    check("vratenie preslo", isinstance(r, dict) and "success" in r, str(r)[:150])

    tv = tasks_of(emp, case_id)
    check("ziadatel ma zase PRESNE jednu ulohu (Podať žiadosť)",
          list(tv) == ["t_dv_podanie"], list(tv))
    check("veduci nema po vrateni nic", not tasks_of(boss, case_id),
          list(tasks_of(boss, case_id)))
    d = fields(emp, tv["t_dv_podanie"])
    check("stav je 'Vrátená na prerobenie'", d.get("dv_stav_label") == "Vrátená na prerobenie",
          d.get("dv_stav_label"))
    check("ziadatel vidi dovod priamo vo formulari podania",
          "Orion" in (d.get("dv_poznamka") or ""), d.get("dv_poznamka"))
    check("povodne hodnoty zostali vyplnene", str(d.get("dv_dni")) in ("5", "5.0"), d.get("dv_dni"))
    st, c = emp.get(f"/api/workflow/case/{case_id}")
    check("nazov casu hlasi vratenie", c["title"].startswith("Vrátená na prerobenie"), c["title"])
    check("farba casu hlasi, ze ziadatel ma nieco spravit", c.get("color") == "orange", c.get("color"))

    print("\n=== 7c. ziadatel opravi a poda znova ===")
    set_data(emp, tv["t_dv_podanie"], {
        "dv_od": {"type": "date", "value": "2026-10-05"},
        "dv_do": {"type": "date", "value": "2026-10-08"},
        "dv_dovod": {"type": "text", "value": "Rodinná dovolenka pri mori. Zastúpi ma Peter."}})
    st, r = emp.get(f"/api/task/finish/{tv['t_dv_podanie']}")
    check("opravena ziadost podana", isinstance(r, dict) and "success" in r, str(r)[:150])
    check("vratila sa veducemu", "t_dv_rozhodnutie" in tasks_of(boss, case_id))
    rozh2 = tasks_of(boss, case_id)["t_dv_rozhodnutie"]
    boss.get(f"/api/task/assign/{rozh2}")
    st, r = boss.get(f"/api/task/finish/{rozh2}")
    check("v druhom kole nie je predvyplnena minula volba",
          isinstance(r, dict) and "error" in r, str(r)[:150])
    d = fields(boss, tasks_of(boss, case_id)["t_dv_rozhodnutie"])
    check("pocet dni je prepocitany na 4", str(d.get("dv_dni")) in ("4", "4.0"), d.get("dv_dni"))
    hist = (d.get("dv_historia") or "")
    check("historia ma podanie, vratenie aj opakovane podanie",
          "podané:" in hist and "vrátené na prerobenie" in hist and "podané znova:" in hist,
          hist.replace("\n", " | "))

    print("\n=== 8. veduci rozhoduje ===")
    tb = tasks_of(boss, case_id)
    check("veduci vidi 'Rozhodnúť o žiadosti'", "t_dv_rozhodnutie" in tb, list(tb))
    rozh = tb["t_dv_rozhodnutie"]
    boss.get(f"/api/task/assign/{rozh}")
    check("token zostal na rozhodnuti", "t_dv_rozhodnutie" in tasks_of(boss, case_id))
    set_data(boss, rozh, {
        "dv_rozhodnutie": {"type": "enumeration_map", "value": "schvalena"},
        "dv_poznamka": {"type": "text", "value": "Schválené, zástup si dohodni s Petrom."}})
    st, r = boss.get(f"/api/task/finish/{rozh}")
    check("DOKONCIT s rozhodnutim presiel", isinstance(r, dict) and "success" in r, str(r)[:150])

    print("\n=== 9. zamestnanec vidi vysledok ===")
    te = tasks_of(emp, case_id)
    check("po rozhodnuti ma zamestnanec PRESNE jednu ulohu (Výsledok)",
          list(te) == ["t_dv_vysledok"], list(te))
    check("veduci tiez PRESNE jednu", list(tasks_of(boss, case_id)) == ["t_dv_vysledok"],
          list(tasks_of(boss, case_id)))
    d = fields(emp, te["t_dv_vysledok"])
    check("stav je 'Schválená'", d.get("dv_stav_label") == "Schválená", d.get("dv_stav_label"))
    check("vidi poznamku veduceho", "zástup" in (d.get("dv_poznamka") or ""), d.get("dv_poznamka"))
    check("vidi kto rozhodol", bool(d.get("dv_rozhodol")), d.get("dv_rozhodol"))
    check("vidi kedy sa rozhodlo", bool(d.get("dv_rozhodnute_o")), d.get("dv_rozhodnute_o"))
    st, c = emp.get(f"/api/workflow/case/{case_id}")
    check("nazov casu zacina stavom", c["title"].startswith("Schválená"), c["title"])
    check("farba casu je zelena", c.get("color") == "green", c.get("color"))
    # Vybavene = zobrazenie "Vybavené" v menu; ten isty dopyt, aky ma polozka.
    st, vyb = emp.post("/api/workflow/case/search?size=50",
                       {"query": 'processIdentifier:"dovolenky/dv_ziadost"'
                                 ' AND taskIds:"t_dv_vysledok"'})
    ids = [x["stringId"] for x in (vyb.get("_embedded") or {}).get("cases", [])] \
        if isinstance(vyb, dict) else []
    check("vybavena ziadost padne do zobrazenia 'Vybavené'", case_id in ids, f"{len(ids)} casov")

    print("\n=== 10. zamietnutie ===")
    c2, _ = new_case(emp, net["stringId"])
    t2 = tasks_of(emp, c2)
    set_data(emp, t2["t_dv_podanie"], {
        "dv_od": {"type": "date", "value": "2026-12-23"},
        "dv_do": {"type": "date", "value": "2026-12-31"},
        "dv_dovod": {"type": "text", "value": "Vianoce doma."}})
    st, r = emp.get(f"/api/task/finish/{t2['t_dv_podanie']}")
    check("druha ziadost podana", isinstance(r, dict) and "success" in r, str(r)[:120])
    r2 = tasks_of(boss, c2)["t_dv_rozhodnutie"]
    set_data(boss, r2, {
        "dv_rozhodnutie": {"type": "enumeration_map", "value": "zamietnuta"},
        "dv_poznamka": {"type": "text", "value": "V decembri je uzávierka, prosím posuň to."}})
    st, r = boss.get(f"/api/task/finish/{r2}")
    check("zamietnutie preslo", isinstance(r, dict) and "success" in r, str(r)[:120])
    d2 = fields(emp, tasks_of(emp, c2)["t_dv_vysledok"])
    check("stav je 'Zamietnutá'", d2.get("dv_stav_label") == "Zamietnutá", d2.get("dv_stav_label"))
    check("vidi zamietaciu poznamku", "uzávierka" in (d2.get("dv_poznamka") or ""),
          d2.get("dv_poznamka"))
    check("pocet dni je 9", str(d2.get("dv_dni")) in ("9", "9.0"), d2.get("dv_dni"))

    print("\n=== STARE VERZIE ===")
    # Case si drzi verziu siete, v ktorej vznikol - nove prechody a polia do neho
    # NEPRIBUDNU. Kto testuje na case zalozenom pred re-importom, testuje stary
    # model a nevie o tom; presne takto sa "nova moznost v tasku" javi ako
    # nefunkcna. Preto to dvcheck po kazdom behu spocita.
    st, allc = boss.post("/api/workflow/case/search?size=500",
                         {"process": [{"identifier": "dovolenky/dv_ziadost"}]})
    cases = (allc.get("_embedded") or {}).get("cases", [])
    stare = [c for c in cases if c.get("version") and c["version"] != net["version"]]
    print(f"  najnovsia siet: v{net['version']}   casov spolu: {len(cases)}")
    if stare:
        print(f"  POZOR: {len(stare)} casov bezi na starsej verzii - v UI sa budu")
        print( "         chovat podla modelu, v ktorom vznikli. Na cistu skusku:")
        print( "           python3 tools/dvcheck.py --wipe    (zmaze VSETKY casy tejto appky)")
    else:
        print("  vsetky casy bezia na najnovsej verzii")

    print("\n=== ZNAME OBMEDZENIE ENGINU (nie je to chyba tejto siete) ===")
    st_c, _ = viewer.get(f"/api/workflow/case/{case_id}")
    st_t, _ = viewer.get(f"/api/task/case/{case_id}")
    st, srch = Client("super@netgrif.com", os.environ.get("PF_PASS", "password")).post(
        "/api/workflow/case/search?size=5", {"process": [{"identifier": "service_desk/sd_menu"}]})
    sd = srch.get("_embedded", {}).get("cases", [])
    st_sd = viewer.get(f"/api/workflow/case/{sd[0]['stringId']}")[0] if sd else None
    print(f"  GET /api/workflow/case/{{id}} ako uzivatel bez roli: HTTP {st_c}")
    print(f"  GET /api/task/case/{{id}}     ako uzivatel bez roli: HTTP {st_t}")
    print(f"  to iste na case Service Desku:                     HTTP {st_sd}")
    print("  -> priame GET podla id neoveruje `view`; filtruju len /search a /assign.")
    print("     Plati to rovnako na Service Desku, teda je to vlastnost HTTP vrstvy")
    print("     enginu, nie tejto siete. UI zoznamy stavia /search, takze v appke")
    print("     to vidno nie je - kto ale pozna id casu, precita ho.")

    print(f"\ndvcheck: {len(OK)} preslo, {len(FAIL)} zlyhalo")
    for f in FAIL:
        print("  ZLYHALO:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
