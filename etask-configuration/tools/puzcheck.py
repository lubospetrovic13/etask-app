#!/usr/bin/env python3
"""
puzcheck - akceptacny test POZVANKOVEJ REGISTRACIE proti beziacemu enginu.

Co sa tu overuje (a preco prave to):

  1. Spravca ma pult `t_pu_pozvi`, iny clovek ho nema.
  2. Pozvanie zaklada ucet v stave INVITED - teda BEZ HESLA. Test to dokazuje
     tym, ze sa tym uctom NEDA prihlasit, nie tym, ze mu verí engine na slovo.
  3. Mail naozaj odide (Mailpit) a je to NAS mail - vlastna sablona, vlastny
     predmet, nie "Registration invite" z jaru.
  4. ODKAZ V MAILI VEDIE NA EXISTUJUCU ROUTU. To je ta kontrola, kvoli ktorej
     tento subor vznikol: enginova sablona ma `${server}/signup/${token}`,
     lenze `encodeToken` je STANDARDNE Base64 a token bezne obsahuje `/` -
     v segmente cesty by rozbil routu zhruba polovici pozvanych. Test preto
     porovnava cestu z mailu proti routam deklarovanym v `nae.json` a overuje,
     ze token z odkazu enginu naozaj prejde cez `/api/auth/token/verify`.
  5. Role pridelene pri pozvani PREZIJU registraciu. `registerUser` dopisuje
     len meno, priezvisko a heslo, ale je to implementacny detail enginu -
     keby sa zmenil, clovek by sa po registracii prihlasil do prazdneho
     dashboardu a nikde by sa to neohlasilo.
  6. Ucet ma po registracii svoj pripad v `pu_pouzivatel` a ten hlasi spravny
     stav (Pozvany -> Aktivny).
  7. Obnova hesla: `/api/auth/reset` -> mail -> `/api/auth/recover` -> stare
     heslo NEFUNGUJE, nove ano. A `/api/auth/reset` neprezradi, ci ucet
     existuje - odpoved je rovnaka pre existujucu aj vymyslenu adresu.

Predpoklad: bezi stack (tools/up.sh --docker) vratane Mailpitu,
role su pridelene (tools/pfseed.py).

    python3 tools/puzcheck.py
    python3 tools/puzcheck.py --wipe    # zmaze testovacie ucty a ich pripady

Test ZAKLADA UZIVATELOV a CITA MAILY - nespustat proti produkcii.

Exit 0 = vsetko preslo, 1 = nieco zlyhalo.
"""

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

URL = os.environ.get("PF_URL", "http://127.0.0.1:8080")
MAILPIT = os.environ.get("PF_MAILPIT", "http://127.0.0.1:8025")
TEST_PASS = os.environ.get("ETASK_TEST_PASSWORD", "test1234")
SUPER_PASS = os.environ.get("PF_PASS", "password")
NAE_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "..", "etask-frontend-starter", "nae.json")

NET = "admin/pouzivatelia/pu_pouzivatel"
NET_ZAL = "admin/pouzivatelia/pu_zalozenie"

# Rola, ktorou sa overuje, ze pozvanie role naozaj prideluje a ze prezije
# registraciu. `zamestnanec` na dovolenkach: existuje v kazdej instancii, ktora
# ma nainstalovanu aspon jednu appku, a viaze sa na kartu, ktoru vidno.
ROLA = os.environ.get("PF_ROLA", "zamestnanec")
ROLA_SIET = os.environ.get("PF_ROLA_SIET", "hr/dovolenky/dv_ziadost")

OK, FAIL = [], []


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Client:
    """Prihlaseny klient. `allow_fail=True` znamena, ze neuspesne prihlasenie
    NIE JE chyba testu - pouziva sa tam, kde sa dokazuje, ze sa prihlasit
    nema (ucet v stave INVITED, stare heslo po obnove)."""

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
            # 405, ale token uz je v hlavicke - autentifikacny filter bezi
            # pred handlerom. Preto sa na stavovy kod tu spoliehat NEDA.
            self.token = e.headers.get("X-Auth-Token")
        except urllib.error.URLError:
            sys.exit(f"puzcheck: engine na {URL} neodpoveda")
        if not self.token and not allow_fail:
            sys.exit(f"puzcheck: prihlasenie {email} zlyhalo")

    def call(self, method, path, body=None, timeout=120, raw=None, ctype=None):
        if raw is not None:
            data = raw.encode("utf-8")
        else:
            data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/hal+json, application/json;q=0.9, */*;q=0.8",
                   # Locale, ktore engine nepozna => vrati `defaultValue`, teda
                   # to, co je v XML. Bez toho porovnava test slovenske
                   # ocakavania s anglickymi odpovedami.
                   "Accept-Language": "zz"}
        if self.token:
            headers["X-Auth-Token"] = self.token
        if data:
            headers["Content-Type"] = ctype or "application/json"
        req = urllib.request.Request(URL + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = r.read().decode("utf-8")
                return r.status, (json.loads(text) if text else None)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(body_text)
            except ValueError:
                return e.code, body_text

    def get(self, p, timeout=120):
        return self.call("GET", p, timeout=timeout)

    def post(self, p, body=None, timeout=120, raw=None, ctype=None):
        return self.call("POST", p, body, timeout=timeout, raw=raw, ctype=ctype)


def anon():
    """Klient BEZ prihlasenia - registracne endpointy musia ist aj tak."""
    c = Client.__new__(Client)
    c.email = None
    c.token = None
    return c


def check(label, cond, detail=""):
    (OK if cond else FAIL).append(label)
    print(("  [OK]   " if cond else "  [ZLE] ") + label +
          ((" -- " + str(detail)) if detail else ""))


# --------------------------------------------------------------------------
# Petriflow
# --------------------------------------------------------------------------

def tasks_by_transition(cl, transition):
    st, r = cl.post("/api/task/search?size=100", {"transitionId": [transition]})
    return (r.get("_embedded") or {}).get("tasks", []) if isinstance(r, dict) else []


def cases_of(cl, identifier, size=300):
    st, r = cl.post(f"/api/workflow/case/search?size={size}",
                    {"process": [{"identifier": identifier}]})
    return (r.get("_embedded") or {}).get("cases", []) if isinstance(r, dict) else []


def tasks_of(cl, case_id):
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


def set_data(cl, task_id, vals, timeout=120):
    # Telo je {taskId: {fieldId: {...}}}. Ploche telo vrati 200 a ticho
    # nezapise nic - preto sa tu nikdy neposiela `vals` priamo.
    cl.get(f"/api/task/assign/{task_id}")
    return cl.call("POST", f"/api/task/{task_id}/data", {task_id: vals}, timeout=timeout)


def release(boss, task_id):
    """Uvolni zdielanu ulohu. Smie ju uvolnit jej drzitel alebo admin."""
    boss.get(f"/api/task/cancel/{task_id}")


def odosli(cl, task_id):
    """Stlaci tlacidlo `poz_odoslat`.

    Pozvanie NIE JE dokoncenie ulohy - pult je trvale otvoreny a pozyva sa
    opakovane, takze akcia visi na datovom tlacidle. `finish` je na tomto
    prechode zakazany a jeho tlacidlo schovane; test to overuje zvlast.
    """
    return set_data(cl, task_id, {"poz_odoslat": {"type": "button", "value": 0}})


def user_by_email(boss, email):
    """POZOR: najde len AKTIVNY ucet.

    `UserService.buildPredicate` ma v podmienke `state.eq(UserState.ACTIVE)`,
    takze `/api/user/search` ucet v stave INVITED ani BLOCKED NEVRATI - z REST
    API sa teda pozvany clovek neda najst vobec. Preto sa id pozvaneho uctu
    v tomto teste cita z jeho PRIPADU (`user_id_from_case`), nie odtialto.
    """
    st, r = boss.post("/api/user/search?size=50", {"fulltext": email})
    users = (r.get("_embedded") or {}).get("users", []) if isinstance(r, dict) else []
    for u in users:
        if (u.get("email") or "").lower() == email.lower():
            return u
    return None


def case_by_email(boss, email):
    for c in cases_of(boss, NET):
        if email.lower() in (c.get("title") or "").lower():
            return c
    return None


def roles_of(boss, user_id):
    st, u = boss.get(f"/api/user/{user_id}")
    if not isinstance(u, dict):
        return []
    return sorted({r.get("importId") for r in (u.get("processRoles") or [])} - {None})


# --------------------------------------------------------------------------
# Mailpit
# --------------------------------------------------------------------------

def mail_api(path, method="GET"):
    req = urllib.request.Request(MAILPIT + path, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read().decode("utf-8")
            return json.loads(text) if text else None
    except urllib.error.URLError:
        return None


def wait_for_mail(address, since_id=None, timeout=25):
    """Pocka na mail pre danu adresu a vrati jeho telo.

    Posiela sa VNUTRI transakcie, ktora dokoncuje ulohu, takze v case, ked
    `finish` vrati odpoved, uz mail spravidla v Mailpite je - ale SMTP je
    siet a cakanie je lacnejsie nez blikajuci test.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        lst = mail_api("/api/v1/messages?limit=50") or {}
        for m in lst.get("messages", []):
            if m["ID"] == since_id:
                break
            to = [t.get("Address", "").lower() for t in (m.get("To") or [])]
            if address.lower() in to:
                detail = mail_api("/api/v1/message/" + m["ID"]) or {}
                return m, detail
        time.sleep(1)
    return None, None


def newest_mail_id():
    lst = mail_api("/api/v1/messages?limit=1") or {}
    msgs = lst.get("messages", [])
    return msgs[0]["ID"] if msgs else None


def links_in(detail, needle):
    """Odkazy z HTML tela mailu, ktore obsahuju `needle`."""
    html = (detail or {}).get("HTML") or ""
    return [h for h in re.findall(r'href="([^"]+)"', html) if needle in h]


# --------------------------------------------------------------------------
# nae.json
# --------------------------------------------------------------------------

def frontend_routes():
    """Cesty verejnych routov deklarovanych vo frontende.

    Toto je jediny sposob, ako sa da odkaz z mailu overit staticky: SPA
    fallback vracia `index.html` na KAZDU cestu, takze HTTP test na
    `/signup?token=...` by vratil 200 aj keby ziadna taka routa neexistovala
    a clovek by videl prazdnu obrazovku.
    """
    try:
        with open(os.path.normpath(NAE_JSON), encoding="utf-8") as fh:
            cfg = json.load(fh)
    except OSError:
        return None
    out = []
    for name, view in (cfg.get("views") or {}).items():
        path = ((view.get("routing") or {}).get("path") or "").strip("/")
        if path:
            out.append((path, view.get("access")))
    return out


def route_matches(path, routes):
    """Sedi cesta z odkazu na niektoru deklarovanu routu?"""
    segs = [s for s in path.strip("/").split("/") if s]
    for route, access in routes:
        rsegs = [s for s in route.split("/") if s]
        if len(rsegs) != len(segs):
            continue
        if all(r.startswith(":") or r == s for r, s in zip(rsegs, segs)):
            return route, access
    return None, None


# --------------------------------------------------------------------------

MONGO_DELETE_TEST_USERS = """
var re = /^puzcheck\\.[0-9]+@test\\.local$/;
var victims = db.user.find({email: {$regex: re}}, {_id: 1}).toArray();
var ids = victims.map(function (u) { return u._id; });
if (ids.length > 0) { db.user.deleteMany({_id: {$in: ids}}); }
print("PURGED " + ids.length);
"""


def mongo_eval(script):
    """Engine na zmazanie uzivatela REST endpoint NEMA (`deleteUser` je len na
    ActionDelegate). Bez tejto cesty by po kazdom behu zostal dalsi ucet."""
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
    return None, "mongosh sa nepodarilo spustit"


def wipe(boss):
    zmazane = 0
    for c in cases_of(boss, NET):
        if "puzcheck." in (c.get("title") or ""):
            boss.call("DELETE", f"/api/workflow/case/{c['stringId']}")
            zmazane += 1
    print(f"puzcheck: zmazanych {zmazane} pripadov uctov")
    out, err = mongo_eval(MONGO_DELETE_TEST_USERS)
    if err:
        print(f"puzcheck: ucty sa zmazat nepodarilo - {err}")
        return
    line = [l for l in (out or "").splitlines() if l.startswith("PURGED")]
    print(f"puzcheck: zmazanych {line[0].split()[1] if line else 0} testovacich uctov")


# --------------------------------------------------------------------------

def main():
    boss = Client("super@netgrif.com", SUPER_PASS)
    if "--wipe" in sys.argv:
        wipe(boss)
        return 0

    if mail_api("/api/v1/messages?limit=1") is None:
        sys.exit(f"puzcheck: Mailpit na {MAILPIT} neodpoveda - bez neho sa "
                 f"pozvanky overit nedaju (tools/up.sh --docker)")

    stamp = int(time.time())
    email = f"puzcheck.{stamp}@test.local"
    heslo = "PozvankaTest123"
    nove_heslo = "PozvankaTest456"

    print("=== 1. prihlasenie a pult ===")
    spravca = Client("admin@test.local", TEST_PASS)
    iny = Client("operator@test.local", TEST_PASS)

    pulty = tasks_by_transition(spravca, "t_pu_pozvi")
    check("spravca vidi pozvankovy pult", len(pulty) == 1, len(pulty))
    check("iny clovek pozvankovy pult nevidi",
          len(tasks_by_transition(iny, "t_pu_pozvi")) == 0)
    if not pulty:
        # Najcastejsia pricina NIE JE chyba v sieti, ale zastaraly bootstrap
        # case. `pu_zalozenie` je v manifeste obycajnym identifikatorom, teda
        # "jeden case NAVZDY" (pult) - takze po re-importe siete s NOVYM
        # prechodom sa case NEPRESTAVI a na starom modeli ziadny taky prechod
        # nie je. Import prejde, `pfsync` je zeleny a uloha jednoducho nie je.
        stare = cases_of(boss, NET_ZAL)
        print("puzcheck: pozvankovy pult neexistuje.")
        if stare:
            print(f"puzcheck: v instancii je {len(stare)} case(ov) {NET_ZAL} - "
                  f"pravdepodobne z predchadzajucej verzie siete.")
            print("puzcheck: zmaz ich a restartuj backend, BootstrapCaseRunner "
                  "ich postavi z novej verzie:")
            for c in stare:
                print(f"    DELETE /api/workflow/case/{c['stringId']}")
        return 1
    pult = pulty[0]["stringId"]

    # Pult je zdielana uloha - ked ju drzi niekto z minuleho behu, uvolni ju.
    release(boss, pult)

    print("\n=== 2. pozvanie ===")
    # (mail sa pre tuto adresu overuje v sekcii 4)
    set_data(spravca, pult, {
        "poz_email": {"type": "text", "value": email},
        "poz_proces": {"type": "enumeration_map", "value": ROLA_SIET},
    })
    set_data(spravca, pult, {"poz_roly": {"type": "multichoice_map", "value": [ROLA]}})
    set_data(spravca, pult, {"poz_pridaj": {"type": "button", "value": 0}})
    v = values(spravca, pult)
    check("rola je v zozname na pridelenie", ROLA in (v.get("poz_pridelene") or ""),
          (v.get("poz_pridelene") or "").replace("\n", " | ")[:120])

    # TLACIDLO DOKONCIT SA NESMIE ZOBRAZIT. Meria sa `finishTitle`: prazdny
    # retazec je to, co ho schova (`canFinish()` je `opravnenie && title !== ''`),
    # a je to jedina cast, ktora sa da odmerat cez API.
    #
    # Opravnenie `<finish>false</finish>` na roleRef je v sieti tiez, ale
    # TESTOVAT sa tu neda: obe konta s rolou `spravca` su zaroven ROLE_ADMIN
    # a ten opravnenia obchadza (cheatsheet, "Opravnenia"). Na admina teda
    # zakaz neplati a `finish` mu prejde - preto je titul to, na com to stoji.
    pult_task = [t for t in tasks_by_transition(spravca, "t_pu_pozvi")
                 if t["stringId"] == pult]
    check("tlacidlo DOKONCIT je na pozvankovom pulte schovane",
          (pult_task[0].get("finishTitle") if pult_task else None) == "",
          pult_task[0].get("finishTitle") if pult_task else "(uloha sa nenasla)")

    st, r = odosli(spravca, pult)
    # Odmietnutie z akcie vracia HTTP 200 a dovod v tele ako `error` - test na
    # stavovy kod by taky blok prehliadol.
    check("pozvanie neskoncilo odmietnutim",
          not (isinstance(r, dict) and r.get("error")), str(r)[:160])
    v = values(spravca, pult)
    vysledok = v.get("poz_vysledok") or ""
    check("pult hlasi odoslanu pozvanku", "Invitation sent to" in vysledok,
          vysledok.replace("\n", " | ")[:160])
    check("pult hlasi pridelenu rolu", ROLA in vysledok,
          vysledok.replace("\n", " | ")[:160])
    check("pult sa po pozvani vyprazdnil", not (v.get("poz_email") or ""),
          v.get("poz_email"))
    hist = v.get("poz_historia") or ""
    check("pozvanie je v historii", email in hist, hist.replace("\n", " | ")[:160])
    check("historia hovori, kto pozval", "admin@test.local" in hist,
          hist.replace("\n", " | ")[:160])
    check("historia hovori, ake role dostal", ROLA in hist,
          hist.replace("\n", " | ")[:160])

    print("\n=== 3. ucet vznikol, ale NEMA heslo ===")
    # Ucet existuje, lenze `/api/user/search` ho NEVRATI - engine v predikate
    # filtruje na `state = ACTIVE`. Jedine miesto, kde je pozvany clovek v appke
    # vidiet, je preto jeho PRIPAD - a to je dovod, preco ho pozvanie zaklada
    # hned a nie az po registracii.
    check("pozvany ucet NIE JE v /api/user/search (engine filtruje na ACTIVE)",
          user_by_email(boss, email) is None)
    pripad = case_by_email(boss, email)
    check("pozvany ucet ma svoj pripad", pripad is not None, email)
    if not pripad:
        return 1
    tid_ucet = tasks_of(spravca, pripad["stringId"]).get("t_pu_uprava")
    pv = values(spravca, tid_ucet) if tid_ucet else {}
    user_id = (pv.get("pu_userid") or "").strip()
    check("pripad je zviazany s uctom", bool(user_id), pv.get("pu_userid"))
    check("pripad hlasi stav Pozvany", pv.get("pu_stav_label") == "Invited",
          pv.get("pu_stav_label"))
    check("pripad ma e-mail pozvaneho", (pv.get("pu_email") or "") == email,
          pv.get("pu_email"))
    if tid_ucet:
        release(boss, tid_ucet)
    if not user_id:
        return 1
    check("ucet ma pridelenu rolu z pozvanky", ROLA in roles_of(boss, user_id),
          roles_of(boss, user_id))
    # Toto je dokaz, ze pozvanka NIE JE ucet s heslom: prihlasit sa nedá.
    check("pozvanym uctom sa NEDA prihlasit",
          Client(email, heslo, allow_fail=True).token is None)

    print("\n=== 3b. opakovana pozvanka na NEAKTIVNY ucet ===")
    # Bezna potreba: odkaz vyprsal a spravca posiela pozvanku znova. Ucet uz
    # existuje, takze `createNewUser` ho len obnovi - a `zaloz_pripad` by mu
    # pri kazdom opakovani pridal dalsi pripad, keby to siet nekontrolovala.
    #
    # NA INEJ ADRESE nez zvysok testu, a to zamerne: engine ma limit
    # `nae.security.limits.email-sends-attempts=2` na adresu a den. Dve
    # pozvanky ho vycerpaju, takze nasledna ziadost o obnovu hesla by uz mail
    # neposlala - a `/api/auth/reset` na to odpovie `successMessage("Done")`,
    # teda uspechom. Prva verzia tohto testu na to naletela a vyzeralo to ako
    # chyba obnovy hesla.
    email_op = f"puzcheck.{stamp + 1}@test.local"
    release(boss, pult)
    set_data(spravca, pult, {"poz_email": {"type": "text", "value": email_op}})
    odosli(spravca, pult)
    release(boss, pult)
    set_data(spravca, pult, {"poz_email": {"type": "text", "value": email_op}})
    st, r = odosli(spravca, pult)
    check("opakovana pozvanka prejde",
          not (isinstance(r, dict) and r.get("error")), str(r)[:140])
    v = values(spravca, pult)
    check("hlasi, ze ide o opakovane poslanie",
          "sent again" in (v.get("poz_vysledok") or ""),
          (v.get("poz_vysledok") or "").replace("\n", " | ")[:140])
    op_pripady = [c for c in cases_of(boss, NET) if email_op in (c.get("title") or "")]
    check("opakovanie NEZALOZI druhy pripad uctu", len(op_pripady) == 1, len(op_pripady))
    hist = (values(spravca, pult).get("poz_historia") or "")
    check("historia rozlisi opakovane poslanie", "SENT AGAIN" in hist,
          hist.replace("\n", " | ")[:160])
    check("historia drzi aj predchadzajuce pozvania", email in hist,
          hist.replace("\n", " | ")[:200])
    release(boss, pult)

    print("\n=== 4. mail ===")
    m, detail = wait_for_mail(email)
    check("pozvanka prisla do schranky", m is not None, email)
    if not m:
        return 1
    check("predmet je nas, nie 'Registration invite' z jaru",
          "Registration invite" not in (m.get("Subject") or "")
          and "eTask" in (m.get("Subject") or ""),
          m.get("Subject"))
    html = (detail or {}).get("HTML") or ""
    check("telo je nasa sablona, nie netgrif.com",
          "netgrif.com/mail" not in html and "eTask" in html)
    check("mail je dvojjazycny",
          "Dokončiť registráciu" in html and "Complete registration" in html)

    odkazy = links_in(detail, "/signup")
    check("mail obsahuje odkaz na registraciu", len(odkazy) > 0, odkazy[:1])
    if not odkazy:
        return 1
    odkaz = odkazy[0]

    print("\n=== 5. odkaz vedie na existujucu routu ===")
    parsed = urllib.parse.urlparse(odkaz)
    routes = frontend_routes()
    check("nae.json sa da precitat", routes is not None, NAE_JSON)
    if routes:
        route, access = route_matches(parsed.path, routes)
        check(f"cesta '{parsed.path}' sedi na deklarovanu routu",
              route is not None, [r for r, _ in routes])
        check("ta routa je verejna", access == "public", access)

    qs = urllib.parse.parse_qs(parsed.query)
    token = (qs.get("token") or [None])[0]
    check("token je v query parametri, nie v ceste",
          token is not None,
          "odkaz s tokenom v ceste sa rozbije vzdy, ked token obsahuje '/'")
    if not token:
        return 1
    # Prave toto je ta pasca: `encodeToken` je standardne Base64, takze `/`
    # a `+` v tokene su bezne. `parse_qs` uz odkodovalo percentovanie; keby
    # sablona token neescapovala, `+` by sa tu zmenil na medzeru a verify by
    # zlyhalo. Test to teda chyta bez toho, aby o escapovani cokolvek vedel.
    st, r = anon().post("/api/auth/token/verify", raw=token, ctype="text/plain")
    check("engine ten token prijme", isinstance(r, dict) and r.get("success"),
          str(r)[:140])
    check("token patri pozvanemu", isinstance(r, dict) and r.get("success") == email,
          str(r)[:140])

    print("\n=== 6. dokoncenie registracie ===")
    st, r = anon().post("/api/auth/signup", {
        "token": token, "name": "Puz", "surname": "Check",
        "password": base64.b64encode(heslo.encode()).decode()})
    check("signup presiel", isinstance(r, dict) and not r.get("error"), str(r)[:160])
    novy = Client(email, heslo, allow_fail=True)
    check("ucet sa uz PRIHLASI nastavenym heslom", novy.token is not None)
    check("role pozvanku prezili", ROLA in roles_of(boss, user_id),
          roles_of(boss, user_id))
    u2 = user_by_email(boss, email)
    check("meno a priezvisko su z registracneho formulara",
          (u2 or {}).get("name") == "Puz" and (u2 or {}).get("surname") == "Check",
          {k: (u2 or {}).get(k) for k in ("name", "surname")})

    print("\n=== 7. pripad uctu a jeho stav po registracii ===")
    pripady = [c for c in cases_of(boss, NET) if email in (c.get("title") or "")]
    check("ucet ma stale prave jeden pripad", len(pripady) == 1, len(pripady))
    if pripady:
        tid = tasks_of(spravca, pripady[0]["stringId"]).get("t_pu_uprava")
        check("pripad ma ulohu upravy", tid is not None)
        if tid:
            # Pripad si stav dotiahne z uctu pri kazdom otvoreni - ucet je
            # zdroj pravdy, nie to, co bolo v pripade zapisane pri zalozeni.
            # Preto sa stav z "Pozvany" prepne na "Aktivny" sam, bez toho, aby
            # sa ho niekto musel dotknut.
            set_data(spravca, tid, {"pu_userid": {"type": "text", "value": user_id}})
            pv = values(spravca, tid)
            check("pripad uz hlasi ucet ako Aktivny",
                  "Active" in (pv.get("pu_stav_label") or ""),
                  pv.get("pu_stav_label"))
            check("pripad ma meno z registracneho formulara",
                  (pv.get("pu_meno") or "") == "Puz", pv.get("pu_meno"))
            release(boss, tid)

    print("\n=== 8. opakovane pozvanie aktivneho uctu ===")
    release(boss, pult)
    set_data(spravca, pult, {"poz_email": {"type": "text", "value": email}})
    odosli(spravca, pult)
    v8 = values(spravca, pult)
    # Tlacidlo nehadze vynimku - odmietnutie je VETA vo formulari, aby
    # spravca vedel, co ma opravit. Preto sa to tu cita z pola, nie zo stavu.
    check("pozvat aktivny ucet sa NEDA",
          "already exists and is active" in (v8.get("poz_vysledok") or ""),
          (v8.get("poz_vysledok") or "")[:180])
    check("neuspesny pokus je v historii", "NOT SENT" in (v8.get("poz_historia") or ""),
          (v8.get("poz_historia") or "").replace("\n", " | ")[:160])
    check("formular sa po neuspechu NEVYPRAZDNIL",
          (v8.get("poz_email") or "") == email, v8.get("poz_email"))
    release(boss, pult)

    print("\n=== 9. obnova hesla ===")
    posledny = newest_mail_id()
    st, r = anon().post("/api/auth/reset", raw=email, ctype="text/plain")
    check("ziadost o obnovu presla", isinstance(r, dict) and not r.get("error"),
          str(r)[:140])
    st, r2 = anon().post("/api/auth/reset", raw=f"nikto.{stamp}@test.local",
                         ctype="text/plain")
    check("odpoved neprezradi, ci ucet existuje", str(r) == str(r2),
          f"{str(r)[:60]} vs {str(r2)[:60]}")

    m, detail = wait_for_mail(email, since_id=posledny)
    check("mail o obnove hesla prisiel", m is not None)
    if m:
        check("predmet je nas, nie 'Reset password' z jaru",
              "Reset password" not in (m.get("Subject") or ""),
              m.get("Subject"))
        odkazy = links_in(detail, "/recover")
        check("mail obsahuje odkaz na obnovu", len(odkazy) > 0)
        if odkazy:
            p2 = urllib.parse.urlparse(odkazy[0])
            if routes:
                route, access = route_matches(p2.path, routes)
                check(f"cesta '{p2.path}' sedi na deklarovanu routu",
                      route is not None)
            tok2 = (urllib.parse.parse_qs(p2.query).get("token") or [None])[0]
            check("token obnovy je v query parametri", tok2 is not None)
            if tok2:
                # Ucet je od `reset` v stave BLOCKED a heslo ma zmazane -
                # STARE HESLO NEFUNGUJE uz teraz, este pred nastavenim noveho.
                check("po ziadosti o obnovu stare heslo uz neplati",
                      Client(email, heslo, allow_fail=True).token is None)
                st, r = anon().post("/api/auth/recover", {
                    "token": tok2, "email": "", "name": "", "surname": "",
                    "password": base64.b64encode(nove_heslo.encode()).decode()})
                check("obnova hesla presla",
                      isinstance(r, dict) and not r.get("error"), str(r)[:160])
                check("nove heslo funguje",
                      Client(email, nove_heslo, allow_fail=True).token is not None)
                check("stare heslo nefunguje ani po obnove",
                      Client(email, heslo, allow_fail=True).token is None)

    print(f"\npuzcheck: {len(OK)} preslo, {len(FAIL)} zlyhalo")
    for f in FAIL:
        print("  ZLYHALO:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
