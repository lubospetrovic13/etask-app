#!/usr/bin/env python3
"""
onboardingcheck - akceptacny test appky Nástup nového zamestnanca proti
BEZIACEMU enginu.

Overuje to, co sa z XML ani z importu zistit neda: ze karta je vidno spravnym
uctom, ze zobrazenia maju stlpce, a ze priebeh pripadu robi to, co ma.

Tazisko je na dvoch veciach, ktore su cele o beznom stave siete a v XML
vyzeraju rovnako spravne aj ked spravne nie su:

  * TRI VETVY BEZIA NARAZ a kazda patri inej role. Kontroluje sa, ze po podani
    existuju vsetky tri ulohy sucasne a ze kazdu vidi prave jej rola.
  * AND-JOIN. `t_on_den_nastupu` ma tri regular vstupne obluky, takze uloha
    „den nastupu" NEEXISTUJE, kym nie su hotove vsetky tri vetvy. Testuje sa po
    kazdej vetve zvlast - keby bol join napisany ako guard v Groovy, uloha by
    tam bola uz po prvej vetve a test by to chytil.

Klient a pomocnici su v `tools/pftestlib.py` - aj s pascami, na ktore sa v tomto
repozitari naletelo (prihlasenie vracia 405 s tokenom v hlavicke, telo setData
je zanorene pod id ulohy, odmietnutie prichadza ako 200 s `error` v tele,
`/api/task/case` neoveruje opravnenia - preto `tasks_raw` vs. `tasks_of`).

Predpoklad: bezi stack (tools/up.sh) a role su pridelene (tools/pfseed.py).

    python3 tools/onboardingcheck.py
    python3 tools/onboardingcheck.py --wipe

Exit 0 = vsetko preslo, 1 = nieco zlyhalo.
"""

import sys
import time

import pftestlib as pf

NET = "onboarding/on_nastup"
MENU = "onboarding/on_menu"
CARD = "onboarding"

# Ucty podla rol. `admin@test.local` ma ROLE_ADMIN, ktora obchadza vsetky
# opravnenia Petriflow - hranice sa preto overuju na uctoch BEZ nej.
HR_EMAIL = "admin@test.local"        # rola hr (zadavatel)
IT_EMAIL = "operator@test.local"     # roly it + nadriadeny, bez ROLE_ADMIN
MAJ_EMAIL = "druhy@test.local"       # rola majetok, bez ROLE_ADMIN
NIC_EMAIL = "viewer@test.local"      # bez procesnych rol

POHLADY = [
    "Nástup nového zamestnanca",
    "Prebieha príprava · Nástup nového zamestnanca",
    "Pripravené na nástup · Nástup nového zamestnanca",
    "Nastúpili · Nástup nového zamestnanca",
]


def user_id(cl, email):
    st, r = cl.post("/api/user/search?size=300", {"fulltext": email})
    users = (r.get("_embedded") or {}).get("users", []) if isinstance(r, dict) else []
    for u in users:
        if (u.get("email") or "").lower() == email.lower():
            return u.get("id")
    return None


def main():
    boss = pf.Client("super@netgrif.com", pf.SUPER_PASS)
    if "--wipe" in sys.argv:
        return pf.wipe_cases(boss, NET, "onboardingcheck")

    hr = pf.Client(HR_EMAIL, pf.TEST_PASS)
    it = pf.Client(IT_EMAIL, pf.TEST_PASS)
    maj = pf.Client(MAJ_EMAIL, pf.TEST_PASS)
    nic = pf.Client(NIC_EMAIL, pf.TEST_PASS)

    print("=== 1. karta v bocnom menu ===")
    for nazov, cl, ocakavane in [("hr", hr, True), ("it", it, True),
                                 ("majetok", maj, True), ("bez roly", nic, False)]:
        paths = pf.uri_paths(cl)
        pf.check(f"{nazov} {'vidi' if ocakavane else 'nevidi'} kartu '{CARD}'",
                 (CARD in paths) == ocakavane, paths)
        if not ocakavane:
            # Bez tejto kontroly by test presiel aj vtedy, keby ucet nevidel
            # ziadnu kartu - a nedokazoval by nic.
            pf.check("bez roly pritom ine karty vidi", len(paths) > 0, paths)

    print("\n=== 2. zobrazenia a stlpce ===")
    items = pf.menu_items(boss, prefix="on_")
    for want in POHLADY:
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
    pf.check(f"bootstrap case menu hlasi {len(POHLADY)}/{len(POHLADY)}",
             any(f"{len(POHLADY)}/{len(POHLADY)}" in t for t in mt), mt)

    print("\n=== 3. podanie ===")
    net = pf.newest_net(hr, NET)
    print(f"  siet {net['identifier']} v{net['version']}")
    case_id, _ = pf.new_case(hr, net["stringId"])

    # Prehlad zadavatela je tu uz PRED podanim: visi na read arcu z `p_alive`,
    # ktore nikto nekonzumuje (B25). Bez neho by zadavatel po podani nemal
    # ziadnu ulohu, a teda ani kde precitat, v akom stave jeho pripad je.
    t = pf.tasks_of(hr, case_id)
    pf.check("hned po zalozeni su podanie AJ prehlad",
             sorted(t) == ["t_on_podanie", "t_on_prehlad"], sorted(t))
    podanie = t.get("t_on_podanie")
    if not podanie:
        return pf.report("onboardingcheck")

    meno = f"Test Nastupujuci {int(time.time())}"
    zaklad = {
        "on_meno": {"type": "text", "value": meno},
        "on_pozicia": {"type": "text", "value": "Analytik"},
        "on_oddelenie": {"type": "enumeration_map", "value": "it"},
        "on_datum_nastupu": {"type": "date", "value": "2026-10-01"},
    }

    # Nadriadeny BEZ roly musi byt odmietnuty. `roleRef` a `userRef` sa na
    # prechode zjednocuju, takze smerovanie na konkretnu osobu je cez `userRef`
    # a rolu drzi tento guard - keby vypadol, potvrdit by mohol ktokolvek,
    # koho HR do pola napise, a nikto by si toho nevsimol.
    pf.set_data(hr, podanie, dict(zaklad, **{
        "on_nadriadeny": {"type": "userList", "value": [user_id(boss, NIC_EMAIL)]}}))
    st, r = pf.finish(hr, podanie)
    pf.check("nadriadeny bez roly je odmietnuty", pf.err_body(r), str(r)[:140])

    # Odmietnute DOKONCIT nesmie zmazat read-only prehlad (B8b) - preto visi
    # z `p_alive`, a nie z miesta, ktore nejaky prechod konzumuje.
    pf.check("prehlad odmietnute DOKONCIT prezil",
             "t_on_prehlad" in pf.tasks_of(hr, case_id), sorted(pf.tasks_of(hr, case_id)))

    pf.set_data(hr, podanie, {
        "on_nadriadeny": {"type": "userList", "value": [user_id(boss, IT_EMAIL)]}})
    st, r = pf.finish(hr, podanie)
    pf.check("podanie preslo", pf.ok_body(r), str(r)[:140])

    print("\n=== 4. tri vetvy bezia naraz, kazda pre svoju rolu ===")
    raw = pf.tasks_raw(boss, case_id)
    pf.check("po podani existuju vsetky tri vetvy sucasne",
             {"t_on_it", "t_on_hr", "t_on_majetok"} <= set(raw), sorted(raw))
    pf.check("IT vidi svoju vetvu a prehlad, nie cudzie",
             sorted(pf.tasks_of(it, case_id)) == ["t_on_it", "t_on_prehlad"],
             sorted(pf.tasks_of(it, case_id)))
    pf.check("majetok vidi svoju vetvu a prehlad, nie cudzie",
             sorted(pf.tasks_of(maj, case_id)) == ["t_on_majetok", "t_on_prehlad"],
             sorted(pf.tasks_of(maj, case_id)))
    pf.check("HR vidi svoju vetvu a prehlad, nie cudzie",
             sorted(pf.tasks_of(hr, case_id)) == ["t_on_hr", "t_on_prehlad"],
             sorted(pf.tasks_of(hr, case_id)))

    def prehlad(cl=hr):
        tid = pf.tasks_of(cl, case_id).get("t_on_prehlad")
        return pf.values(cl, tid) if tid else {}

    v = prehlad()
    pf.check("zadavatel vidi stav 'prebieha'", v.get("on_stav_label") == "prebieha",
             v.get("on_stav_label"))
    # Toto je odpoved na "na ktoru vetvu sa caka". Tri `enumeration_map` polia,
    # nie jeden `text`: text je String, ktory sa neprekladá.
    pf.check("zadavatel vidi, ze sa caka na vsetky tri vetvy",
             [v.get("on_it_stav"), v.get("on_hr_stav"), v.get("on_maj_stav")]
             == ["caka", "caka", "caka"],
             [v.get("on_it_stav"), v.get("on_hr_stav"), v.get("on_maj_stav")])

    print("\n=== 5. AND-join: den nastupu neexistuje, kym nie su hotove vsetky tri ===")

    def den_existuje():
        return "t_on_den_nastupu" in pf.tasks_raw(boss, case_id)

    # -- IT
    t_it = pf.tasks_of(it, case_id)["t_on_it"]
    pf.assign(it, t_it)
    pf.set_data(it, t_it, {"on_it_ucet": {"type": "boolean", "value": True},
                           "on_it_notebook": {"type": "boolean", "value": False},
                           "on_it_email": {"type": "text", "value": "test@firma.sk"}})
    st, r = pf.finish(it, t_it)
    # `required` na `boolean` prejde aj s `false` - preto guard vo `finish`.
    pf.check("IT bez notebooku je odmietnute", pf.err_body(r), str(r)[:140])
    pf.set_data(it, t_it, {"on_it_notebook": {"type": "boolean", "value": True}})
    pf.check("IT vetva dokoncena", pf.ok_body(pf.finish(it, t_it)[1]))
    pf.check("po 1/3 vetvach den nastupu NEEXISTUJE", not den_existuje(),
             sorted(pf.tasks_raw(boss, case_id)))

    # -- HR
    t_hr = pf.tasks_of(hr, case_id)["t_on_hr"]
    pf.assign(hr, t_hr)
    pf.set_data(hr, t_hr, {"on_hr_zmluva": {"type": "boolean", "value": True},
                           "on_hr_gdpr": {"type": "boolean", "value": True},
                           "on_hr_bozp": {"type": "boolean", "value": True}})
    pf.check("HR vetva dokoncena", pf.ok_body(pf.finish(hr, t_hr)[1]))
    pf.check("po 2/3 vetvach den nastupu NEEXISTUJE", not den_existuje(),
             sorted(pf.tasks_raw(boss, case_id)))
    v = prehlad()
    pf.check("zadavatel vidi, ze sa caka uz len na majetok",
             [v.get("on_it_stav"), v.get("on_hr_stav"), v.get("on_maj_stav")]
             == ["hotovo", "hotovo", "caka"],
             [v.get("on_it_stav"), v.get("on_hr_stav"), v.get("on_maj_stav")])
    pf.check("stav je stale 'prebieha'", v.get("on_stav_label") == "prebieha",
             v.get("on_stav_label"))

    # -- Majetok
    t_maj = pf.tasks_of(maj, case_id)["t_on_majetok"]
    pf.assign(maj, t_maj)
    pf.set_data(maj, t_maj, {"on_maj_zariadenie": {"type": "text", "value": "Dell Latitude"},
                             "on_maj_inv": {"type": "text", "value": "INV-1"}})
    pf.check("majetkova vetva dokoncena", pf.ok_body(pf.finish(maj, t_maj)[1]))
    pf.check("az po 3/3 vetvach den nastupu EXISTUJE", den_existuje(),
             sorted(pf.tasks_raw(boss, case_id)))
    v = prehlad()
    pf.check("stav je 'pripravene'", v.get("on_stav_label") == "pripravene",
             v.get("on_stav_label"))

    print("\n=== 6. potvrdzuje nadriadeny, nie ktokolvek ===")
    den = pf.tasks_raw(boss, case_id)["t_on_den_nastupu"]
    pf.check("cudzia rola si den nastupu nepriradi", pf.assign(maj, den)[0] == 403,
             pf.assign(maj, den)[0])
    pf.check("zadavatel den nastupu ani nevidi",
             "t_on_den_nastupu" not in pf.tasks_of(hr, case_id),
             sorted(pf.tasks_of(hr, case_id)))
    pf.check("nadriadeny si den nastupu priradi", pf.assign(it, den)[0] == 200)
    st, r = pf.finish(it, den)
    pf.check("nepotvrdeny nastup je odmietnuty", pf.err_body(r), str(r)[:140])
    pf.set_data(it, den, {"on_potvrdene": {"type": "boolean", "value": True}})
    pf.check("nastup potvrdeny", pf.ok_body(pf.finish(it, den)[1]))

    print("\n=== 7. vysledok ===")
    pf.check("na konci zostava uz len prehlad",
             sorted(pf.tasks_raw(boss, case_id)) == ["t_on_prehlad"],
             sorted(pf.tasks_raw(boss, case_id)))
    v = prehlad()
    pf.check("stav je 'nastupil'", v.get("on_stav_label") == "nastupil",
             v.get("on_stav_label"))
    pf.check("je zapisane, kto potvrdil", bool(v.get("on_potvrdil")), v.get("on_potvrdil"))
    pf.check("priebeh nesie vsetky styri kroky",
             len([r for r in (v.get("on_priebeh") or "").split("\n") if r.strip()]) >= 5,
             v.get("on_priebeh"))
    st, c = hr.get(f"/api/workflow/case/{case_id}")
    pf.check("nazov pripadu nesie meno, nie stav", meno in (c["title"] or ""), c["title"])
    pf.check("farba pripadu je zelena", c.get("color") == "green", c.get("color"))

    print("\n=== 8. stav sa preklada, a zobrazenie filtruje podla KLUCA ===")
    # `text` by v anglickom portali zostal slovensky - preto je stav
    # `enumeration_map` a akcia zapisuje kluc.
    en = pf.Client(HR_EMAIL, pf.TEST_PASS, lang="en")
    tid = pf.tasks_of(en, case_id).get("t_on_prehlad")
    opts = pf.options(en, tid, "on_stav_label") if tid else {}
    pf.check("stav ma anglicky preklad", opts.get("nastupil") == "Onboarded", opts)

    q = f'processIdentifier:"{NET}" AND dataSet.on_stav_label.keyValue:"nastupil"'
    st, r = hr.post("/api/workflow/case/search?size=100", {"query": q})
    ids = [x["stringId"] for x in (r.get("_embedded") or {}).get("cases", [])] \
        if isinstance(r, dict) else []
    pf.check("zobrazenie 'Nastúpili' pripad najde", case_id in ids, f"{len(ids)} pripadov")

    q2 = f'processIdentifier:"{NET}" AND dataSet.on_stav_label.keyValue:"prebieha"'
    st, r = hr.post("/api/workflow/case/search?size=100", {"query": q2})
    ids2 = [x["stringId"] for x in (r.get("_embedded") or {}).get("cases", [])] \
        if isinstance(r, dict) else []
    pf.check("v 'Prebieha príprava' uz nie je", case_id not in ids2, f"{len(ids2)} pripadov")

    return pf.report("onboardingcheck")


if __name__ == "__main__":
    sys.exit(main())
