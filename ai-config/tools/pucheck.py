#!/usr/bin/env python3
"""
pucheck - akceptacny test appky Pouzivatelia proti BEZIACEMU enginu.

Model: JEDEN UCET = JEDEN PRIPAD.

  pouzivatelia/pu_zalozenie   jediny pripad, jedina uloha `t_pu_novy` = pult
                              na zakladanie. Po dokonceni sa SAM vyprazdni.
  pouzivatelia/pu_pouzivatel  pripad na ucet, sluckova uloha `t_pu_uprava`.

Preto tento test okrem funkcnosti overuje aj JEDINECNOST: ze zakladanie
nenechava po sebe rozpisane pripady a ze na jeden ucet je presne jeden pripad.
Predchadzajuci dizajn mal pripad na operaciu, takze sa dalo mat dvadsat
otvorenych "rozpisany ucet pre x@y.sk" - to je to, co sa tu testuje, aby sa
nevratilo.

Styri veci, na ktore sa tu naletelo a preto su v kode napisane:

  1. Telo `POST /api/task/{id}/data` je {taskId: {fieldId: {...}}}, NIE
     {fieldId: {...}}. Ploche telo vrati HTTP 200 s hlaskou "Could not find
     task with id [<fieldId>]" a ticho nezapise nic.
  2. Engine odmietnutie NEHLASI HTTP kodom - `finish` vrati 200 a dovod da do
     tela ako `error`. Test na status by taky blok prehliadol.
  3. `GET /api/auth/login` vrati 405, ale token uz je v hlavicke - autentifikacny
     filter bezi pred handlerom.
  4. Moznosti poli plnene za behu (`change ... options`) sa daju precitat len
     z `GET /api/task/{id}/data`, a to LEN ak je pole v `dataGroup` prechodu -
     inak ho ten endpoint nevracia vobec, ani skryte.

Predpoklad: bezi stack (tools/up.sh) a role su pridelene (tools/pfseed.py).

    python3 tools/pucheck.py
    python3 tools/pucheck.py --wipe    # zmaze pripady uctov aj testovacie ucty

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
NET_ZAL = "pouzivatelia/pu_zalozenie"
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

    def call(self, method, path, body=None, timeout=120):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"X-Auth-Token": self.token,
                   # Bez hal+json vracaju HATEOAS endpointy 406.
                   "Accept": "application/hal+json, application/json;q=0.9, */*;q=0.8",
                   # Locale, ktore engine nepozna => vrati `defaultValue`, teda
                   # to, co je v XML. Bez tejto hlavicky pouzije Spring locale
                   # JVM (tu `en`) a test porovnava slovenske ocakavania
                   # s anglickymi odpovedami.
                   "Accept-Language": "zz"}
        if data:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(URL + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = r.read().decode("utf-8")
                return r.status, (json.loads(text) if text else None)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    def get(self, p, timeout=120):
        return self.call("GET", p, timeout=timeout)

    def post(self, p, body=None, timeout=120):
        return self.call("POST", p, body, timeout=timeout)


def check(label, cond, detail=""):
    (OK if cond else FAIL).append(label)
    print(("  [OK]   " if cond else "  [ZLE] ") + label + ((" -- " + str(detail)) if detail else ""))


def cases_of(cl, identifier, size=300):
    st, r = cl.post(f"/api/workflow/case/search?size={size}",
                    {"process": [{"identifier": identifier}]})
    return (r.get("_embedded") or {}).get("cases", []) if isinstance(r, dict) else []


def tasks_by_transition(cl, transition):
    st, r = cl.post("/api/task/search?size=100", {"transitionId": [transition]})
    return (r.get("_embedded") or {}).get("tasks", []) if isinstance(r, dict) else []


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


def set_data(cl, task_id, vals, timeout=120):
    cl.get(f"/api/task/assign/{task_id}")
    return cl.call("POST", f"/api/task/{task_id}/data", {task_id: vals}, timeout=timeout)


def as_form_password(plain):
    """Heslo tak, ako ho posiela FORMULAR - teda v base64.

    Textove pole s `<component><name>password</name></component>` frontend pred
    odoslanim zakoduje (`FieldConverterService.formatValueForBackend`). Test,
    ktory posiela surovu hodnotu, je sam so sebou konzistentny a tuto chybu
    NEUVIDI - presne to sa stalo: test presiel a ucet zalozeny cez formular sa
    nedal prihlasit tym, co clovek napisal.

    Preto sa tu heslo posiela zakodovane a prihlasuje sa NEZAKODOVANYM - inak
    ten test nedokazuje to, na com zalezi.
    """
    return base64.b64encode(plain.encode("utf-8")).decode()


def release(boss, task_id):
    """Uvolni ulohu, ktoru drzi niekto iny.

    Pult je ZDIELANA uloha: `assignPolicy=manual`, takze ju drzi ten, kto si ju
    vzal, a nikto iny ju medzitym dokoncit nemoze - `finish` vrati
    "User that is not assigned tried to finish task". To je spravne chovanie
    frontu, nie chyba, a `cancel` je presne to, cim sa uloha vracia.

    Cancel smie iba jej drzitel - alebo administrator, ktoreho
    `canCallCancel` prepusti cez `isAdmin()`. Preto sa tu pouziva `super`.
    """
    boss.get(f"/api/task/cancel/{task_id}")


def roles_of(cl, user_id):
    st, u = cl.get(f"/api/user/{user_id}")
    if not isinstance(u, dict):
        return []
    return sorted({r.get("importId") for r in (u.get("processRoles") or [])} - {None})


MONGO_DELETE_TEST_USERS = """
var re = /^(pucheck|uscheck)\\.[0-9]+@test\\.local$/;
var victims = db.user.find({email: {$regex: re}}, {_id: 1, email: 1}).toArray();
var ids = victims.map(function (u) { return u._id; });
if (ids.length > 0) {
    db.user.deleteMany({_id: {$in: ids}});
}
print("PURGED " + ids.length);
"""


def mongo_eval(script):
    """Spusti mongosh - najprv v docker kontejneri, potom lokalne.

    To iste robi `pfseed --repair` a z toho isteho dovodu: engine na zmazanie
    uzivatela REST endpoint NEMA (`deleteUser` je len na ActionDelegate, teda
    dosiahnutelny z akcie siete). Bez tejto cesty by po kazdom behu testu
    v instancii zostal dalsi ucet a po tyzdni ich su desiatky.
    """
    import subprocess
    db = os.environ.get("PF_DB", "etask")
    container = os.environ.get("PF_MONGO_CONTAINER")
    candidates = []
    if container:
        candidates.append(["docker", "exec", container, "mongosh", "--quiet", db,
                           "--eval", script])
    else:
        try:
            out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                                 capture_output=True, text=True, timeout=20)
            for name in out.stdout.split():
                if "mongo" in name:
                    candidates.append(["docker", "exec", name, "mongosh", "--quiet", db,
                                       "--eval", script])
                    break
        except (OSError, subprocess.TimeoutExpired):
            pass
    candidates.append(["mongosh", "--quiet", db, "--eval", script])
    for cmd in candidates:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if res.returncode == 0:
            return res.stdout, None
    return None, "mongosh sa nepodarilo spustit (ani v kontejneri, ani lokalne)"


def wipe(cl):
    cs = cases_of(cl, NET)
    for c in cs:
        cl.call("DELETE", f"/api/workflow/case/{c['stringId']}")
    print(f"pucheck: zmazanych {len(cs)} pripadov uctov")

    # A aj samotne ucty. Kym to tento nastroj nerobil, kazdy beh nechal
    # v instancii dalsi `pucheck.<timestamp>@test.local` - po niekolkych dnoch
    # ich bolo v zozname uzivatelov viac nez skutocnych ludi a v konfiguracnych
    # obrazovkach sa vyberalo z odpadu.
    out, err = mongo_eval(MONGO_DELETE_TEST_USERS)
    if err:
        print(f"pucheck: ucty sa zmazat nepodarilo - {err}")
        print("pucheck: zmaz ich cez tools/up.sh --fresh")
        return
    line = [l for l in (out or "").splitlines() if l.startswith("PURGED")]
    count = int(line[0].split()[1]) if line else 0
    print(f"pucheck: zmazanych {count} testovacich uctov (pucheck.*, uscheck.*)")


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

    print("\n=== 2. karta a zobrazenia ===")
    for name, cl, expected in [("spravca", spravca, True), ("ina rola", iny, False)]:
        st, root = cl.get("/api/v2/uri/root")
        paths = [c["uriPath"] for c in root.get("children", [])]
        check(f"{name} {'vidi' if expected else 'nevidi'} kartu '{CARD}'",
              (CARD in paths) == expected, paths)
        if not expected:
            check(f"{name} pritom ine karty vidi (inak by test nic nedokazal)",
                  len(paths) > 0, paths)

    st, mi = boss.post("/api/workflow/case/search?size=300",
                       {"process": [{"identifier": "preference_filter_item"}]})
    items = {}
    for c in mi.get("_embedded", {}).get("cases", []):
        items.setdefault(c["title"], c["stringId"])

    def view_fields(title):
        st, tl = boss.get(f"/api/task/case/{items[title]}")
        vt = [t for t in (tl or []) if t["transitionId"] == "view"]
        return values(boss, vt[0]["stringId"]) if vt else {}

    for want in ["Nový používateľ", "Používatelia"]:
        check(f"zobrazenie '{want}' existuje", want in items, sorted(items))

    if "Nový používateľ" in items:
        v = view_fields("Nový používateľ")
        # Typ Task, zuzeny na jednu ulohu. Menu pozna len Case a Task
        # (`FilterType`), samostatny "single task" typ neexistuje.
        check("zakladanie je zobrazenie typu Task",
              (v.get("filter") or "").find("transitionId") >= 0, v.get("filter"))
        check("zakladanie mieri na t_pu_novy",
              "t_pu_novy" in (v.get("filter") or ""), v.get("filter"))

    WANT_HEADERS = ("meta-title,pouzivatelia/pu_pouzivatel-pu_stav_label"
                    ",pouzivatelia/pu_pouzivatel-pu_email"
                    ",pouzivatelia/pu_pouzivatel-pu_priezvisko")
    if "Používatelia" in items:
        v = view_fields("Používatelia")
        check("zoznam ma predvolene stlpce", v.get("default_headers") == WANT_HEADERS,
              v.get("default_headers"))
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
        check("zoznam ma v allowedNets siete svojich stlpcov", need <= have,
              f"treba {sorted(need)}, ma {sorted(have)}")

    print("\n=== 3. pult na zakladanie ===")
    zc = cases_of(boss, NET_ZAL)
    check("zakladacia siet ma PRESNE jeden pripad", len(zc) == 1,
          [c["title"] for c in zc])
    pult = tasks_by_transition(spravca, "t_pu_novy")
    check("pult je PRESNE jedna uloha", len(pult) == 1, [t["caseTitle"] for t in pult])
    if not pult:
        print("\npucheck: pult sa nenasiel, dalej sa testovat neda")
        return 1
    tid = pult[0]["stringId"]
    # Pult mohol zostat priradeny z predchadzajuceho behu alebo inemu adminovi.
    release(boss, tid)
    st, _ = spravca.get(f"/api/task/assign/{tid}")
    check("spravca si dokaze pult vziat", st == 200, st)

    procesy = options(spravca, tid, "zl_proces")
    check("ponuka procesov sa nacitala z instancie", len(procesy) > 0, sorted(procesy)[:3])
    check("v ponuke su len aplikacne siete", all("/" in k for k in procesy),
          sorted(procesy)[:3])
    # Pult je ZDIELANY pripad a drzi stav z predchadzajuceho behu, takze sa
    # najprv vynuluje. Prazdny proces = ziadne role, co je zaroven dokaz, ze
    # role visia na vybere procesu a nie su napisane v sieti.
    set_data(spravca, tid, {"zl_proces": {"type": "enumeration_map", "value": ""}})
    check("bez vybraneho procesu nie su ponuknute ziadne role",
          not options(spravca, tid, "zl_roly"), options(spravca, tid, "zl_roly"))

    proces = sorted(procesy)[0]
    set_data(spravca, tid, {"zl_proces": {"type": "enumeration_map", "value": proces}})
    roly = options(spravca, tid, "zl_roly")
    verzie = options(spravca, tid, "zl_verzia")
    check(f"po vybere procesu '{proces}' pribudli jeho role", len(roly) > 0, sorted(roly))
    check("kluc roly je cisty importId", all(":" not in k for k in roly), sorted(roly))
    check("prvou volbou verzie su vsetky verzie", "vsetky" in verzie, sorted(verzie)[:3])
    # Bodka v kluci moznosti zhodi ukladanie do Monga (petriflow_reference C17).
    check("kluce verzii nemaju bodku", all("." not in k for k in verzie), sorted(verzie)[:3])

    print("\n=== 4. co sa nesmie dat ===")
    stamp = str(int(time.time()))
    email = f"pucheck.{stamp}@test.local"
    heslo = "Pucheck!" + stamp
    rola = sorted(roly)[0]

    set_data(spravca, tid, {
        "zl_meno": {"type": "text", "value": "Test"},
        "zl_priezvisko": {"type": "text", "value": "Pucheck"},
        "zl_email": {"type": "text", "value": "toto nie je email"},
        "zl_heslo": {"type": "text", "value": as_form_password(heslo)}})
    st, r = spravca.get(f"/api/task/finish/{tid}")
    check("neplatny e-mail je odmietnuty", isinstance(r, dict) and "error" in r, str(r)[:110])

    set_data(spravca, tid, {"zl_email": {"type": "text", "value": "admin@test.local"}})
    st, r = spravca.get(f"/api/task/finish/{tid}")
    check("existujuci e-mail je odmietnuty", isinstance(r, dict) and "error" in r, str(r)[:110])

    set_data(spravca, tid, {
        "zl_email": {"type": "text", "value": email},
        "zl_authority": {"type": "multichoice_map", "value": ["ROLE_ADMIN"]}})
    st, r = spravca.get(f"/api/task/finish/{tid}")
    check("ucet bez ROLE_USER je odmietnuty", isinstance(r, dict) and "error" in r, str(r)[:110])
    check("odmietnutie vysvetli preco", "neuvidí" in str(r), str(r)[:160])

    print("\n=== 5. zalozenie uctu ===")
    pred = len(cases_of(boss, NET))
    set_data(spravca, tid, {
        "zl_authority": {"type": "multichoice_map", "value": ["ROLE_USER"]},
        "zl_verzia": {"type": "enumeration_map", "value": "vsetky"},
        "zl_roly": {"type": "multichoice_map", "value": [rola]}})
    set_data(spravca, tid, {"zl_pridaj": {"type": "button", "value": 0}})
    v = values(spravca, tid)
    check("tlacidlo pridalo rolu do zoznamu", rola in (v.get("zl_zoznam") or ""),
          repr(v.get("zl_zoznam")))
    check("po pridani je pole rolí prazdne (pripravene na dalsi proces)",
          not v.get("zl_roly"), v.get("zl_roly"))

    st, r = spravca.get(f"/api/task/finish/{tid}")
    check("DOKONCIT presiel", isinstance(r, dict) and "success" in r, str(r)[:130])

    # Pult sa musi vyprazdnit - inak by tu zostali data predchadzajuceho
    # cloveka vratane hesla, a to je presne to, co sa tu nema stat.
    pult2 = tasks_by_transition(spravca, "t_pu_novy")
    check("pult zostal PRESNE jeden (nezalozil sa druhy pripad)", len(pult2) == 1,
          len(pult2))
    tid2 = pult2[0]["stringId"]
    release(boss, tid2)
    spravca.get(f"/api/task/assign/{tid2}")
    v = values(spravca, tid2)
    check("pult sa vyprazdnil - e-mail", not (v.get("zl_email") or ""), repr(v.get("zl_email")))
    check("pult sa vyprazdnil - heslo", not (v.get("zl_heslo") or ""), repr(v.get("zl_heslo")))
    check("pult sa vyprazdnil - zoznam rolí", not (v.get("zl_zoznam") or ""),
          repr(v.get("zl_zoznam")))
    check("pult povie, co sa stalo", email in (v.get("zl_vysledok") or ""),
          (v.get("zl_vysledok") or "").replace("\n", " | ")[:150])

    print("\n=== 6. jeden ucet = jeden pripad ===")
    po = cases_of(boss, NET)
    check("pribudol PRESNE jeden pripad uctu", len(po) == pred + 1,
          f"pred {pred}, po {len(po)}")
    novy = [c for c in po if email in (c.get("title") or "")]
    check("pripad uctu je pomenovany menom a e-mailom", len(novy) == 1,
          [c["title"] for c in po[-3:]])
    if not novy:
        print("\npucheck: pripad uctu sa nenasiel")
        return 1
    case_id = novy[0]["stringId"]
    check("pripad uctu je zeleny (zviazany)", novy[0].get("color") == "green",
          novy[0].get("color"))
    t = tasks_of(spravca, case_id)
    check("pripad uctu ma PRESNE jednu ulohu", list(t) == ["t_pu_uprava"], list(t))
    uprava = t.get("t_pu_uprava")
    v = values(spravca, uprava)
    check("uloha uctu je zviazana s uctom", bool((v.get("pu_userid") or "").strip()),
          repr(v.get("pu_userid")))
    check("stav je 'Aktívny'", v.get("pu_stav_label") == "Aktívny", v.get("pu_stav_label"))
    check("uloha uctu si dotiahla e-mail z uctu", v.get("pu_email") == email,
          v.get("pu_email"))
    check("uloha uctu si dotiahla role z uctu", rola in (v.get("pu_zoznam") or ""),
          repr(v.get("pu_zoznam")))
    user_id = (v.get("pu_userid") or "").strip()

    # Ziadny druhy pripad na ten isty ucet.
    rovnake = [c for c in po
               if email in (c.get("title") or "")]
    check("na jeden ucet je PRESNE jeden pripad", len(rovnake) == 1, len(rovnake))

    print("\n=== 7. novy ucet sa naozaj prihlasi ===")
    ucet = Client(email, heslo, allow_fail=True)
    check("prihlasenie noveho uctu", bool(ucet.token), "bez tokenu" if not ucet.token else "ok")
    if ucet.token:
        st, me = ucet.get("/api/user/me")
        auth = [a.get("authority") if isinstance(a, dict) else a
                for a in (me.get("authorities") or [])] if isinstance(me, dict) else []
        check("ma ROLE_USER (bez toho by nevidel ziadne zobrazenie)",
              any("ROLE_USER" in str(a) for a in auth), auth)
        check("nie je administrator", not any("ROLE_ADMIN" in str(a) for a in auth), auth)
        check(f"ma pridelenu rolu '{rola}'", rola in roles_of(boss, user_id),
              roles_of(boss, user_id))

    print("\n=== 8. uprava uctu na jeho vlastnom pripade ===")
    nove_heslo = "Pucheck2!" + stamp
    set_data(spravca, uprava, {
        "pu_meno": {"type": "text", "value": "Upravene"},
        "pu_heslo": {"type": "text", "value": as_form_password(nove_heslo)}})
    set_data(spravca, uprava, {"pu_vycisti": {"type": "button", "value": 0}})
    st, r = spravca.get(f"/api/task/finish/{uprava}")
    check("uprava presla", isinstance(r, dict) and "success" in r, str(r)[:130])
    st, u = boss.get(f"/api/user/{user_id}")
    check("meno sa naozaj zmenilo", (u or {}).get("name") == "Upravene", (u or {}).get("name"))
    check("rola bola ODOBRANA (uprava nastavuje stav, nie priratava)",
          rola not in roles_of(boss, user_id), roles_of(boss, user_id))
    check("nove heslo funguje", bool(Client(email, nove_heslo, allow_fail=True).token))
    check("stare heslo uz nefunguje", not Client(email, heslo, allow_fail=True).token)
    # Bez tejto kontroly by prehliadlo, ze sa zahashovalo base64 namiesto hesla.
    check("base64 podoba hesla sa prihlasit NEDA",
          not Client(email, as_form_password(nove_heslo), allow_fail=True).token)
    check("uprava sa da spustit znova (slucka)",
          "t_pu_uprava" in tasks_of(spravca, case_id), list(tasks_of(spravca, case_id)))
    check("pripad uctu je stale jeden", len([c for c in cases_of(boss, NET)
                                             if email in (c.get("title") or "")]) == 1)

    print("\n=== 9. pripad z tlacidla + je nezviazany a neda sa dokoncit ===")
    st, nets = spravca.post("/api/petrinet/search?size=100", {"identifier": NET})
    refs = [x for x in nets["_embedded"]["petriNetReferences"] if x["identifier"] == NET]
    refs.sort(key=lambda x: [int(n) for n in x["version"].split(".")])
    st, r = spravca.post("/api/workflow/case",
                         {"netId": refs[-1]["stringId"], "title": None, "color": ""})
    m = re.search(r"Case with id ([0-9a-f]{24})",
                  r.get("success", "") if isinstance(r, dict) else "")
    check("prazdny pripad sa da zalozit (tlacidlo + v zozname)", bool(m), str(r)[:120])
    if m:
        orphan = m.group(1)
        st, oc = spravca.get(f"/api/workflow/case/{orphan}")
        check("nezviazany pripad je cerveny", oc.get("color") == "red", oc.get("color"))
        ot = tasks_of(spravca, orphan).get("t_pu_uprava")
        ov = values(spravca, ot) if ot else {}
        check("nezviazany pripad povie, ze nema ucet",
              "nie je zviazaný" in (ov.get("pu_vysledok") or ""),
              (ov.get("pu_vysledok") or "").replace("\n", " | ")[:110])
        if ot:
            spravca.get(f"/api/task/assign/{ot}")
            st, r = spravca.get(f"/api/task/finish/{ot}")
            check("nezviazany pripad sa NEDA dokoncit",
                  isinstance(r, dict) and "error" in r, str(r)[:120])
        spravca.call("DELETE", f"/api/workflow/case/{orphan}")

    print("\n=== 10. zosuladenie existujucich uctov ===")
    st, r = boss.post("/api/user/search?size=300", {"fulltext": ""})
    # `zl_sync` je idempotentne - druhy beh nesmie nic pridat. Meria sa preto
    # DRUHY beh, nie prvy: co doplni prvy, zavisi od toho, co po sebe nechal
    # predchadzajuci beh (alebo `--wipe`, ktory maze pripady, nie ucty). Kym
    # test cital prvy beh, hlasil chybu podla historie prostredia, nie podla
    # appky - a zelena znamenala len to, ze zosuladenie uz niekto spustil.
    set_data(spravca, tid2, {"zl_sync": {"type": "button", "value": 0}}, timeout=180)
    pocet_pred = len(cases_of(boss, NET))
    set_data(spravca, tid2, {"zl_sync": {"type": "button", "value": 0}}, timeout=180)
    v1 = values(spravca, tid2).get("zl_vysledok") or ""
    check("druhe zosuladenie uz nic nedoplni",
          "nič nebolo treba doplniť" in v1, v1.replace("\n", " | ")[:140])
    check("zosuladenie je idempotentne", len(cases_of(boss, NET)) == pocet_pred,
          f"{pocet_pred} -> {len(cases_of(boss, NET))}")
    titles = [c.get("title") or "" for c in cases_of(boss, NET)]
    check("systemove ucty enginu pripad nemaju",
          not any("anonymous.nae" in t or "engine@netgrif.com" in t for t in titles),
          [t for t in titles if "anonymous" in t or "engine@" in t])
    for kto in ["super@netgrif.com", "admin@test.local", "operator@test.local"]:
        check(f"existujuci ucet {kto} ma svoj pripad",
              any(kto in t for t in titles))

    # Uvolnit pult, aby dalsi beh (alebo clovek v prehliadaci) nenarazil na
    # ulohu drzanu testom.
    for t in tasks_by_transition(boss, "t_pu_novy"):
        release(boss, t["stringId"])

    print(f"\npucheck: {len(OK)} preslo, {len(FAIL)} zlyhalo")
    for f in FAIL:
        print("  ZLYHALO:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
