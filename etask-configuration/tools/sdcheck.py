#!/usr/bin/env python3
"""
sdcheck - akceptacny test Service Desku proti BEZIACEMU enginu.

Overuje cely obeh, ktory sa z XML ani z importu zistit neda:

  1. zamestnanec podpory zalozi firmu a prida do nej ludi - existujuci ucet
     dostane pristup, novy e-mail pozvanku (mail naozaj odide do mailpitu),
  2. pozvany si z odkazu v maile nastavi heslo a prihlasi sa,
  3. zakaznik vidi kartu a podá poziadavku; bez firmy by bola odmietnuta,
  4. kolega z tej istej firmy ju vidi, cudzi clovek nie,
  5. podpora ju prevezme, vyziada doplnenie, zakaznik odpovie, podpora vyriesi,
  6. odobraty clovek firmy prestane poziadavky firmy vidiet (kaskada),
  7. clovek nemoze byt v dvoch firmach.

Predpoklad: bezi stack s SMTP na mailpit a s testovacimi uctami:

    docker run -d --name mailpit -p 1025:1025 -p 8025:8025 axllent/mailpit
    MAIL_HOST=localhost MAIL_PORT=1025 MAIL_TLS_ENABLED=false \
      MAIL_AUTH_ENABLED=false ETASK_TEST_PASSWORD=test1234 tools/up.sh

    python3 tools/sdcheck.py

Exit 0 = vsetko preslo, 1 = nieco zlyhalo.
"""

import base64
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import pftestlib as pf

TICKET = "it/service_desk/sd_ticket"
FIRMA = "it/service_desk/sd_firma"
MENU = "it/service_desk/sd_menu"
CARD = "it/service_desk"
STAFF = "operator@test.local"      # rola `podpora` zo seed.json
CUSTOMER = "druhy@test.local"      # existujuci ucet bez roly podpory
OUTSIDER = "viewer@test.local"     # nie je v ziadnej firme
MAILPIT = os.environ.get("MAILPIT_URL", "http://127.0.0.1:8025")


def mailpit(path):
    with urllib.request.urlopen(MAILPIT + path, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def invite_token(email):
    """Token z posledneho mailu pre `email`. Odkaz v sablone konci tokenom."""
    msgs = mailpit("/api/v1/messages?limit=50").get("messages", [])
    for m in msgs:
        if any(t.get("Address", "").lower() == email.lower() for t in m.get("To", [])):
            body = mailpit(f"/api/v1/message/{m['ID']}")
            text = (body.get("HTML") or "") + "\n" + (body.get("Text") or "")
            hits = re.findall(r"/signup/([A-Za-z0-9_=%-]+)", text) \
                or re.findall(r"token=([A-Za-z0-9_=%-]+)", text)
            if hits:
                return urllib.parse.unquote(hits[0])
    return None


def search_ids(cl, query):
    st, r = cl.post("/api/workflow/case/search?size=200", {"query": query})
    return [x["stringId"] for x in (r.get("_embedded") or {}).get("cases", [])] \
        if isinstance(r, dict) else []


def press(cl, task_id, button, extra=None):
    vals = dict(extra or {})
    vals[button] = {"type": "button", "value": 1}
    pf.set_data(cl, task_id, vals)
    return pf.values(cl, task_id)


def main():
    ts = int(time.time())
    boss = pf.Client("super@netgrif.com", pf.SUPER_PASS)

    print("=== 1. menu a karta ===")
    mt = [c["title"] for c in pf.cases_of(boss, MENU, size=20)]
    pf.check("bootstrap case menu hlasi 6/6", any("6/6" in t for t in mt), mt)
    items = pf.menu_items(boss, prefix="sd_")
    for want in ["Podanie požiadavky", "Moje požiadavky", "Požiadavky na prevzatie",
                 "Požiadavky v riešení", "Všetky požiadavky podpory", "Firmy zákazníkov"]:
        pf.check(f"zobrazenie '{want}' existuje", want in items, sorted(items))
    for stare in ["Tikety", "Moje úlohy", "Zákazníci", "Podania z formulára", "Podať požiadavku"]:
        pf.check(f"stare zobrazenie '{stare}' nie je", stare not in items)

    staff = pf.Client(STAFF, pf.TEST_PASS)
    outsider = pf.Client(OUTSIDER, pf.TEST_PASS)
    pf.check("podpora vidi kartu Service Desku", CARD in pf.uri_paths(staff, deep=True))
    pf.check("clovek mimo firiem kartu nevidi", CARD not in pf.uri_paths(outsider, deep=True))

    print("\n=== 2. firma a ludia ===")
    fnet = pf.newest_net(staff, FIRMA)
    firma_id, _ = pf.new_case(staff, fnet["stringId"])
    t = pf.tasks_of(staff, firma_id)
    pf.check("firma ma ulohu t_firma", "t_firma" in t, list(t))
    tf = t.get("t_firma")
    if not tf:
        return pf.report("sdcheck")
    nazov = f"Firma sdcheck {ts}"
    pf.set_data(staff, tf, {"f_nazov": {"type": "text", "value": nazov}})

    v = press(staff, tf, "btn_pridat", {"f_novy_email": {"type": "text", "value": CUSTOMER}})
    pf.check("existujuci ucet dostal pristup bez pozvanky",
             "access granted" in (v.get("f_vysledok") or ""), v.get("f_vysledok"))
    pf.check("vo firme je 1 clovek", v.get("f_pocet") == 1, v.get("f_pocet"))

    novy = f"sdcheck{ts}@test.local"
    v = press(staff, tf, "btn_pridat", {"f_novy_email": {"type": "text", "value": novy}})
    pf.check("novy e-mail dostal pozvanku",
             "invitation sent" in (v.get("f_vysledok") or ""), v.get("f_vysledok"))
    pf.check("vo firme su 2 ludia", v.get("f_pocet") == 2, v.get("f_pocet"))
    pf.check("pozvany je v zozname ako 'invited'", "invited" in (v.get("f_ludia") or ""),
             v.get("f_ludia"))

    v = press(staff, tf, "btn_pridat", {"f_novy_email": {"type": "text", "value": "zly-email"}})
    pf.check("zly e-mail je odmietnuty vo formulari",
             "not a valid" in (v.get("f_vysledok") or ""), v.get("f_vysledok"))

    # Druha firma: ten isty clovek do nej nesmie.
    f2, _ = pf.new_case(staff, fnet["stringId"])
    t2 = pf.tasks_of(staff, f2).get("t_firma")
    pf.set_data(staff, t2, {"f_nazov": {"type": "text", "value": f"Druha {ts}"}})
    v2 = press(staff, t2, "btn_pridat", {"f_novy_email": {"type": "text", "value": CUSTOMER}})
    pf.check("clovek nemoze byt v dvoch firmach",
             "one company only" in (v2.get("f_vysledok") or ""), v2.get("f_vysledok"))
    boss.call("DELETE", f"/api/workflow/case/{f2}")

    print("\n=== 3. registracia z pozvanky ===")
    token = None
    for _ in range(10):
        token = invite_token(novy)
        if token:
            break
        time.sleep(1)
    pf.check("pozvanka je v mailpite a nesie token", bool(token))
    if token:
        anon = pf.Client(OUTSIDER, pf.TEST_PASS)   # signup je verejny, token netreba
        st, r = anon.post("/api/auth/signup", {
            "token": token, "name": "Nový", "surname": "Zákazník",
            "password": base64.b64encode(b"heslo1234").decode()})
        pf.check("registracia z odkazu presla", isinstance(r, dict) and "success" in r, r)
    kolega = pf.Client(novy, "heslo1234", allow_fail=True)
    pf.check("pozvany sa prihlasi vlastnym heslom", bool(kolega.token))

    print("\n=== 4. podanie poziadavky ===")
    zak = pf.Client(CUSTOMER, pf.TEST_PASS)       # nove prihlasenie = nove roly
    pf.check("zakaznik vidi kartu Service Desku", CARD in pf.uri_paths(zak, deep=True))
    tnet = pf.newest_net(zak, TICKET)
    case_id, case = pf.new_case(zak, tnet["stringId"])
    t = pf.tasks_of(zak, case_id)
    pf.check("na zaciatku ma zakaznik len podanie", list(t) == ["t_podanie"], list(t))
    tp = t.get("t_podanie")
    if not tp:
        return pf.report("sdcheck")
    v = pf.values(zak, tp)
    pf.check("firma je predvyplnena podla clenstva", v.get("tk_firma_nazov") == nazov,
             v.get("tk_firma_nazov"))
    pf.check("koncept kolega nevidi", case_id not in search_ids(kolega, f'processIdentifier:"{TICKET}"'))

    pf.assign(zak, tp)
    st, r = pf.finish(zak, tp)
    pf.check("prazdne podanie je odmietnute", pf.err_body(r), str(r)[:120])
    predmet = f"Nejde tlac {ts}"
    pf.set_data(zak, tp, {
        "tk_predmet": {"type": "text", "value": predmet},
        "tk_typ": {"type": "enumeration_map", "value": "incident"},
        "tk_urgentnost": {"type": "enumeration_map", "value": "A"},
        "tk_popis": {"type": "text", "value": "Tlaciaren na 2. poschodi netlaci."}})
    st, r = pf.finish(zak, tp)
    pf.check("podanie preslo", pf.ok_body(r), str(r)[:160])

    t = pf.tasks_of(zak, case_id)
    pf.check("zakaznik po podani vidi 'Moja poziadavka'", "t_moja" in t, list(t))
    pf.check("zakaznik nevidi ulohy podpory", not ({"t_detail", "t_prevzat"} & set(t)), list(t))
    st, c = zak.get(f"/api/workflow/case/{case_id}")
    pf.check("nazov nesie cislo a predmet", predmet in (c.get("title") or ""), c.get("title"))

    q_moje = f'processIdentifier:"{TICKET}" AND dataSet.tk_stav.keyValue:("nova" OR "v_rieseni" OR "caka" OR "vyriesena")'
    pf.check("zakaznik ju vidi v 'Moje poziadavky'", case_id in search_ids(zak, q_moje))
    pf.check("kolega z firmy ju vidi tiez", case_id in search_ids(kolega, q_moje))
    pf.check("cudzi clovek ju nevidi", case_id not in search_ids(outsider, q_moje))
    pf.check("podpora ju vidi 'Na prevzatie'", case_id in search_ids(
        staff, f'processIdentifier:"{TICKET}" AND dataSet.tk_stav.keyValue:"nova"'))

    print("\n=== 5. spracovanie ===")
    ts_ = pf.tasks_of(staff, case_id)
    pf.check("podpora ma prehlad a prevzatie", {"t_detail", "t_prevzat"} <= set(ts_), list(ts_))
    tv = ts_.get("t_prevzat")
    v = pf.values(staff, tv)
    pf.check("priorita je predvyplnena zo surnosti", v.get("tk_priorita") == "A", v.get("tk_priorita"))
    pf.check("lehota odozvy je vypocitana", bool(v.get("sla_termin")), v.get("sla_termin"))
    pf.assign(staff, tv)
    st, r = pf.finish(staff, tv)
    pf.check("prevzatie preslo", pf.ok_body(r), str(r)[:160])

    tq = pf.tasks_of(staff, case_id).get("t_vyziadat")
    pf.set_data(staff, tq, {"tk_otazka": {"type": "text", "value": "Aky model tlaciarne?"}})
    st, r = pf.finish(staff, tq)
    pf.check("vyziadanie doplnenia preslo", pf.ok_body(r), str(r)[:160])

    tk = pf.tasks_of(kolega, case_id)
    pf.check("kolega moze odpovedat podpore", "t_doplnit" in tk, list(tk))
    if tk.get("t_doplnit"):
        pf.set_data(kolega, tk["t_doplnit"], {"tk_doplnenie": {"type": "text", "value": "HP LaserJet"}})
        st, r = pf.finish(kolega, tk["t_doplnit"])
        pf.check("odpoved zakaznika presla", pf.ok_body(r), str(r)[:160])

    tr = pf.tasks_of(staff, case_id).get("t_vyriesit")
    pf.check("podpora moze vyriesit", bool(tr))
    if tr:
        pf.set_data(staff, tr, {"tk_riesenie": {"type": "text", "value": "Vymeneny toner."}})
        st, r = pf.finish(staff, tr)
        pf.check("vyriesenie preslo", pf.ok_body(r), str(r)[:160])

    tm = pf.tasks_of(zak, case_id)
    v = pf.values(zak, tm["t_moja"]) if tm.get("t_moja") else {}
    pf.check("zakaznik vidi stav 'vyriesena'", v.get("tk_stav") == "vyriesena", v.get("tk_stav"))
    pf.check("zakaznik vidi riesenie", v.get("tk_riesenie") == "Vymeneny toner.", v.get("tk_riesenie"))
    kom = v.get("tk_komunikacia") or ""
    pf.check("komunikacia nesie otazku aj odpoved", "Aky model" in kom and "HP LaserJet" in kom, kom[-200:])
    pf.check("zakaznik nevidi internu poznamku", "tk_interna" not in v)
    pf.check("zakaznik moze znovu otvorit", "t_znovu" in tm, list(tm))

    print("\n=== 6. odobratie z firmy ===")
    kolega_id = None
    opts = pf.options(staff, tf, "f_odobrat")
    for k, lbl in opts.items():
        if novy in str(lbl):
            kolega_id = k
    pf.check("kolega je v ponuke na odobratie", bool(kolega_id), opts)
    if kolega_id:
        v = press(staff, tf, "btn_odobrat", {"f_odobrat": {"type": "enumeration_map", "value": kolega_id}})
        pf.check("odobratie preslo", "Removed" in (v.get("f_vysledok") or ""), v.get("f_vysledok"))
        pf.check("vo firme zostal 1 clovek", v.get("f_pocet") == 1, v.get("f_pocet"))
        kolega2 = pf.Client(novy, "heslo1234")
        pf.check("odobraty kolega poziadavku firmy uz nevidi",
                 case_id not in search_ids(kolega2, q_moje))
        pf.check("odobraty kolega nevidi kartu", CARD not in pf.uri_paths(kolega2, deep=True))
        pf.check("zakaznik, ktory zostal, ju vidi dalej", case_id in search_ids(zak, q_moje))

    return pf.report("sdcheck")


if __name__ == "__main__":
    sys.exit(main())
