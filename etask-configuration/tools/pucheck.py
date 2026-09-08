#!/usr/bin/env python3
"""
pucheck - akceptacny test appky Pouzivatelia proti BEZIACEMU enginu.

Overuje to, co sa z XML ani z importu zistit neda: ze sa cez proces naozaj
zaloz ucet, ze sa PRIHLASI, ze ma systemove authorities (bez nich sa prihlasi
a nevidi nic), ze mu sedia procesne role - a ze sa uz existujuci ucet da
UPRAVIT, vratane odobrania roly a zmeny hesla.

Styri veci, na ktore sa tu naletelo a preto su v kode napisane:

  1. Telo `POST /api/task/{id}/data` je {taskId: {fieldId: {...}}}, NIE
     {fieldId: {...}}. Ploche telo vrati HTTP 200 s hlaskou "Could not find
     task with id [<fieldId>]" a ticho nezapise nic.
  2. Engine odmietnutie NEHLASI HTTP kodom - `finish` vrati 200 a dovod da do
     tela ako `error`. Test na status by taky blok prehliadol.
  3. `GET /api/auth/login` vrati 405, ale token uz je v hlavicke - autentifikacny
     filter bezi pred handlerom.
  4. Moznosti poli plnene za behu (`change ... options`) sa daju precitat len
     z `GET /api/task/{id}/data`, nie zo siete - preto sa dvojkrokovy vyber
     (proces -> role) testuje cez task, nie cez XML.

Predpoklad: bezi stack (tools/up.sh) a role su pridelene (tools/pfseed.py).

    python3 tools/pucheck.py
    python3 tools/pucheck.py --wipe    # zmaze casy appky

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
NET = "pouzivatelia/pu_pouzivatel"
CARD = "pouzivatelia"

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
            sys.exit(f"pucheck: engine na {URL} neodpoveda")
        if not self.token and not allow_fail:
            sys.exit(f"pucheck: prihlasenie {email} zlyhalo")

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
        sys.exit(f"pucheck: siet {identifier} nie je naimportovana")
    refs.sort(key=lambda x: [int(n) for n in x["version"].split(".")])
    return refs[-1]


def new_case(cl, net_id):
    """(caseId, case). Odpoved nesie id len v texte `success`."""
    st, r = cl.post("/api/workflow/case", {"netId": net_id, "title": None, "color": ""})
    m = re.search(r"Case with id ([0-9a-f]{24})", r.get("success", "") if isinstance(r, dict) else "")
    if not m:
        sys.exit(f"pucheck: zalozenie casu zlyhalo: {st} {str(r)[:300]}")
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


def options(cl, task_id, field):
    f = field_map(cl, task_id).get(field) or {}
    return f.get("options") or f.get("choices") or {}


def set_data(cl, task_id, vals):
    cl.get(f"/api/task/assign/{task_id}")
    return cl.post(f"/api/task/{task_id}/data", {task_id: vals})


def wipe(cl):
    st, r = cl.post("/api/workflow/case/search?size=500", {"process": [{"identifier": NET}]})
    cases = (r.get("_embedded") or {}).get("cases", [])
    for c in cases:
        cl.call("DELETE", f"/api/workflow/case/{c['stringId']}")
    print(f"pucheck: zmazanych {len(cases)} casov {NET}")
    print("pucheck: ucty z testov zostavaju - mazanie uzivatela cez REST engine "
          "nema, zmaz ich cez tools/up.sh --fresh")


def roles_of(cl, user_id):
    st, u = cl.get(f"/api/user/{user_id}")
    if not isinstance(u, dict):
        return []
    return sorted({r.get("importId") for r in (u.get("processRoles") or [])} - {None})


def main():
    boss = Client("super@netgrif.com", SUPER_PASS)
    if "--wipe" in sys.argv:
        wipe(boss)
        return 0

    print("=== 1. prihlasenie ===")
    spravca = Client("admin@test.local", TEST_PASS)      # ma rolu spravca
    # NIE viewer@test.local: ten nema ziadnu rolu a nevidi ZIADNU kartu, takze
    # "nevidi pouzivatelia" by preslo aj keby bola karta zle zabezpecena.
    # operator ma rolu `specialist` a nejake karty vidi - preto je jeho slepota
    # prave na tejto karte dokazom, ze `requiredProcessRoles` funguje.
    iny = Client("operator@test.local", TEST_PASS)
    print("  admin (spravca) / operator (specialist, nie spravca)")

    print("\n=== 2. karta v bocnom menu ===")
    for name, cl, expected in [("spravca", spravca, True), ("ina rola", iny, False)]:
        st, root = cl.get("/api/v2/uri/root")
        paths = [c["uriPath"] for c in root.get("children", [])]
        check(f"{name} {'vidi' if expected else 'nevidi'} kartu '{CARD}'",
              (CARD in paths) == expected, paths)
        if not expected:
            check(f"{name} pritom ine karty vidi (inak by test nic nedokazal)",
                  len(paths) > 0, paths)
    st, node = spravca.get("/api/v2/uri/" + base64.b64encode(CARD.encode()).decode())
    check("karta ma ikonu manage_accounts", node.get("icon") == "manage_accounts", node.get("icon"))
    check("stara karta 'uzivatelia' uz neexistuje",
          "uzivatelia" not in [c["uriPath"] for c in
                               (spravca.get("/api/v2/uri/root")[1].get("children") or [])])

    print("\n=== 3. zobrazenia pod kartou ===")
    st, mi = boss.post("/api/workflow/case/search?size=300",
                       {"process": [{"identifier": "preference_filter_item"}]})
    items = {}
    for c in mi.get("_embedded", {}).get("cases", []):
        items.setdefault(c["title"], c["stringId"])
    WANT_HEADERS = ("meta-title,pouzivatelia/pu_pouzivatel-pu_stav_label"
                    ",pouzivatelia/pu_pouzivatel-pu_email"
                    ",pouzivatelia/pu_pouzivatel-pu_priezvisko")

    def view_fields(title):
        st, tl = boss.get(f"/api/task/case/{items[title]}")
        vt = [t for t in (tl or []) if t["transitionId"] == "view"]
        return values(boss, vt[0]["stringId"]) if vt else {}

    for want in ["Používatelia", "Rozpísané"]:
        check(f"zobrazenie '{want}' existuje", want in items, sorted(items))
        if want not in items:
            continue
        v = view_fields(want)
        check(f"'{want}' ma predvolene stlpce", v.get("default_headers") == WANT_HEADERS,
              v.get("default_headers"))
        check(f"'{want}' sa nepyta na nazov pripadu",
              v.get("enable_case_title") is False, v.get("enable_case_title"))
        # Stlpec z datoveho pola sa vykresli len ak je jeho siet v allowedNets:
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
                       {"process": [{"identifier": "pouzivatelia/pu_menu"}]})
    mt = [c["title"] for c in mc.get("_embedded", {}).get("cases", [])]
    check("bootstrap case menu hlasi 2/2", any("2/2" in t for t in mt), mt)

    print("\n=== 4. dvojkrokovy vyber rolí ===")
    net = newest_net(spravca, NET)
    print(f"  siet {net['identifier']} v{net['version']}")
    case_id, case = new_case(spravca, net["stringId"])
    check("nazov casu zacina stavom", case["title"].startswith("Rozpísaný"), case["title"])
    t = tasks_of(spravca, case_id)
    check("spravca ma PRESNE jednu ulohu", list(t) == ["t_pu_zadanie"], list(t))
    zadanie = t["t_pu_zadanie"]
    spravca.get(f"/api/task/assign/{zadanie}")

    procesy = options(spravca, zadanie, "pu_proces")
    check("ponuka procesov sa nacitala z instancie", len(procesy) > 0, sorted(procesy)[:4])
    check("v ponuke procesov su len aplikacne siete",
          all("/" in k for k in procesy), sorted(procesy)[:4])
    check("systemove siete enginu sa neponukaju",
          not any(k in ("filter", "preference_filter_item") for k in procesy))
    check("role este ponuknute nie su (vyber ma dva kroky)",
          not options(spravca, zadanie, "pu_roly"))

    # Krok 1: proces. Krok 2 (role a verzie) doplni `set` akcia toho pola.
    proces = sorted(procesy)[0]
    set_data(spravca, zadanie, {"pu_proces": {"type": "enumeration_map", "value": proces}})
    roly = options(spravca, zadanie, "pu_roly")
    verzie = options(spravca, zadanie, "pu_verzia")
    check(f"po vybere procesu '{proces}' pribudli jeho role", len(roly) > 0, sorted(roly))
    check("kluc roly je cisty importId, bez ':' a bez siete",
          all(":" not in k for k in roly), sorted(roly))
    check("vstavane role default/anonymous sa neponukaju",
          not ({"default", "anonymous"} & set(roly)), sorted(roly))
    check("pribudli aj verzie procesu", len(verzie) > 0, verzie)
    check("prvou volbou verzie su vsetky verzie", "vsetky" in verzie, verzie)
    # Bodka v kluci moznosti zhodi ukladanie do Monga (petriflow_reference C17),
    # a verzie su "1.0.0" - preto musia byt zaslugovane.
    check("kluce verzii nemaju bodku (inak Mongo neulozi options)",
          all("." not in k for k in verzie), verzie)
    check("popis verzie bodky ma (slug je len kluc)",
          any("." in str(v) for k, v in verzie.items() if k != "vsetky"), verzie)

    print("\n=== 5. co sa nesmie dat ===")
    stamp = str(int(time.time()))
    email = f"pucheck.{stamp}@test.local"
    heslo = "Pucheck!" + stamp
    rola = sorted(roly)[0]

    set_data(spravca, zadanie, {
        "pu_meno": {"type": "text", "value": "Test"},
        "pu_priezvisko": {"type": "text", "value": "Pucheck"},
        "pu_email": {"type": "text", "value": "toto nie je email"},
        "pu_heslo": {"type": "text", "value": heslo}})
    st, r = spravca.get(f"/api/task/finish/{zadanie}")
    check("neplatny e-mail je odmietnuty", isinstance(r, dict) and "error" in r, str(r)[:120])

    set_data(spravca, zadanie, {"pu_email": {"type": "text", "value": "admin@test.local"}})
    st, r = spravca.get(f"/api/task/finish/{zadanie}")
    check("existujuci e-mail je odmietnuty", isinstance(r, dict) and "error" in r, str(r)[:120])
    check("odmietnutie povie ktory", "už existuje" in str(r), str(r)[:150])

    set_data(spravca, zadanie, {
        "pu_email": {"type": "text", "value": email},
        "pu_authority": {"type": "multichoice_map", "value": ["ROLE_ADMIN"]}})
    st, r = spravca.get(f"/api/task/finish/{zadanie}")
    check("ucet bez ROLE_USER je odmietnuty", isinstance(r, dict) and "error" in r, str(r)[:120])
    check("odmietnutie vysvetli preco", "neuvidí" in str(r), str(r)[:170])
    check("case stale caka na zadanie", "t_pu_zadanie" in tasks_of(spravca, case_id))

    print("\n=== 6. zalozenie uctu s rolou z vybraneho procesu ===")
    verzia = sorted([k for k in verzie if k != "vsetky"])[0] if len(verzie) > 1 else "vsetky"
    set_data(spravca, zadanie, {
        "pu_authority": {"type": "multichoice_map", "value": ["ROLE_USER"]},
        "pu_verzia": {"type": "enumeration_map", "value": verzia},
        "pu_roly": {"type": "multichoice_map", "value": [rola]}})
    # Tlacidlo naberie vybrane role do zoznamu. Bez neho by vyber druheho
    # procesu ten prvy prepisal.
    set_data(spravca, zadanie, {"pu_pridaj": {"type": "button", "value": 0}})
    v = values(spravca, zadanie)
    check("tlacidlo pridalo rolu do zoznamu", rola in (v.get("pu_zoznam") or ""),
          repr(v.get("pu_zoznam")))
    check("zoznam nesie aj siet a verziu",
          (v.get("pu_zoznam") or "").count("|") >= 2, repr(v.get("pu_zoznam")))
    check("citatelny prehlad zoznamu sa naplnil",
          rola in (v.get("pu_pridelene") or ""), repr(v.get("pu_pridelene")))
    check("po pridani je pole rolí prazdne (pripravene na dalsi proces)",
          not v.get("pu_roly"), v.get("pu_roly"))

    st, r = spravca.get(f"/api/task/finish/{zadanie}")
    check("DOKONCIT presiel", isinstance(r, dict) and "success" in r, str(r)[:150])

    te = tasks_of(spravca, case_id)
    check("po zalozeni ma spravca PRESNE jednu ulohu (uprava)",
          list(te) == ["t_pu_uprava"], list(te))
    uprava = te.get("t_pu_uprava")
    v = values(spravca, uprava) if uprava else {}
    check("stav je 'Hotový'", v.get("pu_stav_label") == "Hotový", v.get("pu_stav_label"))
    check("heslo je z pripadu zmazane", not (v.get("pu_heslo") or ""), repr(v.get("pu_heslo")))
    check("vysledok popisuje, co sa stalo", email in (v.get("pu_vysledok") or ""),
          (v.get("pu_vysledok") or "").replace("\n", " | "))
    st, c = spravca.get(f"/api/workflow/case/{case_id}")
    check("farba casu je zelena", c.get("color") == "green", c.get("color"))

    print("\n=== 7. novy ucet sa naozaj prihlasi ===")
    novy = Client(email, heslo, allow_fail=True)
    check("prihlasenie noveho uctu", bool(novy.token), "bez tokenu" if not novy.token else "ok")
    user_id = None
    if novy.token:
        st, me = novy.get("/api/user/me")
        user_id = me.get("id") or me.get("stringId") if isinstance(me, dict) else None
        auth = [a.get("authority") if isinstance(a, dict) else a
                for a in (me.get("authorities") or [])] if isinstance(me, dict) else []
        check("ma ROLE_USER (bez toho by nevidel ziadne zobrazenie)",
              any("ROLE_USER" in str(a) for a in auth), auth)
        check("nie je administrator", not any("ROLE_ADMIN" in str(a) for a in auth), auth)
        roles = [r.get("importId") for r in (me.get("processRoles") or [])] \
            if isinstance(me, dict) else []
        check(f"ma pridelenu rolu '{rola}' z vybraneho procesu", rola in roles, roles)

    print("\n=== 8. uprava uctu ===")
    check("uprava je dostupna ako opakovatelna uloha", bool(uprava), te)
    if uprava and user_id:
        spravca.get(f"/api/task/assign/{uprava}")
        v = values(spravca, uprava)
        check("uprava predvyplnila e-mail zo skutocneho stavu",
              v.get("pu_email") == email, v.get("pu_email"))
        check("uprava predvyplnila zoznam rolí", rola in (v.get("pu_zoznam") or ""),
              repr(v.get("pu_zoznam")))

        # Zmena mena + odobranie roly (vycistenim zoznamu) + nove heslo.
        nove_heslo = "Pucheck2!" + stamp
        set_data(spravca, uprava, {
            "pu_meno": {"type": "text", "value": "Upravene"},
            "pu_priezvisko": {"type": "text", "value": "Priezvisko"},
            "pu_heslo": {"type": "text", "value": nove_heslo}})
        set_data(spravca, uprava, {"pu_vycisti": {"type": "button", "value": 0}})
        check("vycistenie vyprazdnilo zoznam",
              not (values(spravca, uprava).get("pu_zoznam") or ""),
              repr(values(spravca, uprava).get("pu_zoznam")))
        st, r = spravca.get(f"/api/task/finish/{uprava}")
        check("uprava presla", isinstance(r, dict) and "success" in r, str(r)[:150])

        st, u = boss.get(f"/api/user/{user_id}")
        check("meno sa naozaj zmenilo", (u or {}).get("name") == "Upravene",
              (u or {}).get("name"))
        check("rola bola ODOBRANA (uprava nastavuje stav, nie priratava)",
              rola not in roles_of(boss, user_id), roles_of(boss, user_id))
        check("nove heslo funguje", bool(Client(email, nove_heslo, allow_fail=True).token))
        check("stare heslo uz nefunguje",
              not Client(email, heslo, allow_fail=True).token)

        t2 = tasks_of(spravca, case_id)
        check("uprava sa da spustit znova (slucka)", "t_pu_uprava" in t2, list(t2))

    print("\n=== 9. zobrazenie 'Rozpísané' filtruje podla datoveho pola ===")
    q = (f'processIdentifier:"{NET}" AND dataSet.pu_stav_label.textValue:"Rozpísaný"')
    st, r = spravca.post("/api/workflow/case/search?size=100", {"query": q})
    ids = [x["stringId"] for x in (r.get("_embedded") or {}).get("cases", [])] \
        if isinstance(r, dict) else []
    check("hotovy case v 'Rozpísané' nie je", case_id not in ids, f"{len(ids)} casov")
    c2, _ = new_case(spravca, net["stringId"])
    st, r = spravca.post("/api/workflow/case/search?size=100", {"query": q})
    ids = [x["stringId"] for x in (r.get("_embedded") or {}).get("cases", [])] \
        if isinstance(r, dict) else []
    check("novy rozpisany case v 'Rozpísané' je", c2 in ids, f"{len(ids)} casov")

    print(f"\npucheck: {len(OK)} preslo, {len(FAIL)} zlyhalo")
    for f in FAIL:
        print("  ZLYHALO:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
