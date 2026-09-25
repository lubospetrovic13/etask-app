#!/usr/bin/env python3
"""
sddemo - demo data Service Desku do BEZIACEHO enginu.

Zalozi to, co by inak naklikal spravca a ludia klienta, a vsetko ide cez
tie iste siete a tlacidla ako v portali (ziadny zapis do databazy):

  * tri SLA plany (Basic, Standard, Premium),
  * dvoch agentov a dve organizacie s ludmi - pozvanky naozaj odidu do
    mailpitu a ucty sa z nich zaregistruju s heslom DEMO_PASSWORD,
  * deviat tiketov v roznych stavoch: novy, v rieseni, caka na zakaznika,
    vyrieseny, zatvoreny, zamietnuty - s konverzaciou.

Na konci vypise, kto sa ako prihlasi.

    tools/up.sh --docker
    python3 tools/sddemo.py

Druhe spustenie nic nezdvoji: organizacia, ktora uz existuje, sa preskoci
aj s jej tiketmi. Od nuly: tools/up.sh --docker --fresh (ZMAZE data).
"""

import base64
import os
import sys
import time

import pftestlib as pf
from sdcheck import AGENT, ORG, PLAN, TICKET, invite_token, press

PASSWORD = os.environ.get("DEMO_PASSWORD", "demo1234")

PLANS = [
    {"name": "Basic", "code": "BAS", "resp": [4, 8, 16, 24], "res": [16, 40, 80, 160],
     "from": 8, "to": 16, "accounts": 5, "agents": 1},
    {"name": "Standard", "code": "STD", "resp": [1, 2, 4, 8], "res": [8, 16, 40, 80],
     "from": 8, "to": 16, "accounts": 10, "agents": 2},
    {"name": "Premium", "code": "PRM", "resp": [1, 1, 2, 4], "res": [4, 8, 24, 40],
     "from": 7, "to": 19, "accounts": 25, "agents": 3},
]
PRIORITIES = ["critical", "high", "medium", "low"]

AGENTS = [("anna.agent@demo.local", "Anna", "Agentová"), ("peter.agent@demo.local", "Peter", "Agent")]

ORGS = [
    {"name": "Acme s.r.o.", "code": "ACME", "plan": "Premium", "contact": "Jana Nováková",
     "agents": ["anna.agent@demo.local", AGENT],
     "people": [("jana.novakova@acme.demo", "Jana", "Nováková"),
                ("martin.kral@acme.demo", "Martin", "Kráľ"),
                ("eva.biela@acme.demo", "Eva", "Biela")]},
    {"name": "Globex a.s.", "code": "GLBX", "plan": "Basic", "contact": "Tomáš Horák",
     "agents": ["peter.agent@demo.local"],
     "people": [("tomas.horak@globex.demo", "Tomáš", "Horák"),
                ("lucia.mala@globex.demo", "Lucia", "Malá")]},
]

# (autor, typ, podkategoria-pole, podkategoria, priorita, predmet, popis, extra, co s nim)
TICKETS = [
    ("jana.novakova@acme.demo", "bug", "tk_cat_bug", "production", "critical",
     "Checkout fails with error 500",
     "Since 8:30 every order ends with 'Internal Server Error' on the payment step.",
     {"tk_environment": ("enumeration_map", "production"),
      "tk_steps": ("text", "Add any product to the cart, go to checkout, pay by card.")},
     "in_progress"),
    ("martin.kral@acme.demo", "change", "tk_cat_change", "feature", "medium",
     "Export invoices to CSV",
     "Our accountants need the monthly invoice list as a CSV file.",
     {"tk_justification": ("text", "Manual copying takes a day every month.")},
     "new"),
    ("eva.biela@acme.demo", "service", "tk_cat_service", "logs", "high",
     "Investigate slow login on Monday",
     "On Monday morning the login took over a minute for all of us.",
     {"tk_system": ("text", "Production portal"), "tk_window": ("text", "Any time")},
     "waiting"),
    ("jana.novakova@acme.demo", "bug", "tk_cat_bug", "login", "low",
     "Password reset e-mail does not arrive",
     "Two colleagues asked for a new password yesterday and got no e-mail.",
     {}, "resolved"),
    ("martin.kral@acme.demo", "other", None, None, "low",
     "Question about the August invoice",
     "The August invoice has one item twice. Is that right?",
     {}, "closed"),
    ("tomas.horak@globex.demo", "service", "tk_cat_service", "migration", "medium",
     "Migrate customer data from the old CRM",
     "We are switching off the old CRM at the end of October and need the customers moved.",
     {"tk_system": ("text", "CRM 2014, MS SQL"), "tk_window": ("text", "Weekends only")},
     "in_progress"),
    ("lucia.mala@globex.demo", "bug", "tk_cat_bug", "testing", "high",
     "Save button overlaps the text",
     "On the testing environment the Save button covers the last line of the form.",
     {"tk_environment": ("enumeration_map", "testing")},
     "rejected"),
    ("lucia.mala@globex.demo", "change", "tk_cat_change", "improvement", "low",
     "Dark mode for the portal",
     "Several of us work late and would appreciate a dark theme.",
     {}, "new"),
    ("tomas.horak@globex.demo", "bug", "tk_cat_bug", "production", "high",
     "Reports show yesterday's numbers",
     "The dashboard reports are one day behind since the last update.",
     {"tk_environment": ("enumeration_map", "production")},
     "resolved"),
]


def signup(email, name, surname):
    """Pozvany ucet si z mailu nastavi heslo - presne ako clovek z odkazu."""
    token = None
    for _ in range(15):
        token = invite_token(email)
        if token:
            break
        time.sleep(1)
    if not token:
        return False
    anon = pf.Client("viewer@test.local", pf.TEST_PASS)
    st, r = anon.post("/api/auth/signup", {
        "token": token, "name": name, "surname": surname,
        "password": base64.b64encode(PASSWORD.encode()).decode()})
    return isinstance(r, dict) and "success" in r


def can_login(email, password):
    return bool(pf.Client(email, password, allow_fail=True).token)


def ensure_account(email, name, surname, result):
    if "invitation sent" in (result or "").lower() or "invited" in (result or "").lower():
        ok = signup(email, name, surname)
        print(f"  {'registrovany' if ok else 'REGISTRACIA ZLYHALA'}: {email}")


def task_of(cl, case_id, transition):
    return pf.tasks_of(cl, case_id).get(transition)


def run_task(cl, case_id, transition, vals=None):
    tid = task_of(cl, case_id, transition)
    if not tid:
        raise RuntimeError(f"{cl.email} nema ulohu {transition} v {case_id}")
    if vals:
        pf.set_data(cl, tid, vals)
    else:
        pf.assign(cl, tid)
    st, r = pf.finish(cl, tid)
    if not pf.ok_body(r):
        raise RuntimeError(f"{transition}: {r}")


def main():
    boss = pf.Client("super@netgrif.com", pf.SUPER_PASS)

    existing = {(o.get("title") or "") for o in pf.cases_of(boss, ORG)}
    todo = [o for o in ORGS if o["name"] not in existing]
    if not todo:
        print("sddemo: demo organizacie uz existuju - nic nerobim")
        return 0

    print("== SLA plany")
    pnet = pf.newest_net(boss, PLAN)
    plans = {(p.get("title") or ""): p["stringId"] for p in pf.cases_of(boss, PLAN)}
    for p in PLANS:
        if p["name"] in plans:
            continue
        pid, _ = pf.new_case(boss, pnet["stringId"])
        vals = {"sp_name": {"type": "text", "value": p["name"]},
                "sp_code": {"type": "text", "value": p["code"]},
                "sp_work_from": {"type": "number", "value": p["from"]},
                "sp_work_to": {"type": "number", "value": p["to"]},
                "sp_max_accounts": {"type": "number", "value": p["accounts"]},
                "sp_max_agents": {"type": "number", "value": p["agents"]}}
        for i, prio in enumerate(PRIORITIES):
            vals[f"sp_resp_{prio}"] = {"type": "number", "value": p["resp"][i]}
            vals[f"sp_res_{prio}"] = {"type": "number", "value": p["res"][i]}
        pf.set_data(boss, pf.tasks_of(boss, pid)["t_plan"], vals)
        plans[p["name"]] = pid
        print(f"  {p['name']}")

    print("== Organizacie, agenti a ludia")
    onet = pf.newest_net(boss, ORG)
    names = dict((e, (n, s)) for e, n, s in AGENTS)
    for o in todo:
        oid, _ = pf.new_case(boss, onet["stringId"])
        to = pf.tasks_of(boss, oid)["t_org"]
        pf.set_data(boss, to, {"org_name": {"type": "text", "value": o["name"]},
                               "org_code": {"type": "text", "value": o["code"]},
                               "org_contact": {"type": "text", "value": o["contact"]}})
        pf.set_data(boss, to, {"org_plan": {"type": "enumeration_map", "value": plans[o["plan"]]}})
        print(f"  {o['name']} ({o['plan']})")
        for email in o["agents"]:
            v = press(boss, to, "btn_add_agent", {"org_agent_email": {"type": "text", "value": email}})
            print(f"    agent {email}: {(v.get('org_result') or '').splitlines()[0]}")
            if email in names:
                ensure_account(email, *names[email], v.get("org_result"))
        for email, name, surname in o["people"]:
            v = press(boss, to, "btn_add", {"org_new_email": {"type": "text", "value": email}})
            print(f"    {email}: {(v.get('org_result') or '').splitlines()[0]}")
            ensure_account(email, name, surname, v.get("org_result"))

    print("== Tikety")
    clients = {}

    def client(email):
        if email not in clients:
            pw = pf.TEST_PASS if email.endswith("@test.local") else PASSWORD
            clients[email] = pf.Client(email, pw)
        return clients[email]

    org_of = {e: o for o in todo for e, _, _ in o["people"]}
    tnet = None
    for author, typ, cat_field, cat, prio, subject, desc, extra, fate in TICKETS:
        if author not in org_of:
            continue
        cust = client(author)
        agent = client(org_of[author]["agents"][0])
        if tnet is None:
            tnet = pf.newest_net(cust, TICKET)
        cid, _ = pf.new_case(cust, tnet["stringId"])
        vals = {"tk_type": {"type": "enumeration_map", "value": typ},
                "tk_priority": {"type": "enumeration_map", "value": prio},
                "tk_subject": {"type": "text", "value": subject},
                "tk_description": {"type": "text", "value": desc}}
        if cat_field:
            vals[cat_field] = {"type": "enumeration_map", "value": cat}
        for k, (t, val) in extra.items():
            vals[k] = {"type": t, "value": val}
        # Typ najprv: jeho `set` akcia ukaze polia podkategorie.
        pf.set_data(cust, task_of(cust, cid, "t_submit"), {"tk_type": vals.pop("tk_type")})
        run_task(cust, cid, "t_submit", vals)

        if fate == "rejected":
            run_task(agent, cid, "t_reject", {"tk_reject_reason": {
                "type": "text", "value": "This is the same issue as the Save button ticket from last week - "
                                         "we fixed it there and it will be on testing tomorrow."}})
        elif fate != "new":
            td = task_of(agent, cid, "t_detail")
            press(agent, td, "btn_agent_send", {"tk_agent_msg": {
                "type": "text", "value": "Thank you, we are looking into it."}})
            run_task(agent, cid, "t_accept")
            press(agent, td, "btn_note", {"tk_note_new": {
                "type": "text", "value": "Checked the logs, looks related to the last deployment."}})
            if fate == "waiting":
                press(agent, td, "btn_agent_ask", {"tk_agent_msg": {
                    "type": "text", "value": "Could you tell us the exact time and which browser you use?"}})
            if fate == "in_progress":
                press(agent, td, "btn_agent_ask", {"tk_agent_msg": {
                    "type": "text", "value": "Does it happen for every user, or only some?"}})
                tm = task_of(cust, cid, "t_my")
                press(cust, tm, "btn_customer_send", {"tk_customer_msg": {
                    "type": "text", "value": "For everyone in our office, in Chrome and Firefox."}})
            if fate in ("resolved", "closed"):
                run_task(agent, cid, "t_resolve", {"tk_resolution": {
                    "type": "text", "value": "Fixed and deployed. Please let us know if you still see it."}})
            if fate == "closed":
                run_task(cust, cid, "t_close")
        print(f"  {fate:12} {subject}  ({author})")

    print("\n== Prihlasenie (portal http://localhost:4200)")
    print(f"  spravca    super@netgrif.com / {pf.SUPER_PASS}")
    print(f"  agent      {AGENT} / {pf.TEST_PASS}   (Acme)")
    for e, n, s in AGENTS:
        print(f"  agent      {e} / {PASSWORD}")
    for o in todo:
        for e, n, s in o["people"]:
            print(f"  zakaznik   {e} / {PASSWORD}   ({o['name']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
