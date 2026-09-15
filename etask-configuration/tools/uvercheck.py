#!/usr/bin/env python3
"""
uvercheck - akceptacny test appky Ziadost o uver proti BEZIACEMU enginu.

Overuje to, co sa z XML ani z importu zistit neda: ze kartu vidi kazdy
prihlaseny (ziadost o uver je verejna pre vsetkych zamestnancov, nie len pre
referentov), ze zobrazenia maju stlpce, a ze cely priebeh - podanie,
automaticke rozhodnutie (nahrada DMN tabulky), volitelne manualne posudenie -
vedie k spravnemu stavu a ze naň vidi presne ten, kto ma.

Klient a pomocnici su v `tools/pftestlib.py` - aj s pascami, na ktore sa v tomto
repozitari naletelo (prihlasenie vracia 405 s tokenom v hlavicke, telo setData
je zanorene pod id ulohy, odmietnutie prichadza ako 200 s `error` v tele,
`/api/task/case` neoveruje opravnenia).

Predpoklad: bezi stack (tools/up.sh) a role su pridelene (tools/pfseed.py).

    python3 tools/uvercheck.py
    python3 tools/uvercheck.py --wipe

Exit 0 = vsetko preslo, 1 = nieco zlyhalo.
"""

import sys
import time

import pftestlib as pf

NET = "uver/uv_ziadost"
MENU = "uver/uv_menu"
CARD = "uver"
REFERENT_EMAIL = "operator@test.local"   # ucet s rolou `referent`
OTHER_EMAIL = "druhy@test.local"         # ucet BEZ nej, ale karty (default) vidi
NOONE_EMAIL = "viewer@test.local"        # ucet bez ziadnej procesnej roly


def wait_decided(cl, case_id, tries=16, delay=0.5):
    """Pocka, kym `t_rozhodnutie` (system task za `async.run`) dobehne -
    teda kym `stav_label` na prehlade uz nie je nastavovacie 'vyhodnocovanie'.
    `t_prehlad` je vidno HNED (sink dostane token uz pri podani), takze
    samotna pritomnost ulohy nie je signal - treba pockat na hodnotu poľa."""
    v = {}
    for _ in range(tries):
        t = pf.tasks_of(cl, case_id)
        if t.get("t_prehlad"):
            v = pf.values(cl, t["t_prehlad"])
            if v.get("stav_label") not in (None, "vyhodnocovanie"):
                return v
        time.sleep(delay)
    return v


def main():
    boss = pf.Client("super@netgrif.com", pf.SUPER_PASS)
    if "--wipe" in sys.argv:
        return pf.wipe_cases(boss, NET, "uvercheck")

    referent = pf.Client(REFERENT_EMAIL, pf.TEST_PASS)
    other = pf.Client(OTHER_EMAIL, pf.TEST_PASS)
    noone = pf.Client(NOONE_EMAIL, pf.TEST_PASS)

    print("=== 1. karta v bocnom menu - ziadost o uver je pre kazdeho prihlaseneho ===")
    for nazov, cl in [("s rolou referent", referent), ("bez roly", other), ("uplne bez roli", noone)]:
        paths = pf.uri_paths(cl)
        pf.check(f"{nazov} vidi kartu '{CARD}'", CARD in paths, paths)

    print("\n=== 2. zobrazenia a stlpce ===")
    items = pf.menu_items(boss, prefix="uv_")
    net_title = "Žiadosť o úver"
    for want in [net_title, "Na manuálne posúdenie · Žiadosť o úver",
                 "Schválené · Žiadosť o úver", "Zamietnuté · Žiadosť o úver"]:
        if not pf.check(f"zobrazenie '{want}' existuje", want in items, sorted(items)):
            continue
        st, tl = boss.get(f"/api/task/case/{items[want]}")
        vt = [t for t in (tl or []) if t["transitionId"] == "view"]
        v = pf.values(boss, vt[0]["stringId"]) if vt else {}
        pf.check(f"'{want}' ma predvolene stlpce", bool(v.get("default_headers")),
                 v.get("default_headers"))
        need = {h.rsplit("-", 1)[0] for h in (v.get("default_headers") or "").split(",")
                if h and not h.startswith("meta-")}
        have = set()
        if v.get("filter_case_id"):
            st, fc = boss.get(f"/api/workflow/case/{v['filter_case_id']}")
            for d in (fc.get("immediateData") or []):
                if d.get("allowedNets"):
                    have = set(d["allowedNets"])
        pf.check(f"'{want}' ma v allowedNets siete svojich stlpcov", need <= have,
                 f"treba {sorted(need)}, ma {sorted(have)}")

    mt = [c["title"] for c in pf.cases_of(boss, MENU, size=20)]
    pf.check("bootstrap case menu hlasi 4/4", any("4/4" in t for t in mt), mt)

    net = pf.newest_net(other, NET)
    print(f"\n  siet {net['identifier']} v{net['version']}")

    print("\n=== 3. validacia pri podani ===")
    case_id, _ = pf.new_case(other, net["stringId"])
    t = pf.tasks_of(other, case_id)
    pf.check("na zaciatku je PRESNE jedna uloha (podat ziadost)",
             list(t) == ["t_podat"], list(t))
    podat = t.get("t_podat")
    if not podat:
        return pf.report("uvercheck")

    pf.set_data(other, podat, {
        "meno_ziadatela": {"type": "text", "value": ""},
        "suma_uveru": {"type": "number", "value": 5000},
        "prijem": {"type": "number", "value": 1000},
        "skore": {"type": "number", "value": 700}})
    st, r = pf.finish(other, podat)
    pf.check("prazdne meno ziadatela je odmietnute", pf.err_body(r), str(r)[:160])

    pf.set_data(other, podat, {
        "meno_ziadatela": {"type": "text", "value": "Skore mimo rozsahu"},
        "skore": {"type": "number", "value": 950}})
    st, r = pf.finish(other, podat)
    pf.check("skore nad 900 je odmietnute", pf.err_body(r), str(r)[:160])

    def podaj(cl, meno, suma, prijem, skore, case_id=None):
        """Zalozi (ak netreba existujuci case) a odosle podanie so zadanymi
        udajmi. Vrati case_id."""
        if case_id is None:
            case_id, _ = pf.new_case(cl, net["stringId"])
        task = pf.tasks_of(cl, case_id)["t_podat"]
        pf.set_data(cl, task, {
            "meno_ziadatela": {"type": "text", "value": meno},
            "suma_uveru": {"type": "number", "value": suma},
            "prijem": {"type": "number", "value": prijem},
            "skore": {"type": "number", "value": skore}})
        st, r = pf.finish(cl, task)
        pf.check(f"podanie '{meno}' preslo", pf.ok_body(r), str(r)[:160])
        return case_id

    print("\n=== 4. automaticke SCHVALENIE (vysoke skore, primerana suma) ===")
    c_ok = podaj(other, f"Schvalenie {int(time.time())}", 20000, 3000, 750, case_id=case_id)
    v_ok = wait_decided(other, c_ok)
    pf.check("stav je 'schvalena'", v_ok.get("stav_label") == "schvalena", v_ok.get("stav_label"))
    st, c = other.get(f"/api/workflow/case/{c_ok}")
    pf.check("farba pripadu je zelena (schvalena)", (c or {}).get("color") == "green", (c or {}).get("color"))
    t_ok = pf.tasks_of(other, c_ok)
    pf.check("ziadatelovi po rozhodnuti zostava len prehlad", list(t_ok) == ["t_prehlad"], list(t_ok))
    pf.check("cislo ziadosti je vyplnene", bool(v_ok.get("cislo_ziadosti")), v_ok.get("cislo_ziadosti"))
    t_ok_ref = pf.tasks_of(referent, c_ok)
    pf.check("referent manualne posudenie nevidi (nevzniklo)",
             "t_manualne_preskumanie" not in t_ok_ref, list(t_ok_ref))

    print("\n=== 5. automaticke ZAMIETNUTIE (nizke skore) ===")
    c_rej = podaj(other, f"Zamietnutie {int(time.time())}", 5000, 1000, 400)
    v_rej = wait_decided(other, c_rej)
    pf.check("stav je 'zamietnuta'", v_rej.get("stav_label") == "zamietnuta", v_rej.get("stav_label"))
    st, c = other.get(f"/api/workflow/case/{c_rej}")
    pf.check("farba pripadu je cervena (zamietnuta)", (c or {}).get("color") == "red", (c or {}).get("color"))

    print("\n=== 6. MANUALNE POSUDENIE (stredne skore / vysoka suma) ===")
    c_rev = podaj(other, f"Preskumanie {int(time.time())}", 50000, 2000, 650)
    v_rev = wait_decided(other, c_rev)
    pf.check("stav je 'na_preskumani'", v_rev.get("stav_label") == "na_preskumani", v_rev.get("stav_label"))
    t_rev_owner = pf.tasks_of(other, c_rev)
    pf.check("ziadatel v stave 'na preskumani' vidi len prehlad (nie posudenie)",
             list(t_rev_owner) == ["t_prehlad"], list(t_rev_owner))

    t_rev_ref = pf.tasks_of(referent, c_rev)
    pf.check("referent vidi manualne posudenie", "t_manualne_preskumanie" in t_rev_ref, list(t_rev_ref))
    t_rev_noone = pf.tasks_of(noone, c_rev)
    pf.check("cudzi pouzivatel (ani referent, ani ziadatel) nevidi ANI prehlad ANI posudenie",
             list(t_rev_noone) == [], list(t_rev_noone))

    posudenie = t_rev_ref.get("t_manualne_preskumanie")
    if posudenie:
        pf.set_data(referent, posudenie, {
            "komentar_referenta": {"type": "text", "value": ""},
            "rozhodnutie_referenta": {"type": "enumeration_map", "value": "schvalit"}})
        st, r = pf.finish(referent, posudenie)
        pf.check("prazdny komentar referenta je odmietnuty", pf.err_body(r), str(r)[:160])

        pf.set_data(referent, posudenie, {
            "komentar_referenta": {"type": "text", "value": "Doklady v poriadku, schvalene."},
            "rozhodnutie_referenta": {"type": "enumeration_map", "value": "schvalit"}})
        st, r = pf.finish(referent, posudenie)
        pf.check("rozhodnutie referenta preslo", pf.ok_body(r), str(r)[:160])

        t_final = pf.tasks_of(other, c_rev)
        v_final = pf.values(other, t_final["t_prehlad"]) if t_final.get("t_prehlad") else {}
        pf.check("po posudeni je stav 'schvalena'", v_final.get("stav_label") == "schvalena",
                 v_final.get("stav_label"))
        pf.check("meno referenta je zapisane", bool(v_final.get("vybavil")), v_final.get("vybavil"))
        pf.check("komentar referenta je vidiet v prehlade",
                 v_final.get("komentar_referenta") == "Doklady v poriadku, schvalene.",
                 v_final.get("komentar_referenta"))

    return pf.report("uvercheck")


if __name__ == "__main__":
    sys.exit(main())
