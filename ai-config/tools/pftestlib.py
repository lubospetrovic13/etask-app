#!/usr/bin/env python3
"""
pftestlib - spolocny základ akceptacnych testov proti BEZIACEMU enginu.

PRECO TO EXISTUJE

Akceptacny test je jediné miesto, kde sa da overit, ze appka robi to, co ma:
ze schvalovatel fakturu vidi a zadavatel nie, ze odmietnute DOKONCIT nikomu
neubralo ulohu, ze zobrazenie v menu naozaj nieco najde. Z XML ani z importu sa
to zistit neda.

Cena za to bola, ze kazda appka si tych ~250 riadkov klienta a pomocnikov pisala
znova - a s nimi aj kazdu pascu, na ktoru sa uz raz naletelo. Tu su raz
a poriadne:

  1. `GET /api/auth/login` vrati 405, ale token uz JE v hlavicke - autentifikacny
     filter bezi pred handlerom.
  2. Telo `POST /api/task/{id}/data` je {taskId: {fieldId: ...}}, NIE
     {fieldId: ...}. Ploche telo vrati HTTP 200 s hlaskou "Could not find task
     with id [<fieldId>]" a ticho nezapise nic.
  3. Engine odmietnutie NEHLASI HTTP kodom: `finish` blokovany akciou vrati 200
     a dovod da do tela ako `error`. Test na stavovy kod taky blok prehliadne.
  4. `GET /api/task/case/{id}` NEFILTRUJE podla opravneni - vrati vsetky ulohy
     kazdemu, kto pozna id. Na to, co uzivatel naozaj vidi, je `POST /api/task/search`.
  5. Bez hlavicky `Accept: application/hal+json` vracaju HATEOAS endpointy 406.
  6. Bez `Accept-Language` odpoveda engine v jazyku JVM, nie hodnotou z XML.
     `zz` je jazyk, ktory engine NEPOZNA, takze spadne na `defaultValue` -
     teda na to, co je v sieti. Na overenie prekladu sa pouzije `en`.

POUZITIE

    import pftestlib as pf

    def main():
        boss = pf.Client("super@netgrif.com", pf.SUPER_PASS)
        if "--wipe" in sys.argv:
            return pf.wipe_cases(boss, NET)
        net = pf.newest_net(boss, NET)
        case_id, _ = pf.new_case(boss, net["stringId"])
        t = pf.tasks_of(boss, case_id)["t_podanie"]
        pf.set_data(boss, t, {"predmet": {"type": "text", "value": "x"}})
        st, r = pf.finish(boss, t)
        pf.check("podanie preslo", pf.ok_body(r), str(r)[:120])
        return pf.report("mojaappcheck")

Existujuce sady (`sccheck`, `dvcheck`, `pucheck`) si vlastne kopie ponechavaju
zamerne: su to jedine kontroly, ktore appky maju, a prepisovat ich naraz by
znamenalo menit bezpecnostnu siet a jej test sucasne. Nove appky (`pfnew`)
stavaju na tomto.
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
SUPER_PASS = os.environ.get("PF_PASS", "password")

OK, FAIL = [], []


class Client:
    """Prihlaseny klient. `lang="zz"` = odpovede v defaultValue zo siete."""

    def __init__(self, email, password, lang="zz", allow_fail=False):
        self.email = email
        self.lang = lang
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
            sys.exit(f"pftestlib: engine na {URL} neodpoveda (bezi tools/up.sh?)")
        if not self.token and not allow_fail:
            sys.exit(f"pftestlib: prihlasenie {email} zlyhalo")

    def call(self, method, path, body=None, timeout=120):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"X-Auth-Token": self.token,
                   "Accept": "application/hal+json, application/json;q=0.9, */*;q=0.8",
                   "Accept-Language": self.lang}
        if data:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(URL + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = r.read().decode("utf-8")
                return r.status, (json.loads(text) if text else None)
        except urllib.error.HTTPError as e:
            telo = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(telo)
            except ValueError:
                return e.code, telo

    def get(self, path):
        return self.call("GET", path)

    def post(self, path, body=None):
        return self.call("POST", path, body)


# ----------------------------------------------------------------- vysledky

def check(label, cond, detail=""):
    (OK if cond else FAIL).append(label)
    print(("  [OK]   " if cond else "  [ZLE] ") + label
          + ((" -- " + str(detail)) if detail else ""))
    return bool(cond)


def report(nazov):
    print(f"\n{nazov}: {len(OK)} preslo, {len(FAIL)} zlyhalo")
    for f in FAIL:
        print("  ZLYHALO:", f)
    return 1 if FAIL else 0


# -------------------------------------------------------------- siete a casy

def newest_net(cl, identifier):
    st, r = cl.post("/api/petrinet/search?size=200", {"identifier": identifier})
    refs = (r.get("_embedded") or {}).get("petriNetReferences", []) if isinstance(r, dict) else []
    refs = [x for x in refs if x["identifier"] == identifier]
    if not refs:
        sys.exit(f"pftestlib: siet {identifier} nie je naimportovana (pfsync --sync)")
    refs.sort(key=lambda x: [int(n) for n in str(x["version"]).split(".")])
    return refs[-1]


def new_case(cl, net_id, title=None):
    st, r = cl.post("/api/workflow/case", {"netId": net_id, "title": title, "color": ""})
    m = re.search(r"Case with id ([0-9a-f]{24})",
                  r.get("success", "") if isinstance(r, dict) else "")
    if not m:
        sys.exit(f"pftestlib: zalozenie pripadu zlyhalo: {st} {str(r)[:300]}")
    st, c = cl.get(f"/api/workflow/case/{m.group(1)}")
    return m.group(1), c


def cases_of(cl, identifier, size=500):
    st, r = cl.post(f"/api/workflow/case/search?size={size}",
                    {"process": [{"identifier": identifier}]})
    return (r.get("_embedded") or {}).get("cases", []) if isinstance(r, dict) else []


def wipe_cases(cl, identifier, nazov="pftestlib"):
    cs = cases_of(cl, identifier)
    for c in cs:
        cl.call("DELETE", f"/api/workflow/case/{c['stringId']}")
    print(f"{nazov}: zmazanych {len(cs)} pripadov")
    return 0


# ------------------------------------------------------------------- ulohy

def tasks_of(cl, case_id):
    """Ulohy, ktore uzivatel NAOZAJ vidi (`/search` filtruje podla opravneni)."""
    st, r = cl.post("/api/task/search?size=100", {"case": [{"id": case_id}]})
    tl = (r.get("_embedded") or {}).get("tasks", []) if isinstance(r, dict) else []
    return {t["transitionId"]: t["stringId"] for t in tl}


def tasks_raw(cl, case_id):
    """Vsetky ulohy casu bez ohladu na opravnenia - na overenie, ze uloha
    EXISTUJE, aj ked ju konkretny uzivatel vidiet nema."""
    st, tl = cl.get(f"/api/task/case/{case_id}")
    return {t["transitionId"]: t["stringId"] for t in (tl or [])}


def assign(cl, task_id):
    return cl.get(f"/api/task/assign/{task_id}")


def finish(cl, task_id):
    return cl.get(f"/api/task/finish/{task_id}")


def field_map(cl, task_id):
    """{id pola: cele pole}. `data` aj `outcome.data` - engine pouziva oboje."""
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


def options(cl, task_id, field_id):
    return (field_map(cl, task_id).get(field_id) or {}).get("options") or {}


def behavior(cl, task_id, field_id):
    return (field_map(cl, task_id).get(field_id) or {}).get("behavior")


def set_data(cl, task_id, vals, timeout=120):
    """Priradi a zapise. Telo je {taskId: {fieldId: ...}} - ploche telo vrati
    200 a nezapise nic."""
    assign(cl, task_id)
    return cl.call("POST", f"/api/task/{task_id}/data", {task_id: vals}, timeout=timeout)


# ---------------------------------------------------------------- odpovede

def err_body(r):
    """Engine odmietnutie vracia 200 + `error` v tele."""
    return isinstance(r, dict) and "error" in r


def ok_body(r):
    return isinstance(r, dict) and "error" not in r


# -------------------------------------------------------------------- menu

def uri_paths(cl, deep=False):
    """Karty, ktore uzivatel vidi v bocnom menu.

    `deep=True` vrati aj vnorene uzly (`hr/cesty`, nielen `hr`). Appka, ktora
    zije v podpriecinku, sa inak overit neda: v korenovych detoch je len jej
    kategoria a tu vidi aj ten, kto do appky nesmie.
    """
    st, root = cl.get("/api/v2/uri/root")
    deti = (root or {}).get("children", [])
    if not deep:
        return [c["uriPath"] for c in deti]

    # `children` v odpovedi je VZDY PRAZDNE - naplneny je len `childrenId`,
    # takze rekurzia cez `children` by nasla len prvu uroven a kontrola
    # "appku v podpriecinku nevidno" by presla aj ked ju vidno. Deti uzla
    # vracia `/api/v2/uri/parent/{id}` (to vola aj frontend).
    def deti_uzla(uzol_id):
        st2, r = cl.get(f"/api/v2/uri/parent/{uzol_id}")
        if isinstance(r, list):
            return r
        return ((r or {}).get("_embedded") or {}).get("uriNodes", []) or []

    out = []

    def zober(uzol, hlbka=0):
        if not uzol or hlbka > 6:
            return
        cesta = uzol.get("uriPath")
        if cesta:
            out.append(cesta)
        for d in deti_uzla(uzol.get("id")):
            zober(d, hlbka + 1)

    for c in deti:
        zober(c)
    return out


def menu_items(cl, prefix=None):
    """{nazov zobrazenia: id pripadu}. `prefix` filtruje podla
    `menu_item_identifier` - nazvy NIE SU v ramci portalu unikatne."""
    st, r = cl.post("/api/workflow/case/search?size=300",
                    {"process": [{"identifier": "preference_filter_item"}]})
    out = {}
    for c in (r.get("_embedded") or {}).get("cases", []) if isinstance(r, dict) else []:
        ident = ""
        for d in (c.get("immediateData") or []):
            if d.get("importId") == "menu_item_identifier":
                ident = d.get("value") or ""
        if prefix and not ident.startswith(prefix):
            continue
        out.setdefault(c["title"], c["stringId"])
    return out
