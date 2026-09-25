#!/usr/bin/env python3
"""
sdcheck - akceptacny test Service Desku proti BEZIACEMU enginu.

Overuje cely obeh, ktory sa z XML ani z importu zistit neda:

  1. menu a karty podla roli (sd_admin, sd_agent, sd_customer),
  2. admin zalozi SLA plan a organizaciu, da jej plan a limit uctov,
     prida existujuci ucet (pristup bez pozvanky), novy e-mail (pozvanka
     naozaj odide do mailpitu) a limit zastavi dalsieho,
  3. admin priradi agenta; zakaznik agentom byt nemoze, clovek nemoze byt
     v dvoch organizaciach,
  4. pozvany si z odkazu nastavi heslo a prihlasi sa,
  5. zakaznik poda tiket - typ a podkategoria su povinne, terminy SLA sa
     vypocitaju z planu; kolega ho len sleduje, cudzi ho nevidi, agent
     organizacie ho vidi,
  6. agent odpovie (prva reakcia), prijme, vyziada doplnenie (pauza SLA),
     zakaznik odpovie (pauza konci), agent vyriesi, zakaznik potvrdi,
  7. odobraty kolega aj odobraty agent prestanu tiket vidiet (kaskada).

Predpoklad: bezi stack s SMTP na mailpit a s testovacimi uctami:

    tools/up.sh --docker            # mailpit je v nom

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
ORG = "it/service_desk/sd_organization"
PLAN = "it/service_desk/sd_sla_plan"
MENU = "it/service_desk/sd_menu"
CARD = "it/service_desk"
AGENT = "operator@test.local"      # rola `sd_agent` zo seed.json
CUSTOMER = "druhy@test.local"      # existujuci ucet bez roli Service Desku
OUTSIDER = "viewer@test.local"     # nie je v ziadnej organizacii
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
    boss = pf.Client("super@netgrif.com", pf.SUPER_PASS)     # sd_admin zo seed.json

    # Organizacie z minulych behov: CUSTOMER by v nich zostal clenom a clovek
    # smie byt len v jednej - druhy beh by inak zlyhal na vlastnych datach.
    for o in pf.cases_of(boss, ORG):
        if (o.get("title") or "").startswith(("Org sdcheck", "Second ")):
            boss.call("DELETE", f"/api/workflow/case/{o['stringId']}")

    print("=== 1. menu a karty ===")
    mt = [c["title"] for c in pf.cases_of(boss, MENU, size=20)]
    pf.check("bootstrap case menu hlasi 9/9", any("9/9" in t for t in mt), mt)
    items = pf.menu_items(boss, prefix="sd_")
    for want in ["Create New Ticket", "My Tickets", "Company Tickets", "Triage", "Tickets in progress",
                 "All Tickets", "My Organizations", "Organizations", "SLA Plans"]:
        pf.check(f"zobrazenie '{want}' existuje", want in items, sorted(items))
    for old in ["Podanie požiadavky", "Moje požiadavky", "Firmy zákazníkov"]:
        pf.check(f"stare zobrazenie '{old}' nie je", old not in items)

    agent = pf.Client(AGENT, pf.TEST_PASS)
    outsider = pf.Client(OUTSIDER, pf.TEST_PASS)
    pf.check("admin vidi kartu Service Desku", CARD in pf.uri_paths(boss, deep=True))
    pf.check("agent vidi kartu Service Desku", CARD in pf.uri_paths(agent, deep=True))
    pf.check("clovek mimo organizacii kartu nevidi", CARD not in pf.uri_paths(outsider, deep=True))

    print("\n=== 2. SLA plan a organizacia ===")
    pnet = pf.newest_net(boss, PLAN)
    plan_id, _ = pf.new_case(boss, pnet["stringId"])
    tp = pf.tasks_of(boss, plan_id).get("t_plan")
    pf.check("plan ma ulohu t_plan", bool(tp))
    if not tp:
        return pf.report("sdcheck")
    plan_name = f"Standard {ts}"
    pf.set_data(boss, tp, {"sp_name": {"type": "text", "value": plan_name},
                           "sp_resp_high": {"type": "number", "value": 3},
                           "sp_max_accounts": {"type": "number", "value": 5}})
    st, c = boss.get(f"/api/workflow/case/{plan_id}")
    pf.check("nazov planu je nazov pripadu", c.get("title") == plan_name, c.get("title"))
    pf.check("agent plany nevidi", plan_id not in search_ids(agent, f'processIdentifier:"{PLAN}"'))

    onet = pf.newest_net(boss, ORG)
    org_id, _ = pf.new_case(boss, onet["stringId"])
    to = pf.tasks_of(boss, org_id).get("t_org")
    pf.check("organizacia ma ulohu t_org", bool(to))
    if not to:
        return pf.report("sdcheck")
    org_name = f"Org sdcheck {ts}"
    pf.set_data(boss, to, {"org_name": {"type": "text", "value": org_name}})
    opts = pf.options(boss, to, "org_plan")
    pf.check("plan je v ponuke organizacie", plan_id in opts, opts)
    pf.set_data(boss, to, {"org_plan": {"type": "enumeration_map", "value": plan_id},
                           "org_max_accounts": {"type": "number", "value": 2}})
    v = pf.values(boss, to)
    pf.check("sumar planu nesie cas reakcie 'high 3 h'", "high 3 h" in (v.get("org_sla_summary") or ""),
             v.get("org_sla_summary"))

    v = press(boss, to, "btn_add", {"org_new_email": {"type": "text", "value": CUSTOMER}})
    pf.check("existujuci ucet dostal pristup bez pozvanky",
             "access granted" in (v.get("org_result") or ""), v.get("org_result"))
    novy = f"sdcheck{ts}@test.local"
    v = press(boss, to, "btn_add", {"org_new_email": {"type": "text", "value": novy}})
    pf.check("novy e-mail dostal pozvanku", "invitation" in (v.get("org_result") or "").lower(),
             v.get("org_result"))
    pf.check("pozvany je v zozname ako 'invited'", "invited" in (v.get("org_people") or ""),
             v.get("org_people"))
    pf.check("vyuzitie hlasi '2 of 2 accounts'", "2 of 2 accounts" in (v.get("org_usage") or ""),
             v.get("org_usage"))
    v = press(boss, to, "btn_add", {"org_new_email": {"type": "text", "value": f"third{ts}@test.local"}})
    pf.check("limit uctov zastavi tretieho", "2 of 2" in (v.get("org_result") or ""), v.get("org_result"))
    v = press(boss, to, "btn_add", {"org_new_email": {"type": "text", "value": "zly-email"}})
    pf.check("zly e-mail je odmietnuty vo formulari",
             "not a valid" in (v.get("org_result") or ""), v.get("org_result"))

    print("\n=== 3. agent ===")
    v = press(boss, to, "btn_add_agent", {"org_agent_email": {"type": "text", "value": CUSTOMER}})
    pf.check("zakaznik nemoze byt agent", "is a customer" in (v.get("org_result") or ""),
             v.get("org_result"))
    v = press(boss, to, "btn_add_agent", {"org_agent_email": {"type": "text", "value": AGENT}})
    pf.check("agent je priradeny", AGENT in (v.get("org_agent_list") or ""), v.get("org_result"))

    o2, _ = pf.new_case(boss, onet["stringId"])
    t2 = pf.tasks_of(boss, o2).get("t_org")
    pf.set_data(boss, t2, {"org_name": {"type": "text", "value": f"Second {ts}"}})
    v2 = press(boss, t2, "btn_add", {"org_new_email": {"type": "text", "value": CUSTOMER}})
    pf.check("clovek nemoze byt v dvoch organizaciach",
             "one organization only" in (v2.get("org_result") or ""), v2.get("org_result"))
    v2 = press(boss, t2, "btn_add", {"org_new_email": {"type": "text", "value": AGENT}})
    pf.check("agent nemoze byt zakaznik", "staff" in (v2.get("org_result") or ""), v2.get("org_result"))
    boss.call("DELETE", f"/api/workflow/case/{o2}")

    agent = pf.Client(AGENT, pf.TEST_PASS)
    pf.check("agent vidi svoju organizaciu", org_id in search_ids(agent, f'processIdentifier:"{ORG}"'))
    ta = pf.tasks_of(agent, org_id)
    pf.check("agent ma len pohlad na organizaciu", list(ta) == ["t_org_view"], list(ta))

    print("\n=== 4. registracia z pozvanky ===")
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
            "token": token, "name": "New", "surname": "Customer",
            "password": base64.b64encode(b"heslo1234").decode()})
        pf.check("registracia z odkazu presla", isinstance(r, dict) and "success" in r, r)
    kolega = pf.Client(novy, "heslo1234", allow_fail=True)
    pf.check("pozvany sa prihlasi vlastnym heslom", bool(kolega.token))

    print("\n=== 5. podanie tiketu ===")
    zak = pf.Client(CUSTOMER, pf.TEST_PASS)       # nove prihlasenie = nove roly
    pf.check("zakaznik vidi kartu Service Desku", CARD in pf.uri_paths(zak, deep=True))
    tnet = pf.newest_net(zak, TICKET)
    case_id, case = pf.new_case(zak, tnet["stringId"])
    t = pf.tasks_of(zak, case_id)
    pf.check("na zaciatku ma zakaznik len podanie", list(t) == ["t_submit"], list(t))
    ts_sub = t.get("t_submit")
    if not ts_sub:
        return pf.report("sdcheck")
    v = pf.values(zak, ts_sub)
    pf.check("organizacia je predvyplnena podla clenstva", v.get("tk_org_name") == org_name,
             v.get("tk_org_name"))
    pf.check("koncept kolega nevidi", case_id not in search_ids(kolega, f'processIdentifier:"{TICKET}"'))
    pf.check("koncept agent nevidi", case_id not in search_ids(agent, f'processIdentifier:"{TICKET}"'))

    # Opusteny formular: uvolnenie ulohy podania koncept zmaze (cancel event).
    draft_id, _ = pf.new_case(zak, tnet["stringId"])
    td0 = pf.tasks_of(zak, draft_id).get("t_submit")
    pf.assign(zak, td0)
    zak.get(f"/api/task/cancel/{td0}")
    gone = False
    for _ in range(10):
        if draft_id not in [c["stringId"] for c in pf.cases_of(boss, TICKET)]:
            gone = True
            break
        time.sleep(1)
    pf.check("opusteny koncept zanikne", gone)

    pf.assign(zak, ts_sub)
    st, r = pf.finish(zak, ts_sub)
    pf.check("prazdne podanie je odmietnute", pf.err_body(r), str(r)[:120])
    subject = f"Login fails {ts}"
    pf.set_data(zak, ts_sub, {
        "tk_type": {"type": "enumeration_map", "value": "bug"},
        "tk_priority": {"type": "enumeration_map", "value": "high"},
        "tk_subject": {"type": "text", "value": subject},
        "tk_description": {"type": "text", "value": "Nobody can log in since 9:00."}})
    beh = json.dumps(pf.behavior(zak, ts_sub, "tk_cat_bug"))
    pf.check("pri type bug sa ukaze druh chyby", "editable" in beh, beh)
    beh = json.dumps(pf.behavior(zak, ts_sub, "tk_cat_change"))
    pf.check("pole zmeny zostane skryte", "hidden" in beh, beh)
    st, r = pf.finish(zak, ts_sub)
    pf.check("bug bez druhu chyby je odmietnuty", pf.err_body(r), str(r)[:120])
    pf.set_data(zak, ts_sub, {"tk_cat_bug": {"type": "enumeration_map", "value": "login"},
                              "tk_steps": {"type": "text", "value": "Open the portal, sign in."}})
    st, r = pf.finish(zak, ts_sub)
    pf.check("podanie preslo", pf.ok_body(r), str(r)[:160])

    t = pf.tasks_of(zak, case_id)
    pf.check("zakaznik po podani vidi 'My ticket'", "t_my" in t, list(t))
    pf.check("zakaznik nevidi ulohy Service Desku", not ({"t_detail", "t_accept"} & set(t)), list(t))
    st, c = zak.get(f"/api/workflow/case/{case_id}")
    pf.check("nazov nesie cislo a predmet", subject in (c.get("title") or ""), c.get("title"))

    q_open = (f'processIdentifier:"{TICKET}" AND dataSet.tk_status.keyValue:'
              '("new" OR "in_progress" OR "waiting" OR "resolved" OR "closed" OR "rejected")')
    pf.check("zakaznik ho vidi v 'Company Tickets'", case_id in search_ids(zak, q_open))
    pf.check("kolega z organizacie ho vidi tiez", case_id in search_ids(kolega, q_open))
    tk = pf.tasks_of(kolega, case_id)
    pf.check("kolega ho len sleduje (t_watch, nie t_my)", list(tk) == ["t_watch"], list(tk))
    pf.check("cudzi clovek ho nevidi", case_id not in search_ids(outsider, q_open))
    pf.check("agent organizacie ho vidi", case_id in search_ids(agent, q_open))

    print("\n=== 6. spracovanie ===")
    tg = pf.tasks_of(agent, case_id)
    pf.check("agent ma detail, prijatie a zamietnutie", {"t_detail", "t_accept", "t_reject"} <= set(tg), list(tg))
    td = tg.get("t_detail")
    if not td:
        return pf.report("sdcheck")
    v = pf.values(agent, td)
    pf.check("termin prvej reakcie je vypocitany", bool(v.get("sla_response_due")), v.get("sla_response_due"))
    pf.check("termin vyriesenia je vypocitany", bool(v.get("sla_resolution_due")), v.get("sla_resolution_due"))
    pf.check("hodiny vyriesenia su z planu (high = 16)", v.get("sla_res_hours") == 16, v.get("sla_res_hours"))
    pf.check("podrobnosti nesu druh chyby", "Problem with login" in (v.get("tk_details") or ""),
             v.get("tk_details"))

    v = press(agent, td, "btn_agent_send", {"tk_agent_msg": {"type": "text", "value": "Looking into it."}})
    pf.check("sprava agenta je v konverzacii", "Looking into it." in (v.get("tk_conversation") or ""),
             v.get("tk_notice"))
    pf.check("prva reakcia je v lehote", v.get("sla_response_met") is True, v.get("sla_response_met"))
    v = press(agent, td, "btn_agent_ask", {"tk_agent_msg": {"type": "text", "value": "Which browser?"}})
    pf.check("pred prijatim sa na zakaznika cakat neda", "Accept the ticket first" in (v.get("tk_notice") or ""),
             v.get("tk_notice"))
    pf.assign(agent, tg["t_accept"])
    st, r = pf.finish(agent, tg["t_accept"])
    pf.check("prijatie preslo", pf.ok_body(r), str(r)[:160])
    v = press(agent, td, "btn_agent_ask", {"tk_agent_msg": {"type": "text", "value": "Which browser?"}})
    pf.check("tiket caka na zakaznika", v.get("tk_status") == "waiting", v.get("tk_notice"))
    pf.check("lehota vyriesenia stoji", bool(v.get("sla_paused_since")), v.get("sla_paused_since"))

    tm = pf.tasks_of(zak, case_id).get("t_my")
    v = press(zak, tm, "btn_customer_send", {"tk_customer_msg": {"type": "text", "value": "Firefox 128"}})
    pf.check("odpoved zakaznika vrati tiket do riesenia", v.get("tk_status") == "in_progress", v.get("tk_notice"))
    pf.check("zakaznik nevidi interne poznamky", "tk_internal" not in v)
    vk = pf.values(kolega, pf.tasks_of(kolega, case_id).get("t_watch"))
    pf.check("kolega vidi konverzaciu", "Firefox 128" in (vk.get("tk_conversation") or ""))
    pf.check("kolega nema kam pisat", "tk_customer_msg" not in vk)
    va = pf.values(agent, td)
    pf.check("pauza skoncila", not va.get("sla_paused_since"), va.get("sla_paused_since"))

    tr = pf.tasks_of(agent, case_id).get("t_resolve")
    pf.check("agent moze vyriesit", bool(tr))
    if tr:
        pf.set_data(agent, tr, {"tk_resolution": {"type": "text", "value": "Cache cleared."}})
        st, r = pf.finish(agent, tr)
        pf.check("vyriesenie preslo", pf.ok_body(r), str(r)[:160])
    tz = pf.tasks_of(zak, case_id)
    v = pf.values(zak, tz["t_my"])
    pf.check("zakaznik vidi stav 'resolved'", v.get("tk_status") == "resolved", v.get("tk_status"))
    pf.check("zakaznik vidi riesenie", v.get("tk_resolution") == "Cache cleared.", v.get("tk_resolution"))
    pf.check("zakaznik moze znovu otvorit aj potvrdit", {"t_reopen", "t_close"} <= set(tz), list(tz))
    if tz.get("t_close"):
        pf.assign(zak, tz["t_close"])
        st, r = pf.finish(zak, tz["t_close"])
        pf.check("potvrdenie vyriesenia preslo", pf.ok_body(r), str(r)[:160])
        pf.check("tiket je zatvoreny", pf.values(zak, tz["t_my"]).get("tk_status") == "closed")

    print("\n=== 7. odobratie z organizacie ===")
    kid = next((k for k, lbl in pf.options(boss, to, "org_remove").items() if novy in str(lbl)), None)
    pf.check("kolega je v ponuke na odobratie", bool(kid))
    if kid:
        v = press(boss, to, "btn_remove", {"org_remove": {"type": "enumeration_map", "value": kid}})
        pf.check("odobratie preslo", "Removed" in (v.get("org_result") or ""), v.get("org_result"))
        kolega2 = pf.Client(novy, "heslo1234")
        pf.check("odobraty kolega tiket uz nevidi", case_id not in search_ids(kolega2, q_open))
        pf.check("odobraty kolega nevidi kartu", CARD not in pf.uri_paths(kolega2, deep=True))
        pf.check("autor ho vidi dalej", case_id in search_ids(zak, q_open))
    aid = next((k for k, lbl in pf.options(boss, to, "org_agent_remove").items() if AGENT in str(lbl)), None)
    pf.check("agent je v ponuke na odobratie", bool(aid))
    if aid:
        v = press(boss, to, "btn_remove_agent", {"org_agent_remove": {"type": "enumeration_map", "value": aid}})
        pf.check("odobratie agenta preslo", "Agent removed" in (v.get("org_result") or ""), v.get("org_result"))
        # Nove prihlasenie ako pri kolegovi: index sa po kaskade obnovuje so
        # sekundovym oneskorenim a hned po zapise by videl este stav pred nim.
        agent2 = pf.Client(AGENT, pf.TEST_PASS)
        pf.check("odobraty agent tiket uz nevidi", case_id not in search_ids(agent2, q_open))
        pf.check("odobraty agent organizaciu nevidi",
                 org_id not in search_ids(agent2, f'processIdentifier:"{ORG}"'))

    return pf.report("sdcheck")


if __name__ == "__main__":
    sys.exit(main())
