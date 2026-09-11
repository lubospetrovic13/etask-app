#!/usr/bin/env python3
"""
majetokcheck - akceptacny test appky Evidencia zariadení proti BEZIACEMU enginu.

Skelet z tools/pfnew.py. Overuje to, co sa z XML ani z importu zistit neda.
Domenove kontroly sa dopisuju; to, co je tu, plati pre kazdu appku.

Styri veci, na ktore sa v tomto repozitari naletelo a preto su v kode napisane:

  1. Telo `POST /api/task/{id}/data` je {taskId: {fieldId: {...}}}, NIE
     {fieldId: {...}}. Ploche telo vrati HTTP 200 s hlaskou "Could not find
     task with id [<fieldId>]" a ticho nezapise nic.
  2. Engine odmietnutie NEHLASI HTTP kodom - `finish` vrati 200 a dovod da do
     tela ako `error`. Test na status by taky blok prehliadol.
  3. `GET /api/auth/login` vrati 405, ale token uz je v hlavicke - filter bezi
     pred handlerom.
  4. `GET /api/task/case/{id}` NEOVERUJE opravnenia. Na to, co uzivatel naozaj
     vidi, sa musi pouzit `POST /api/task/search`.

Predpoklad: bezi stack (tools/up.sh) a role su pridelene (tools/pfseed.py).

    python3 tools/majetokcheck.py
    python3 tools/majetokcheck.py --wipe

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
NET = "it/majetok/ma_zariadenie"
CARD = "it/majetok"
ROLE_USER_EMAIL = "admin@test.local"       # ucet, ktory ma rolu `spravca_majetku`
OTHER_USER_EMAIL = "operator@test.local"   # ucet, ktory ju NEMA, ale karty vidi

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
            self.token = e.headers.get("X-Auth-Token")
        except urllib.error.URLError:
            sys.exit(f"majetokcheck: engine na {URL} neodpoveda")
        if not self.token and not allow_fail:
            sys.exit(f"majetokcheck: prihlasenie {email} zlyhalo")

    def call(self, method, path, body=None, timeout=120):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"X-Auth-Token": self.token,
                   # Bez hal+json vracaju HATEOAS endpointy 406.
                   "Accept": "application/hal+json, application/json;q=0.9, */*;q=0.8"}
        if data:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(URL + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
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
        sys.exit(f"majetokcheck: siet {identifier} nie je naimportovana")
    refs.sort(key=lambda x: [int(n) for n in x["version"].split(".")])
    return refs[-1]


def new_case(cl, net_id):
    st, r = cl.post("/api/workflow/case", {"netId": net_id, "title": None, "color": ""})
    m = re.search(r"Case with id ([0-9a-f]{24})",
                  r.get("success", "") if isinstance(r, dict) else "")
    if not m:
        sys.exit(f"majetokcheck: zalozenie pripadu zlyhalo: {st} {str(r)[:300]}")
    st, c = cl.get(f"/api/workflow/case/{m.group(1)}")
    return m.group(1), c


def tasks_of(cl, case_id):
    """Ulohy, ktore uzivatel NAOZAJ vidi - `/api/task/case/{id}` opravnenia
    neoveruje a vrati vsetko kazdemu, kto pozna id."""
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
    print(f"majetokcheck: zmazanych {len(cases)} pripadov")


def uri_paths_deep(cl):
    """Vsetky karty, ktore ucet vidi - vratane tych v kategoriach.

    `/api/v2/uri/root` vracia len PRIAME deti korena, a odkedy appka zije
    v kategorii, je dietatom korena uz len ta kategoria. Test hladajuci kartu
    medzi detmi korena by preto zlyhal bez ohladu na to, ci appka funguje.
    Endpoint filtruje podla opravneni, takze vysledok je naozaj to, co ten
    ucet vidi.
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
    boss = Client("super@netgrif.com", SUPER_PASS)
    if "--wipe" in sys.argv:
        wipe(boss)
        return 0

    print("=== 1. karta v bocnom menu ===")
    user = Client(ROLE_USER_EMAIL, TEST_PASS)
    other = Client(OTHER_USER_EMAIL, TEST_PASS)
    for name, cl, expected in [("s rolou", user, True), ("bez roly", other, False)]:
        paths = uri_paths_deep(cl)
        check(f"{name} {'vidi' if expected else 'nevidi'} kartu '{CARD}'",
              (CARD in paths) == expected, paths)
        if not expected:
            # Bez tejto kontroly by test presel aj vtedy, keby ucet nevidel
            # ziadnu kartu - a nedokazoval by nic.
            check(f"{name} pritom ine karty vidi", len(paths) > 0, paths)

    print("\n=== 2. zobrazenia a stlpce ===")
    st, mi = boss.post("/api/workflow/case/search?size=300",
                       {"process": [{"identifier": "preference_filter_item"}]})
    items = {}
    for c in mi.get("_embedded", {}).get("cases", []):
        items.setdefault(c["title"], c["stringId"])

    def view_fields(title):
        st, tl = boss.get(f"/api/task/case/{items[title]}")
        vt = [t for t in (tl or []) if t["transitionId"] == "view"]
        return values(boss, vt[0]["stringId"]) if vt else {}

    for want in ["Evidencia zariadení", "Rozpísané"]:
        check(f"zobrazenie '{want}' existuje", want in items, sorted(items))
        if want not in items:
            continue
        v = view_fields(want)
        check(f"'{want}' ma predvolene stlpce", bool(v.get("default_headers")),
              v.get("default_headers"))
        # Stlpec z datoveho pola sa vykresli LEN ak je jeho siet v allowedNets:
        # ponuku stlpcov sklada CaseHeaderService z povolenych sieti a
        # `default_headers` v nej uniqueId iba vyhlada. Co nenajde, necha
        # prazdne a NIC nezaloguje.
        need = {h.rsplit("-", 1)[0] for h in (v.get("default_headers") or "").split(",")
                if h and not h.startswith("meta-")}
        have = set()
        if v.get("filter_case_id"):
            st, fc = boss.get(f"/api/workflow/case/{v['filter_case_id']}")
            for d in (fc.get("immediateData") or []):
                if d.get("allowedNets"):
                    have = set(d["allowedNets"])
        check(f"'{want}' ma v allowedNets siete svojich stlpcov", need <= have,
              f"treba {sorted(need)}, ma {sorted(have)}")

    st, mc = boss.post("/api/workflow/case/search?size=20",
                       {"process": [{"identifier": "it/majetok/ma_menu"}]})
    mt = [c["title"] for c in mc.get("_embedded", {}).get("cases", [])]
    check("bootstrap case menu hlasi 2/2", any("2/2" in t for t in mt), mt)

    print("\n=== 3. priebeh pripadu ===")
    net = newest_net(user, NET)
    print(f"  siet {net['identifier']} v{net['version']}")
    case_id, case = new_case(user, net["stringId"])
    check("nazov pripadu zacina stavom", case["title"].startswith("Rozpísané"), case["title"])
    t = tasks_of(user, case_id)
    check("na zaciatku je PRESNE jedna uloha", list(t) == ["t_ma_podanie"], list(t))
    podanie = t.get("t_ma_podanie")
    if not podanie:
        print("\nmajetokcheck: uloha podania sa nenasla")
        return 1

    # Prazdny predmet musi byt odmietnuty - a odmietnutie prichadza ako HTTP 200
    # s `error` v tele.
    set_data(user, podanie, {"ma_predmet": {"type": "text", "value": ""}})
    st, r = user.get(f"/api/task/finish/{podanie}")
    check("prazdny predmet je odmietnuty", isinstance(r, dict) and "error" in r, str(r)[:110])

    stamp = str(int(time.time()))
    predmet = f"Test {stamp}"
    set_data(user, podanie, {
        "ma_predmet": {"type": "text", "value": predmet},
        "ma_popis": {"type": "text", "value": "Popis z testu."}})
    st, r = user.get(f"/api/task/finish/{podanie}")
    check("DOKONCIT presiel", isinstance(r, dict) and "success" in r, str(r)[:110])

    t2 = tasks_of(user, case_id)
    check("po podani je PRESNE jedna uloha (prehlad)",
          list(t2) == ["t_ma_prehlad"], list(t2))
    if t2.get("t_ma_prehlad"):
        v = values(user, t2["t_ma_prehlad"])
        check("stav je 'Podané'", v.get("ma_stav_label") == "Podané",
              v.get("ma_stav_label"))
        check("je zapisane, kto podal", bool(v.get("ma_podal")),
              v.get("ma_podal"))
    st, c = user.get(f"/api/workflow/case/{case_id}")
    check("nazov pripadu zacina 'Podané'", c["title"].startswith("Podané"), c["title"])
    check("farba pripadu je zelena", c.get("color") == "green", c.get("color"))

    print("\n=== 4. zobrazenie 'Rozpísané' filtruje podla datoveho pola ===")
    q = f'processIdentifier:"{NET}" AND dataSet.ma_stav_label.textValue:"Rozpísané"'
    st, r = user.post("/api/workflow/case/search?size=100", {"query": q})
    ids = [x["stringId"] for x in (r.get("_embedded") or {}).get("cases", [])] \
        if isinstance(r, dict) else []
    check("podany pripad v 'Rozpísané' nie je", case_id not in ids, f"{len(ids)} pripadov")
    c2, _ = new_case(user, net["stringId"])
    st, r = user.post("/api/workflow/case/search?size=100", {"query": q})
    ids = [x["stringId"] for x in (r.get("_embedded") or {}).get("cases", [])] \
        if isinstance(r, dict) else []
    check("novy rozpisany pripad v 'Rozpísané' je", c2 in ids, f"{len(ids)} pripadov")

    print(f"\nmajetokcheck: {len(OK)} preslo, {len(FAIL)} zlyhalo")
    for f in FAIL:
        print("  ZLYHALO:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
