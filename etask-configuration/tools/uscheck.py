#!/usr/bin/env python3
"""
uscheck - akceptacny test appky Uzivatelia proti BEZIACEMU enginu.

Overuje to, co sa z XML ani z importu zistit neda: ze sa cez proces naozaj
vytvori uzivatel, ze sa PRIHLASI, ze ma systemove authorities (bez nich sa
prihlasi a nevidi nic) a ze mu sedi procesna rola.

Tri veci, na ktore sa tu naletelo a preto su v kode napisane:

  1. Telo `POST /api/task/{id}/data` je {taskId: {fieldId: {...}}}, NIE
     {fieldId: {...}}. Ploche telo vrati HTTP 200 s hlaskou "Could not find
     task with id [<fieldId>]" a ticho nezapise nic.
  2. Engine odmietnutie NEHLASI HTTP kodom - `finish` vrati 200 a dovod da do
     tela ako `error`. Test na status by taky blok prehliadol.
  3. `GET /api/auth/login` vrati 405, ale token uz je v hlavicke - autentifikacny
     filter bezi pred handlerom.

Predpoklad: bezi stack (tools/up.sh) a role su pridelene (tools/pfseed.py).

    python3 tools/uscheck.py
    python3 tools/uscheck.py --wipe    # zmaze casy appky aj uzivatelov z testov

Test ZAKLADA UZIVATELOV - nespustat proti produkcii.

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
NET = "uzivatelia/us_uzivatel"

OK, FAIL = [], []


class Client:
    def __init__(self, email, password, allow_fail=False):
        self.email = email
        self.token = None
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
        except urllib.error.URLError:
            sys.exit(f"uscheck: engine na {URL} neodpoveda")
        if not self.token and not allow_fail:
            sys.exit(f"uscheck: prihlasenie {email} zlyhalo")

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
    st, r = cl.post("/api/petrinet/search?size=200", {"identifier": identifier})
    refs = [x for x in r["_embedded"]["petriNetReferences"] if x["identifier"] == identifier]
    if not refs:
        sys.exit(f"uscheck: siet {identifier} nie je naimportovana")
    refs.sort(key=lambda x: [int(n) for n in x["version"].split(".")])
    return refs[-1]


def new_case(cl, net_id):
    """(caseId, case). Odpoved nesie id len v texte `success`."""
    st, r = cl.post("/api/workflow/case", {"netId": net_id, "title": None, "color": ""})
    m = re.search(r"Case with id ([0-9a-f]{24})", r.get("success", "") if isinstance(r, dict) else "")
    if not m:
        sys.exit(f"uscheck: zalozenie casu zlyhalo: {st} {str(r)[:300]}")
    st, c = cl.get(f"/api/workflow/case/{m.group(1)}")
    return m.group(1), c


def tasks_of(cl, case_id):
    """Ulohy, ktore uzivatel NAOZAJ vidi. NIE `GET /api/task/case/{id}` - ten
    opravnenia neoveruje a vrati vsetko kazdemu, kto pozna id."""
    st, r = cl.post("/api/task/search?size=100", {"case": [{"id": case_id}]})
    tl = (r.get("_embedded") or {}).get("tasks", []) if isinstance(r, dict) else []
    return {t["transitionId"]: t["stringId"] for t in tl}


def field_map(cl, task_id):
    st, d = cl.get(f"/api/task/{task_id}/data")
    groups = (d.get("data") or d.get("outcome", {}).get("data") or []) if isinstance(d, dict) else []
    out = {}
    for grp in groups:
        for _, lst in grp.get("fields", {}).get("_embedded", {}).items():
            for f in lst:
                out[f["stringId"]] = f
    return out


def values(cl, task_id):
    return {k: v.get("value") for k, v in field_map(cl, task_id).items()}


def set_data(cl, task_id, vals):
    cl.get(f"/api/task/assign/{task_id}")
    return cl.post(f"/api/task/{task_id}/data", {task_id: vals})


def wipe(cl):
    st, r = cl.post("/api/workflow/case/search?size=500", {"process": [{"identifier": NET}]})
    cases = (r.get("_embedded") or {}).get("cases", [])
    for c in cases:
        cl.call("DELETE", f"/api/workflow/case/{c['stringId']}")
    print(f"uscheck: zmazanych {len(cases)} casov {NET}")
    st, r = cl.post("/api/user/search?size=500", {"fulltext": "uscheck"})
    users = (r.get("_embedded") or {}).get("users", []) if isinstance(r, dict) else []
    print(f"uscheck: uzivatelov z testov najdenych {len(users)} "
          f"(mazanie uzivatela cez REST engine nema, zmaz ich cez --fresh)")


def main():
    boss = Client("super@netgrif.com", SUPER_PASS)
    if "--wipe" in sys.argv:
        wipe(boss)
        return 0

    print("=== 1. prihlasenie ===")
    spravca = Client("admin@test.local", TEST_PASS)      # ma rolu spravca
    # NIE viewer@test.local: ten nema ziadnu rolu a nevidi ZIADNU kartu, takze
    # "nevidi uzivatelia" by preslo aj keby bola karta zle zabezpecena.
    # operator ma rolu `specialist` a nejake karty vidi - preto je jeho slepota
    # prave na tejto karte dokazom, ze `requiredProcessRoles` funguje.
    iny = Client("operator@test.local", TEST_PASS)
    print("  admin (spravca) / operator (specialist, nie spravca)")

    print("\n=== 2. karta v bocnom menu ===")
    for name, cl, expected in [("spravca", spravca, True), ("ina rola", iny, False)]:
        st, root = cl.get("/api/v2/uri/root")
        paths = [c["uriPath"] for c in root.get("children", [])]
        check(f"{name} {'vidi' if expected else 'nevidi'} kartu 'uzivatelia'",
              ("uzivatelia" in paths) == expected, paths)
        if not expected:
            check(f"{name} pritom ine karty vidi (inak by test nic nedokazal)",
                  len(paths) > 0, paths)
    st, node = spravca.get("/api/v2/uri/" + base64.b64encode(b"uzivatelia").decode())
    check("karta ma ikonu manage_accounts", node.get("icon") == "manage_accounts", node.get("icon"))

    print("\n=== 3. zobrazenia pod kartou ===")
    st, mi = boss.post("/api/workflow/case/search?size=300",
                       {"process": [{"identifier": "preference_filter_item"}]})
    items = {c["title"]: c["stringId"] for c in mi.get("_embedded", {}).get("cases", [])}
    WANT_HEADERS = ("meta-title,uzivatelia/us_uzivatel-us_stav_label"
                    ",uzivatelia/us_uzivatel-us_email,uzivatelia/us_uzivatel-us_authority")
    for want in ["Používatelia", "Rozpísané"]:
        check(f"zobrazenie '{want}' existuje", want in items, sorted(items))
        if want in items:
            st, tl = boss.get(f"/api/task/case/{items[want]}")
            vt = [t for t in (tl or []) if t["transitionId"] == "view"]
            f = values(boss, vt[0]["stringId"]) if vt else {}
            check(f"'{want}' ma predvolene stlpce", f.get("default_headers") == WANT_HEADERS,
                  f.get("default_headers"))
            check(f"'{want}' sa nepyta na nazov pripadu",
                  f.get("enable_case_title") is False, f.get("enable_case_title"))
    # Stlpec z DATOVEHO pola sa vykresli len na zobrazeni, ktore ma ten net
    # v `allowedNets` - `CaseHeaderService` sklada ponuku stlpcov z povolenych
    # sieti a `default_headers` v nej `uniqueId` iba vyhlada. Co nenajde, necha
    # prazdne a NIC nezaloguje, takze hodnota v datach sedi a v appke vidno len
    # `meta-*`. V sesterskej appke to takto ticho vypadlo dvom zobrazeniam.
    for want in ["Používatelia", "Rozpísané"]:
        if want not in items:
            continue
        st, tl = boss.get(f"/api/task/case/{items[want]}")
        vt = [t for t in (tl or []) if t["transitionId"] == "view"]
        v = values(boss, vt[0]["stringId"]) if vt else {}
        need = {h.rsplit("-", 1)[0]
                for h in (v.get("default_headers") or "").split(",")
                if h and not h.startswith("meta-")}
        have = set()
        if v.get("filter_case_id"):
            st, fc = boss.get(f"/api/workflow/case/{v['filter_case_id']}")
            for d in (fc.get("immediateData") or []):
                if d.get("allowedNets"):
                    have = set(d["allowedNets"])
        check(f"'{want}' ma v allowedNets siete svojich stlpcov",
              need <= have, f"treba {sorted(need)}, ma {sorted(have)}")

    st, mc = boss.post("/api/workflow/case/search?size=10",
                       {"process": [{"identifier": "uzivatelia/us_menu"}]})
    mt = [c["title"] for c in mc.get("_embedded", {}).get("cases", [])]
    check("bootstrap case menu hlasi 2/2", any("2/2" in t for t in mt), mt)

    print("\n=== 4. spravca zaklada uzivatela ===")
    net = newest_net(spravca, NET)
    print(f"  siet {net['identifier']} v{net['version']}")
    case_id, case = new_case(spravca, net["stringId"])
    check("nazov casu zacina stavom", case["title"].startswith("Rozpísaný"), case["title"])
    t = tasks_of(spravca, case_id)
    check("spravca ma PRESNE jednu ulohu", list(t) == ["t_us_zadanie"], list(t))
    zadanie = t["t_us_zadanie"]

    # Moznosti roli sa citaju z instancie cez processRoleOptions(), nie z XML.
    fm = field_map(spravca, zadanie)
    role_opts = list((fm.get("us_roly", {}).get("options") or {}).keys())
    check("moznosti roli sa nacitali z instancie", len(role_opts) > 0, role_opts[:4])
    check("kluc roly je 'importId:identifikator/siete'",
          all(":" in k and "/" in k.split(":", 1)[1] for k in role_opts), role_opts[:4])
    check("systemove roly enginu sa neponukaju",
          not any(k.startswith("default:") or k.startswith("anonymous:") for k in role_opts))

    print("\n=== 5. co sa nesmie dat ===")
    set_data(spravca, zadanie, {
        "us_meno": {"type": "text", "value": "Test"},
        "us_priezvisko": {"type": "text", "value": "Uscheck"},
        "us_email": {"type": "text", "value": "toto nie je email"},
        "us_heslo": {"type": "text", "value": "dostatocne_dlhe"}})
    st, r = spravca.get(f"/api/task/finish/{zadanie}")
    check("neplatny e-mail je odmietnuty", isinstance(r, dict) and "error" in r, str(r)[:120])
    check("odmietnutie povie preco", "nemá platný tvar" in str(r), str(r)[:160])

    stamp = str(int(time.time()))
    email = f"uscheck.{stamp}@test.local"
    set_data(spravca, zadanie, {
        "us_email": {"type": "text", "value": email},
        "us_heslo": {"type": "text", "value": "krat"}})
    st, r = spravca.get(f"/api/task/finish/{zadanie}")
    check("krotke heslo je odmietnute", isinstance(r, dict) and "error" in r, str(r)[:120])

    set_data(spravca, zadanie, {"us_email": {"type": "text", "value": "admin@test.local"},
                                "us_heslo": {"type": "text", "value": "dostatocne_dlhe"}})
    st, r = spravca.get(f"/api/task/finish/{zadanie}")
    check("existujuci e-mail je odmietnuty", isinstance(r, dict) and "error" in r, str(r)[:120])
    check("odmietnutie povie ktory", "už existuje" in str(r), str(r)[:160])
    check("case stale caka na zadanie", "t_us_zadanie" in tasks_of(spravca, case_id))

    print("\n=== 6. vytvorenie uzivatela ===")
    rola = role_opts[0]
    heslo = "Uscheck!" + stamp
    set_data(spravca, zadanie, {
        "us_email": {"type": "text", "value": email},
        "us_heslo": {"type": "text", "value": heslo},
        "us_authority": {"type": "enumeration_map", "value": "user"},
        "us_roly": {"type": "multichoice_map", "value": [rola]}})
    st, r = spravca.get(f"/api/task/finish/{zadanie}")
    check("DOKONCIT presiel", isinstance(r, dict) and "success" in r, str(r)[:150])

    te = tasks_of(spravca, case_id)
    check("po vytvoreni ma spravca PRESNE jednu ulohu (prehlad)",
          list(te) == ["t_us_prehlad"], list(te))
    v = values(spravca, te["t_us_prehlad"])
    check("stav je 'Vytvorený'", v.get("us_stav_label") == "Vytvorený", v.get("us_stav_label"))
    check("heslo je z pripadu zmazane", not (v.get("us_heslo") or ""), repr(v.get("us_heslo")))
    check("vysledok popisuje, co sa stalo", email in (v.get("us_vysledok") or ""),
          (v.get("us_vysledok") or "").replace("\n", " | "))
    check("je zapisane kto vytvoril", bool(v.get("us_vytvoril")), v.get("us_vytvoril"))
    st, c = spravca.get(f"/api/workflow/case/{case_id}")
    check("nazov casu zacina 'Vytvorený'", c["title"].startswith("Vytvorený"), c["title"])
    check("farba casu je zelena", c.get("color") == "green", c.get("color"))

    print("\n=== 7. novy uzivatel sa naozaj prihlasi ===")
    novy = Client(email, heslo, allow_fail=True)
    check("prihlasenie noveho uzivatela", bool(novy.token), "bez tokenu" if not novy.token else "ok")
    if novy.token:
        st, me = novy.get("/api/user/me")
        auth = [a.get("authority") if isinstance(a, dict) else a
                for a in (me.get("authorities") or [])] if isinstance(me, dict) else []
        check("ma ROLE_USER (bez toho by nevidel ziadne zobrazenie)",
              any("ROLE_USER" in str(a) for a in auth), auth)
        roles = [r.get("importId") for r in (me.get("processRoles") or [])] \
            if isinstance(me, dict) else []
        want_import = rola.split(":", 1)[0]
        check(f"ma pridelenu procesnu rolu '{want_import}'", want_import in roles, roles)
        check("nie je administrator", not any("ROLE_ADMIN" in str(a) for a in auth), auth)

    print("\n=== 8. zobrazenie 'Rozpísané' filtruje podla datoveho pola ===")
    st, r = spravca.post("/api/workflow/case/search?size=100",
                         {"query": f'processIdentifier:"{NET}"'
                                   ' AND dataSet.us_stav_label.textValue:"Rozpísaný"'})
    ids = [x["stringId"] for x in (r.get("_embedded") or {}).get("cases", [])] \
        if isinstance(r, dict) else []
    check("vytvoreny case v 'Rozpísané' nie je", case_id not in ids, f"{len(ids)} casov")
    c2, _ = new_case(spravca, net["stringId"])
    st, r = spravca.post("/api/workflow/case/search?size=100",
                         {"query": f'processIdentifier:"{NET}"'
                                   ' AND dataSet.us_stav_label.textValue:"Rozpísaný"'})
    ids = [x["stringId"] for x in (r.get("_embedded") or {}).get("cases", [])] \
        if isinstance(r, dict) else []
    check("novy rozpisany case v 'Rozpísané' je", c2 in ids, f"{len(ids)} casov")

    print(f"\nuscheck: {len(OK)} preslo, {len(FAIL)} zlyhalo")
    for f in FAIL:
        print("  ZLYHALO:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
