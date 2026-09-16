#!/usr/bin/env python3
"""
demo_ob_fa - naplni lokalny engine ukazkovymi objednavkami a fakturami
(appka "Schvalovanie faktur a objednavok"), aby appka na demo nebola prazdna.

Toto NIE JE akceptacny test - ten je `tools/sccheck.py` a nic tu neoveruje.
Skript len zaklada realisticky vyzerajuci mix stavov cez normalne API prechody
(rovnaky vzor ako `sccheck.py`), aby zoznamy v drawer menu ukazovali vsetko, co
appka vie: rozpisane, cakajuce na stredisko, cakajuce na riaditela nad limitom,
kompletne spracovane (zauctovane / objednane) aj zamietnute.

Predpoklad: bezi stack (tools/up.sh) a role su pridelene (tools/pfseed.py).

    python3 tools/demo_ob_fa.py
    python3 tools/demo_ob_fa.py --wipe   # zmaze VSETKY objednavky a faktury
"""

import sys

import pftestlib as pf

# Windows konzola je cp1252 - diakritika v printoch by inak zhodila skript
# uprostred behu (`UnicodeEncodeError`), ked uz par prípadov existuje.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

FAKTURA = "financie/faktury/fa_faktura"
OBJEDNAVKA = "financie/objednavky/ob_objednavka"

# `druhy@test.local` je len zadavatel (ziadne schvalovacie roly) - kazda demo
# objednavka/faktura tak ide cez smerovanie ako u realneho radoveho ziadatela.
#
# Schvalovatel je `super@netgrif.com`, nie `admin@test.local`: strediska
# "sprava"/"udrzba"/"marketing" maju svojho `schv_*` len na superovi
# (`admin` ma iba schv_wellness/schv_restauracia), takze admin by na tychto
# pripadoch ulohu na schvalenie vobec nedostal - kandidatov najde uz prvy
# kandidat (schv_<stredisko>) a na vseobecnu rolu `schvalovatel` sa nikdy
# nedostane. Super ma vsetky schv_* aj riaditel aj uctovnik naraz, takze
# jeden klient vie prejst cely schvalovaci retazec pre kazde stredisko.
REQUESTER_EMAIL = "druhy@test.local"
APPROVER_EMAIL = "super@netgrif.com"


def new_invoice(zad, net, dodavatel, cislo, suma, splatnost, stredisko, predmet):
    case_id, _ = pf.new_case(zad, net["stringId"])
    t = pf.tasks_of(zad, case_id)["t_fa_zapis"]
    pf.set_data(zad, t, {
        "fa_dodavatel": {"type": "text", "value": dodavatel},
        "fa_cislo": {"type": "text", "value": cislo},
        "fa_suma": {"type": "number", "value": suma},
        "fa_datum_splatnosti": {"type": "date", "value": splatnost},
        "fa_stredisko": {"type": "enumeration_map", "value": stredisko},
        "fa_predmet": {"type": "text", "value": predmet}})
    st, r = pf.finish(zad, t)
    if pf.err_body(r):
        print(f"  ! faktura {cislo} sa nepodala: {str(r)[:160]}")
    else:
        print(f"  faktura {cislo} ({dodavatel}, {suma} EUR) podana")
    return case_id


def advance_invoice(sch, case_id, decision="schvalit", complete=False, doklad=None, dovod=None):
    """`decision`: schvalit / vratit / zamietnut na urovni strediska. `dovod` je
    POVINNY pri vsetkom okrem "schvalit" - bez neho `finish` odmietne (200 +
    `error` v tele, ziadny vynimocny stavovy kod) a stav zostane bez zmeny.
    `complete=True` dotiahne schvalenu fakturu az po zauctovanie (cez riaditela,
    ak je nad limitom)."""
    t = pf.tasks_of(sch, case_id)
    if "t_fa_schvalenie" not in t:
        print(f"  ! {case_id}: schvalovatel na nej nema ulohu (zle stredisko?)")
        return
    data = {"fa_rozhodnutie": {"type": "enumeration_map", "value": decision}}
    if decision != "schvalit":
        data["fa_poznamka"] = {"type": "text", "value": dovod or "Bez uvedenia dôvodu."}
    pf.set_data(sch, t["t_fa_schvalenie"], data)
    st, r = pf.finish(sch, t["t_fa_schvalenie"])
    if pf.err_body(r):
        print(f"  ! {case_id}: schválenie strediska zlyhalo: {str(r)[:160]}")
        return
    if decision != "schvalit" or not complete:
        return
    t = pf.tasks_of(sch, case_id)
    if "t_fa_riaditel" in t:
        pf.set_data(sch, t["t_fa_riaditel"], {"fa_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
        st, r = pf.finish(sch, t["t_fa_riaditel"])
        if pf.err_body(r):
            print(f"  ! {case_id}: schválenie riaditeľom zlyhalo: {str(r)[:160]}")
            return
    t = pf.tasks_of(sch, case_id)
    if "t_fa_zauctovanie" in t:
        pf.set_data(sch, t["t_fa_zauctovanie"], {
            "fa_uctovanie": {"type": "enumeration_map", "value": "zauctovat"},
            "fa_doklad": {"type": "text", "value": doklad or "DF-DEMO"}})
        st, r = pf.finish(sch, t["t_fa_zauctovanie"])
        if pf.err_body(r):
            print(f"  ! {case_id}: zaúčtovanie zlyhalo: {str(r)[:160]}")


def new_order(zad, net, predmet, dodavatel, termin, stredisko, zdovodnenie, items):
    case_id, _ = pf.new_case(zad, net["stringId"])
    t = pf.tasks_of(zad, case_id)["t_ob_ziadost"]
    pf.set_data(zad, t, {
        "ob_predmet": {"type": "text", "value": predmet},
        "ob_dodavatel": {"type": "text", "value": dodavatel},
        "ob_termin": {"type": "date", "value": termin},
        "ob_stredisko": {"type": "enumeration_map", "value": stredisko},
        "ob_zdovodnenie": {"type": "text", "value": zdovodnenie}})
    for nazov, mnozstvo, jednotka, cena in items:
        pf.set_data(zad, t, {
            "ob_p_nazov": {"type": "text", "value": nazov},
            "ob_p_mnozstvo": {"type": "number", "value": mnozstvo},
            "ob_p_jednotka": {"type": "text", "value": jednotka},
            "ob_p_cena": {"type": "number", "value": cena}})
        pf.set_data(zad, t, {"btn_ob_pridat": {"type": "button", "value": 0}})
    st, r = pf.finish(zad, t)
    if pf.err_body(r):
        print(f"  ! objednavka '{predmet}' sa nepodala: {str(r)[:160]}")
    else:
        print(f"  objednavka '{predmet}' ({dodavatel}) podana")
    return case_id


def advance_order(sch, requester, case_id, decision="schvalit", complete=False, cislo=None, dovod=None):
    """Rovnaka pasca ako pri fakture: `ob_poznamka` je POVINNA pri vsetkom okrem
    "schvalit", inak `finish` ticho odmietne a stav sa nezmeni."""
    t = pf.tasks_of(sch, case_id)
    if "t_ob_schvalenie" not in t:
        print(f"  ! {case_id}: schvalovatel na nej nema ulohu (zle stredisko?)")
        return
    data = {"ob_rozhodnutie": {"type": "enumeration_map", "value": decision}}
    if decision != "schvalit":
        data["ob_poznamka"] = {"type": "text", "value": dovod or "Bez uvedenia dôvodu."}
    pf.set_data(sch, t["t_ob_schvalenie"], data)
    st, r = pf.finish(sch, t["t_ob_schvalenie"])
    if pf.err_body(r):
        print(f"  ! {case_id}: schválenie strediska zlyhalo: {str(r)[:160]}")
        return
    if decision != "schvalit":
        return
    t = pf.tasks_of(sch, case_id)
    if "t_ob_riaditel" in t:
        pf.set_data(sch, t["t_ob_riaditel"], {"ob_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
        st, r = pf.finish(sch, t["t_ob_riaditel"])
        if pf.err_body(r):
            print(f"  ! {case_id}: schválenie riaditeľom zlyhalo: {str(r)[:160]}")
            return
    if not complete:
        return
    # Potvrdenie objednania robi ten, kto o objednavku poziadal - nie schvalovatel.
    t = pf.tasks_of(requester, case_id)
    if "t_ob_objednanie" in t:
        pf.set_data(requester, t["t_ob_objednanie"], {"ob_cislo": {"type": "text", "value": cislo or "OBJ-DEMO"}})
        st, r = pf.finish(requester, t["t_ob_objednanie"])
        if pf.err_body(r):
            print(f"  ! {case_id}: potvrdenie objednania zlyhalo: {str(r)[:160]}")


def main():
    boss = pf.Client("super@netgrif.com", pf.SUPER_PASS)
    if "--wipe" in sys.argv:
        pf.wipe_cases(boss, FAKTURA, "demo_ob_fa faktury")
        pf.wipe_cases(boss, OBJEDNAVKA, "demo_ob_fa objednavky")
        return 0

    zad = pf.Client(REQUESTER_EMAIL, pf.TEST_PASS)
    # `boss` uz JE prihlaseny ako `APPROVER_EMAIL` (super@netgrif.com), a jeho
    # heslo je `SUPER_PASS`, nie `TEST_PASS` - druhy klient by sa neprihlasil.
    sch = boss

    net_fa = pf.newest_net(boss, FAKTURA)
    net_ob = pf.newest_net(boss, OBJEDNAVKA)

    print("=== Faktúry ===")
    f1 = new_invoice(zad, net_fa, "Gastro Trade s.r.o.", "2026041", 240.50,
                      "2026-10-15", "restauracia", "Dodávka mäsa a mliečnych výrobkov, október.")

    f2 = new_invoice(zad, net_fa, "Wellness Technik a.s.", "2026058", 890.00,
                      "2026-10-20", "wellness", "Servis a chemické ošetrenie bazénovej technológie.")

    f3 = new_invoice(zad, net_fa, "Kancelária Papier s.r.o.", "2026072", 85.30,
                      "2026-10-05", "sprava", "Kancelársky papier a tonery na Q4.")
    advance_invoice(sch, f3, decision="schvalit", complete=True, doklad="DF-2026-00301")

    f4 = new_invoice(zad, net_fa, "Stavebniny Údržba s.r.o.", "2026081", 1450.00,
                      "2026-11-01", "udrzba", "Materiál na opravu strechy wellness krídla.")
    advance_invoice(sch, f4, decision="schvalit", complete=False)  # čaká u riaditeľa (nad limit)

    f5 = new_invoice(zad, net_fa, "Reklamná agentúra Vision", "2026065", 610.00,
                      "2026-10-25", "marketing", "Jesenná kampaň - sociálne siete a tlač letákov.")
    advance_invoice(sch, f5, decision="zamietnut",
                     dovod="Kampaň nebola vopred odsúhlasená marketingovým plánom na Q4.")

    f6 = new_invoice(zad, net_fa, "Hotel Recepcia Servis", "2026090", 320.00,
                      "2026-10-18", "hotel", "Ročná údržba recepčného softvéru a tlačiarne kľúčových kariet.")

    print("\n=== Objednávky ===")
    o1 = new_order(zad, net_ob, "Vybavenie wellness", "Textil Hotel s.r.o.", "2026-10-31",
                    "wellness", "Staré uteráky a plášte sú po troch rokoch nepoužiteľné.",
                    [("Uteráky 70×140", 200, "ks", 3.50), ("Prostěradlá", 100, "ks", 0.80)])

    o2 = new_order(zad, net_ob, "Kancelárske potreby na Q4", "Office Depot SK",
                    "2026-10-10", "sprava", "Bežné doplnenie zásob pre recepciu a administratívu.",
                    [("Kancelársky papier A4", 20, "balenie", 4.20), ("Toner do tlačiarne", 4, "ks", 45.00)])
    advance_order(sch, zad, o2, decision="schvalit", complete=True, cislo="OBJ-2026-142")

    o3 = new_order(zad, net_ob, "Rekonštrukcia bazénového okruhu", "AquaTech Slovakia s.r.o.",
                    "2026-12-01", "udrzba",
                    "Filtračný systém dosluhuje, hrozí odstávka wellness časti v sezóne.",
                    [("Filtračná jednotka", 1, "ks", 2200.00), ("Montáž a zapojenie", 1, "služba", 450.00)])
    advance_order(sch, zad, o3, decision="schvalit", complete=False)  # čaká u riaditeľa (nad limit)

    o4 = new_order(zad, net_ob, "Marketingové materiály - zima 2026", "Print & Design s.r.o.",
                    "2026-11-15", "marketing", "Letáky a rollupy na vianočnú kampaň.",
                    [("Rollup banner", 3, "ks", 89.00), ("Letáky A5 (1000 ks)", 5, "balenie", 35.00)])
    advance_order(sch, zad, o4, decision="zamietnut",
                   dovod="Rozpočet na marketingovú tlač na tento kvartál je už vyčerpaný.")

    o5 = new_order(zad, net_ob, "Reštauračné vybavenie", "Gastro Trade s.r.o.", "2026-10-20",
                    "restauracia", "Doplnenie riadu po letnej sezóne, časť je poškodená.",
                    [("Tanier plytký 27cm", 120, "ks", 4.90), ("Obrus damaškový 140×140", 30, "ks", 12.50)])

    print(f"\nHotovo: 6 faktúr ({f1[:6]}…, {f2[:6]}…, {f3[:6]}…, {f4[:6]}…, {f5[:6]}…, {f6[:6]}…), "
          f"5 objednávok ({o1[:6]}…, {o2[:6]}…, {o3[:6]}…, {o4[:6]}…, {o5[:6]}…)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
