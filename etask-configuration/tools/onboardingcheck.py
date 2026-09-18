#!/usr/bin/env python3
"""
onboardingcheck - akceptacny test appky Nástup zamestnanca proti BEZIACEMU enginu.

Overuje to, co sa z XML ani z importu zistit neda: ze kartu vidia spravne ucty,
ze zobrazenia maju stlpce, ze ziadost dostane na schvalenie PRAVE TEN vybrany
nadriadeny (a nikto iny), a ze na konci vznikne ucet, ktorym sa da prihlasit.

Klient a pomocnici su v `tools/pftestlib.py` - aj s pascami, na ktore sa v tomto
repozitari naletelo (prihlasenie vracia 405 s tokenom v hlavicke, telo setData
je zanorene pod id ulohy, odmietnutie prichadza ako 200 s `error` v tele,
`/api/task/case` neoveruje opravnenia).

Predpoklad: bezi stack (tools/up.sh) a role su pridelene (tools/pfseed.py).

    python3 tools/onboardingcheck.py
    python3 tools/onboardingcheck.py --wipe

Exit 0 = vsetko preslo, 1 = nieco zlyhalo.

Pozor na `admin@test.local`: ma ROLE_ADMIN, ktora obchadza VSETKY opravnenia
Petriflow. Hranice sa preto overuju na ucte bez roli, nie na nom (RUNBOOK 11).
"""

import base64
import sys
import time

import pftestlib as pf

NET = "onboarding/on_nastup"
MENU = "onboarding/on_menu"
CARD = "onboarding"

HR_EMAIL = "admin@test.local"        # rola `personalista`
IT_EMAIL = "druhy@test.local"        # rola `it_spravca`
CUDZI_EMAIL = "viewer@test.local"    # ziadna z troch roli

# Schvalovatela si test NEVYBERA podla mena - vyberie prvu moznost, ktoru mu
# siet ponukne, a az potom sa z `on_schvalovatelia` dozvie, komu ziadost
# pridelil. Tak test prezije zmenu v seed.json aj premenovanie uctov.
HESLA = {
    "super@netgrif.com": pf.SUPER_PASS,
    "admin@test.local": pf.TEST_PASS,
    "operator@test.local": pf.TEST_PASS,
    "druhy@test.local": pf.TEST_PASS,
    "viewer@test.local": pf.TEST_PASS,
}

# Stale rovnaky, aby test nenechaval za sebou novy ucet pri kazdom spusteni.
# Prvy beh ho zaklada, dalsie prejdu vetvou "ucet uz v instancii bol" - a tym
# sa otestuje aj ona.
NOVY_EMAIL = "test.nastup@ditec.local"
# Heslo ide do pola ako BASE64 - `formPassword` v delegate ho dekoduje, lebo
# frontend ho tak posiela. Plain text prejde ako platny base64 a dekoduje sa
# na smeti, ktore instancia odmietne ako prislabe heslo - a hlaska o tom
# nepovie ani slovo (min. dlzka je 8, `test1234` ju splna).
NOVE_HESLO = "Nastup2026!"
NOVE_HESLO_B64 = base64.b64encode(NOVE_HESLO.encode()).decode()

VIEWS = [
    "Nástup zamestnanca",
    "Rozpísané · Nástupy",
    "Na schválenie · Nástupy",
    "Zakladajú sa účty · Nástupy",
    "Nastúpení · Nástupy",
    "Zamietnuté · Nástupy",
]


def stav(cl, case_id):
    """Stav pripadu tak, ako ho vidi read-only pohlad `t_on_prehlad`.

    Vo formularoch, v ktorych sa pracuje, stav ZAMERNE nie je - kde pripad
    stoji, povie uloha, ktoru ma clovek pred sebou. Preto sa cita odtialto.
    """
    t = pf.tasks_of(cl, case_id)
    if "t_on_prehlad" not in t:
        return None
    return pf.values(cl, t["t_on_prehlad"]).get("on_stav_label")


def userlist(hodnota):
    """Pouzivatelia z pola typu `userList`.

    Hodnota NIE JE zoznam - je to `{"userValues": [{id, email, fullName, ...}]}`.
    Kto caka zoznam, dostane prazdno a nic to nepovie.
    """
    if isinstance(hodnota, dict):
        return hodnota.get("userValues") or []
    if isinstance(hodnota, list):
        return hodnota
    return []


def main():
    boss = pf.Client("super@netgrif.com", pf.SUPER_PASS)
    if "--wipe" in sys.argv:
        return pf.wipe_cases(boss, NET, "onboardingcheck")

    print("=== 1. karta v bocnom menu ===")
    hr = pf.Client(HR_EMAIL, pf.TEST_PASS)
    it = pf.Client(IT_EMAIL, pf.TEST_PASS)
    cudzi = pf.Client(CUDZI_EMAIL, pf.TEST_PASS)

    for nazov, cl in [("personalista", hr), ("IT správca", it)]:
        paths = pf.uri_paths(cl)
        pf.check(f"{nazov} vidi kartu '{CARD}'", CARD in paths, paths)
    # Viditelnost karty riadi `uriNodes` v processes.json - a ten sa PAKUJE DO
    # JARU. V instancii postavenej zo starsieho manifestu polozka pre
    # `onboarding` chyba, uzol je vtedy viditelny pre kazdeho prihlaseneho
    # a tato kontrola zlyha bez toho, aby bola chyba v sieti.
    pf.check(f"ucet bez roly kartu '{CARD}' nevidi", CARD not in pf.uri_paths(cudzi),
             f"{pf.uri_paths(cudzi)} - ak je karta vidno, bezi engine zo starsieho "
             f"manifestu (uriNodes sa pakuje do jaru)")

    print("\n=== 2. zobrazenia a stlpce ===")
    items = pf.menu_items(boss, prefix="on_")
    for want in VIEWS:
        if not pf.check(f"zobrazenie '{want}' existuje", want in items, sorted(items)):
            continue
        st, tl = boss.get(f"/api/task/case/{items[want]}")
        vt = [t for t in (tl or []) if t["transitionId"] == "view"]
        v = pf.values(boss, vt[0]["stringId"]) if vt else {}
        pf.check(f"'{want}' ma predvolene stlpce", bool(v.get("default_headers")),
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
        pf.check(f"'{want}' ma v allowedNets siete svojich stlpcov", need <= have,
                 f"treba {sorted(need)}, ma {sorted(have)}")

    mt = [c["title"] for c in pf.cases_of(boss, MENU, size=20)]
    pf.check(f"bootstrap case menu hlasi {len(VIEWS)}/{len(VIEWS)}",
             any(f"{len(VIEWS)}/{len(VIEWS)}" in t for t in mt), mt)

    print("\n=== 3. ziadost ===")
    net = pf.newest_net(hr, NET)
    print(f"  siet {net['identifier']} v{net['version']}")
    case_id, case = pf.new_case(hr, net["stringId"])
    t = pf.tasks_of(hr, case_id)
    # `t_on_prehlad` visi na read arcu z miesta, ktore nikto nekonzumuje, takze
    # je dostupny cely zivot pripadu - aj hned na zaciatku (B25).
    pf.check("na zaciatku su ulohy 'ziadost' a 'prehlad'",
             sorted(t) == ["t_on_prehlad", "t_on_ziadost"], sorted(t))
    ziadost = t.get("t_on_ziadost")
    if not ziadost:
        return pf.report("onboardingcheck")

    # Priradenie spusta `assign` udalost, ktora stava moznosti schvalovatela.
    # `change ... options {}` v `create` udalosti pripadu sa NEUCHOVA (B11),
    # takze bez tohto kroku by bol vyber prazdny.
    pf.assign(hr, ziadost)
    moznosti = pf.options(hr, ziadost, "on_schvalovatel_vyber")
    pf.check("vyber nadriadeneho ma moznosti", bool(moznosti), moznosti)
    # Kto ziadost pise, vie siet z `on_ziadatel` - a presne toho ma zo zoznamu
    # schvalovatelov vyhodit. Porovnava sa ID, nie meno: mien podobnych
    # "Admin ..." je v testovacej instancii viac a heuristika na meno
    # hlasila chybu tam, kde ziadna nebola.
    prehlad0 = pf.tasks_of(hr, case_id).get("t_on_prehlad")
    ja = userlist(pf.values(hr, prehlad0).get("on_ziadatel")) if prehlad0 else []
    moje_id = (ja[0].get("id") if ja else None)
    pf.check("zadavatel sam sebe v ponuke nie je", moje_id not in moznosti,
             f"zadavatel {moje_id}, v ponuke {sorted(moznosti)}")
    if not moznosti:
        return pf.report("onboardingcheck")
    vybrany = sorted(moznosti)[0]

    # Formular pracovnej ulohy stav NEUKAZUJE - je to procesny udaj, nie udaj,
    # ktory by clovek pri pisani ziadosti potreboval.
    polia = pf.values(hr, ziadost)
    pf.check("formular ziadosti stav NEobsahuje", "on_stav_label" not in polia,
             sorted(polia))

    # Odmietnutie prichadza ako HTTP 200 s `error` v tele, nie ako 4xx.
    pf.set_data(hr, ziadost, {"on_meno": {"type": "text", "value": ""}})
    st, r = pf.finish(hr, ziadost)
    pf.check("ziadost bez mena je odmietnuta", pf.err_body(r), str(r)[:110])

    priezvisko = f"Testovic{int(time.time()) % 100000}"
    zadanie = {
        "on_meno": {"type": "text", "value": "Jozef"},
        "on_priezvisko": {"type": "text", "value": priezvisko},
        "on_pozicia": {"type": "text", "value": "Vývojár"},
        "on_oddelenie": {"type": "enumeration_map", "value": "vyvoj"},
        "on_uvazok": {"type": "enumeration_map", "value": "trvaly"},
        "on_nastup_datum": {"type": "date", "value": "2026-10-01"},
        "on_firemny_email": {"type": "text", "value": NOVY_EMAIL},
        "on_systemy": {"type": "multichoice_map", "value": ["entra", "atlassian", "netgrif"]},
        "on_schvalovatel_vyber": {"type": "enumeration_map", "value": vybrany},
    }
    pf.set_data(hr, ziadost, zadanie)
    st, r = pf.finish(hr, ziadost)
    pf.check("podanie preslo", pf.ok_body(r), str(r)[:110])
    pf.check("stav je 'schvalenie'", stav(hr, case_id) == "schvalenie", stav(hr, case_id))

    raw = pf.tasks_raw(boss, case_id)
    pf.check("uloha schvalenia vznikla", "t_on_schvalenie" in raw, sorted(raw))
    pf.check("ucet bez roli z pripadu nevidi nic",
             not pf.tasks_of(cudzi, case_id), sorted(pf.tasks_of(cudzi, case_id)))

    print("\n=== 4. ziadost ma len VYBRANY nadriadeny ===")
    prehlad = pf.tasks_of(hr, case_id).get("t_on_prehlad")
    schv = userlist(pf.values(hr, prehlad).get("on_schvalovatelia")) if prehlad else []
    email = (schv[0].get("email") if schv else None)
    if not pf.check("v `on_schvalovatelia` je vybrany clovek", bool(email), email):
        return pf.report("onboardingcheck")
    print(f"  schvaluje: {email}")
    if email not in HESLA:
        pf.check(f"heslo k uctu {email} test pozna", False,
                 "doplň ho do HESLA v tomto súbore")
        return pf.report("onboardingcheck")
    schvalovatel = pf.Client(email, HESLA[email])
    pf.check("vybrany nadriadeny ulohu vidi",
             "t_on_schvalenie" in pf.tasks_of(schvalovatel, case_id),
             sorted(pf.tasks_of(schvalovatel, case_id)))
    # IT ma rolu `it_spravca`, nie `veduci`, a `userRef` na neho nemieri -
    # schvalovaciu ulohu vidiet nesmie. Toto je ta hranica, kvoli ktorej na
    # prechode NIE JE `roleRef` (zjednocoval by sa s `userRef`).
    pf.check("IT spravca schvalovaciu ulohu NEvidi",
             "t_on_schvalenie" not in pf.tasks_of(it, case_id),
             sorted(pf.tasks_of(it, case_id)))

    print("\n=== 5. vratenie na doplnenie ===")
    uloha = pf.tasks_of(schvalovatel, case_id).get("t_on_schvalenie")
    pf.set_data(schvalovatel, uloha,
                {"on_rozhodnutie": {"type": "enumeration_map", "value": "vratit"}})
    st, r = pf.finish(schvalovatel, uloha)
    pf.check("vratenie bez komentara je odmietnute", pf.err_body(r), str(r)[:110])

    pf.set_data(schvalovatel, uloha, {
        "on_rozhodnutie": {"type": "enumeration_map", "value": "vratit"},
        "on_komentar": {"type": "text", "value": "Doplň telefón na nastupujúceho."}})
    st, r = pf.finish(schvalovatel, uloha)
    pf.check("vratenie preslo", pf.ok_body(r), str(r)[:110])
    pf.check("stav je spat na 'navrh'", stav(hr, case_id) == "navrh", stav(hr, case_id))
    ziadost2 = pf.tasks_of(hr, case_id).get("t_on_ziadost")
    pf.check("zadavatelovi sa uloha znova otvorila", bool(ziadost2),
             sorted(pf.tasks_of(hr, case_id)))
    if ziadost2:
        pf.assign(hr, ziadost2)
        pf.check("a vidi v nej komentar, preco sa vratila",
                 "telefón" in ((pf.values(hr, ziadost2).get("on_komentar") or "")),
                 pf.values(hr, ziadost2).get("on_komentar"))

    print("\n=== 6. schvalenie ===")
    pf.set_data(hr, ziadost2, zadanie)
    pf.finish(hr, ziadost2)
    uloha = pf.tasks_of(schvalovatel, case_id).get("t_on_schvalenie")
    pf.set_data(schvalovatel, uloha,
                {"on_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
    st, r = pf.finish(schvalovatel, uloha)
    pf.check("nadriadeny schvalil", pf.ok_body(r), str(r)[:110])
    pf.check("stav je 'provisioning'", stav(hr, case_id) == "provisioning", stav(hr, case_id))

    print("\n=== 7. vytvorenie uctov ===")
    u = pf.tasks_of(it, case_id).get("t_on_provisioning")
    if not pf.check("IT vidi ulohu vytvorenia uctov", bool(u), sorted(pf.tasks_of(it, case_id))):
        return pf.report("onboardingcheck")

    pf.assign(it, u)
    st, r = pf.finish(it, u)
    pf.check("ukoncenie bez protokolu je odmietnute", pf.err_body(r), str(r)[:110])

    # `saveWhileTyping` na hesle a na textovych poliach je tu podstatne: bez
    # neho by akcia tlacidla citala hodnoty z pred pisania (RUNBOOK 6).
    pf.set_data(it, u, {
        "on_heslo": {"type": "text", "value": NOVE_HESLO_B64},
        "on_entra_skupiny": {"type": "text", "value": "GRP-VYVOJ"},
        "on_atlassian_tim": {"type": "text", "value": "ETASK"},
        "on_profil": {"type": "enumeration_map", "value": "zamestnanec"}})
    st, r = pf.set_data(it, u, {"btn_on_provision": {"type": "button", "value": 0}})
    pf.check("tlacidlo 'Vytvoriť účty' preslo", pf.ok_body(r), str(r)[:160])

    v = pf.values(it, u)
    protokol = (v.get("on_protokol") or "")
    pf.check("protokol ma riadok pre Entra ID", "Entra ID" in protokol, protokol[:200])
    pf.check("protokol ma riadok pre Atlassian", "Atlassian" in protokol, protokol[:200])
    pf.check("protokol nesie skupiny z formulara", "GRP-VYVOJ" in protokol, protokol[:200])
    pf.check("Netgrif ucet je zapisany", v.get("on_ucet") == NOVY_EMAIL, v.get("on_ucet"))

    st, r = pf.finish(it, u)
    pf.check("ukoncenie nastupu preslo", pf.ok_body(r), str(r)[:110])
    pf.check("stav je 'hotovo'", stav(it, case_id) == "hotovo", stav(it, case_id))
    st, c = boss.get(f"/api/workflow/case/{case_id}")
    pf.check("nazov pripadu nesie cloveka, nie stav", priezvisko in (c["title"] or ""), c["title"])
    pf.check("farba pripadu je zelena", c.get("color") == "green", c.get("color"))
    pf.check("na konci zostava len read-only pohlad",
             sorted(pf.tasks_of(it, case_id)) == ["t_on_prehlad"], sorted(pf.tasks_of(it, case_id)))

    print("\n=== 8. novy clovek sa vie prihlasit ===")
    # Toto je cela pointa zadania: po dobehnuti procesu ma clovek pristup
    # do tejto aplikacie. Entra ID a Atlassian su zatial simulovane.
    novy = pf.Client(NOVY_EMAIL, NOVE_HESLO, allow_fail=True)
    if pf.check("vytvoreny ucet sa prihlasi", bool(novy.token), NOVY_EMAIL):
        paths = pf.uri_paths(novy)
        pf.check(f"a kartu '{CARD}' zatial nevidi (profil 'zamestnanec')",
                 CARD not in paths,
                 f"{paths} - to iste ako vyssie: uriNodes zo starsieho jaru")

    print("\n=== 9. zobrazenie 'Nastúpení' filtruje podla datoveho pola ===")
    # Podla KLUCA moznosti - popisok sa prekladom meni, kluc nie.
    q = f'processIdentifier:"{NET}" AND dataSet.on_stav_label.keyValue:"hotovo"'
    st, r = boss.post("/api/workflow/case/search?size=100", {"query": q})
    ids = [x["stringId"] for x in (r.get("_embedded") or {}).get("cases", [])] \
        if isinstance(r, dict) else []
    pf.check("ukonceny pripad je medzi 'Nastúpení'", case_id in ids, f"{len(ids)} pripadov")

    return pf.report("onboardingcheck")


if __name__ == "__main__":
    sys.exit(main())
