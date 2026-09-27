#!/usr/bin/env python3
"""
fakcheck - akceptacny test nastrelu z dokumentu kolegov (BRIEF.md).

Overuje len to, co nastrel pridal k faktúram. Zvysok appky overuje sccheck.py,
ktoreho pomocne funkcie sa tu pouzivaju, aby sa klient a kontroly nepisali
dvakrat.

  1. faktura ide po zapise NAJPRV referentovi, zadavatel ani stredisko ju nemaju
  2. vstupne kontroly vypisu, co nesedi, a fakturu nezastavia
  3. referent bez dodania neskonci, vratenie bez dovodu neprejde
  4. vratenie na PREDOSLE urovne: stredisko -> referent, riaditel -> stredisko,
     uctovnik -> referent; stredisko nemoze "vratit stredisku"
  5. pravidlo "schvalenie netreba": faktura kryta schvalenou objednavkou,
     dodana kompletne, nie drahsia nez objednavka, ide rovno na zauctovanie
  6. po zauctovani je pripravene XML pre uctovnictvo

Predpoklad: bezi stack a role su pridelene (seed.json, pfseed): druhy@test.local
je zadavatel, super referent aj riaditel, admin@test.local schvaluje wellness
a operator@test.local uctovnik.

    python3 tools/fakcheck.py
"""
import sys

import sccheck as sc
from sccheck import (Client, assign, check, fields, finish, newest_net, new_case,
                     ok_body, err_body, set_data, stav_of, tasks_of, tasks_raw,
                     FAKTURA, OBJEDNAVKA, SUPER_PASS, TEST_PASS)


def podaj_fakturu(cl, net_id, suma, cislo, stredisko="wellness"):
    cid, _ = new_case(cl, net_id)
    t = tasks_of(cl, cid)["t_fa_zapis"]
    set_data(cl, t, {
        "fa_dodavatel": {"type": "text", "value": "Textil Hotel s.r.o."},
        "fa_cislo": {"type": "text", "value": cislo},
        "fa_suma": {"type": "number", "value": suma},
        "fa_datum_vystavenia": {"type": "date", "value": "2026-09-20"},
        "fa_datum_splatnosti": {"type": "date", "value": "2026-10-20"},
        "fa_stredisko": {"type": "enumeration_map", "value": stredisko},
        "fa_predmet": {"type": "text", "value": "Nastrel: kontrola referentom."}})
    st, r = finish(cl, t)
    return cid, r


def kontrola(ref, cid, volba, dodanie=None, poznamka=None, objednavka=None):
    tid = tasks_raw(ref, cid)["t_fa_kontrola"]
    assign(ref, tid)
    if objednavka:
        set_data(ref, tid, {"fa_objednavka_vyber": {"type": "enumeration_map", "value": objednavka}})
    vals = {"fa_kontrola_volba": {"type": "enumeration_map", "value": volba}}
    if dodanie:
        vals["fa_dodanie"] = {"type": "enumeration_map", "value": dodanie}
    if poznamka is not None:
        vals["fa_poznamka"] = {"type": "text", "value": poznamka}
    set_data(ref, tid, vals)
    return tid, finish(ref, tid)


def rozhodni(cl, cid, transition, pole, volba, poznamka=None):
    tid = tasks_raw(cl, cid)[transition]
    assign(cl, tid)
    vals = {pole: {"type": "enumeration_map", "value": volba}}
    if poznamka is not None:
        vals["fa_poznamka"] = {"type": "text", "value": poznamka}
    set_data(cl, tid, vals)
    return finish(cl, tid)


RIADITEL = None


def schvalena_objednavka(zad, sch, suma_ks):
    """Objednavka prejde celym tokom az do 'objednana' - az na taku sa da
    fakturovat. Tok je ten isty ako v sccheck, kroku 12."""
    net_ob = newest_net(zad, OBJEDNAVKA)
    ob, _ = new_case(zad, net_ob["stringId"])
    z = tasks_of(zad, ob)["t_ob_ziadost"]
    set_data(zad, z, {
        "ob_predmet": {"type": "text", "value": "Nastrel: uteráky"},
        "ob_dodavatel": {"type": "text", "value": "Textil Hotel s.r.o."},
        "ob_termin": {"type": "date", "value": "2026-10-31"},
        "ob_stredisko": {"type": "enumeration_map", "value": "wellness"},
        "ob_zdovodnenie": {"type": "text", "value": "Test pravidla bez schválenia."}})
    set_data(zad, z, {
        "ob_p_nazov": {"type": "text", "value": "Uteráky"},
        "ob_p_mnozstvo": {"type": "number", "value": 100},
        "ob_p_jednotka": {"type": "text", "value": "ks"},
        "ob_p_cena": {"type": "number", "value": suma_ks}})
    set_data(zad, z, {"btn_ob_pridat": {"type": "button", "value": 0}})
    finish(zad, z)
    s = tasks_raw(sch, ob)["t_ob_schvalenie"]
    assign(sch, s)
    set_data(sch, s, {"ob_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
    finish(sch, s)
    # Nad limitom riaditela ide objednavka aj jemu. Limit je konfiguracia
    # (sc_nastavenia) a iny test ho moze mat prave zmeneny - test na nom
    # nesmie zavisiet.
    r = tasks_raw(RIADITEL, ob).get("t_ob_riaditel")
    if r:
        assign(RIADITEL, r)
        set_data(RIADITEL, r, {"ob_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
        finish(RIADITEL, r)
    o = tasks_raw(zad, ob)["t_ob_objednanie"]
    assign(zad, o)
    set_data(zad, o, {"ob_cislo": {"type": "text", "value": "OBJ-NASTREL-1"}})
    finish(zad, o)
    return ob, stav_of(zad, ob, "ob_stav_label")


def main():
    zad = Client("druhy@test.local", TEST_PASS)       # zadavatel
    ref = Client("super@netgrif.com", SUPER_PASS)     # referent (aj riaditel)
    sch = Client("admin@test.local", TEST_PASS)       # schv_wellness
    riad = Client("super@netgrif.com", SUPER_PASS)    # riaditel
    global RIADITEL
    RIADITEL = riad
    uct = Client("operator@test.local", TEST_PASS)    # uctovnik
    net_fa = newest_net(zad, FAKTURA)["stringId"]

    print("=== 1. po zapise ide faktura referentovi ===")
    fa, r = podaj_fakturu(zad, net_fa, 240.0, "N-001")
    check("faktura podana", ok_body(r), str(r)[:140])
    check("stav je 'na_kontrolu'", stav_of(zad, fa, "fa_stav_label") == "na_kontrolu",
          stav_of(zad, fa, "fa_stav_label"))
    check("schvalovatel ju este nema", "t_fa_schvalenie" not in tasks_raw(sch, fa),
          sorted(tasks_raw(sch, fa)))
    check("referent ma ulohu na kontrolu", "t_fa_kontrola" in tasks_raw(ref, fa),
          sorted(tasks_raw(ref, fa)))

    print("\n=== 2. vstupne kontroly ===")
    tid = tasks_raw(ref, fa)["t_fa_kontrola"]
    assign(ref, tid)
    d = fields(ref, tid)
    v = d.get("fa_validacia") or ""
    check("hlasi chybajucu prilohu", "príloha" in v, v)
    check("hlasi chybajuce ICO", "IČO" in v, v)
    check("hlasi chybajucu objednavku", "objednávkou" in v, v)
    check("kanal je 'gui'", d.get("fa_kanal") == "gui", d.get("fa_kanal"))

    print("\n=== 3. referent: povinne veci ===")
    set_data(ref, tid, {"fa_kontrola_volba": {"type": "enumeration_map", "value": "pokracovat"}})
    st, r = finish(ref, tid)
    check("bez dodania kontrola neskonci", err_body(r), str(r)[:140])
    set_data(ref, tid, {"fa_kontrola_volba": {"type": "enumeration_map", "value": "vratit"},
                        "fa_poznamka": {"type": "text", "value": ""}})
    st, r = finish(ref, tid)
    check("vratenie bez dovodu neprejde", err_body(r), str(r)[:140])
    set_data(ref, tid, {"fa_poznamka": {"type": "text", "value": "Doplňte IČO."}})
    st, r = finish(ref, tid)
    check("vratenie zadavatelovi preslo", ok_body(r), str(r)[:140])
    check("stav je 'vratena'", stav_of(zad, fa, "fa_stav_label") == "vratena",
          stav_of(zad, fa, "fa_stav_label"))
    t = tasks_of(zad, fa)["t_fa_zapis"]
    set_data(zad, t, {"fa_ico": {"type": "text", "value": "12345678"}})
    st, r = finish(zad, t)
    check("zadavatel doplnil a podal znova", ok_body(r), str(r)[:140])
    _, (st, r) = kontrola(ref, fa, "pokracovat", dodanie="ciastocne")
    check("referent poslal na schvalenie", ok_body(r), str(r)[:140])
    check("stav je 'na_schvalenie'", stav_of(zad, fa, "fa_stav_label") == "na_schvalenie",
          stav_of(zad, fa, "fa_stav_label"))

    print("\n=== 4. vratenie na predosle urovne ===")
    st, r = rozhodni(sch, fa, "t_fa_schvalenie", "fa_rozhodnutie", "vratit_stredisko", "x")
    check("stredisko nemoze 'vratit stredisku'", err_body(r), str(r)[:140])
    st, r = rozhodni(sch, fa, "t_fa_schvalenie", "fa_rozhodnutie", "vratit_kontrola",
                     "Spárujte s objednávkou.")
    check("stredisko vratilo referentovi", ok_body(r), str(r)[:140])
    check("stav je znova 'na_kontrolu'", stav_of(zad, fa, "fa_stav_label") == "na_kontrolu",
          stav_of(zad, fa, "fa_stav_label"))
    kontrola(ref, fa, "pokracovat", dodanie="ciastocne")
    st, r = rozhodni(sch, fa, "t_fa_schvalenie", "fa_rozhodnutie", "schvalit")
    check("stredisko schvalilo", ok_body(r), str(r)[:140])
    check("do limitu ide na zauctovanie", stav_of(zad, fa, "fa_stav_label") == "na_zauctovanie",
          stav_of(zad, fa, "fa_stav_label"))
    st, r = rozhodni(uct, fa, "t_fa_zauctovanie", "fa_uctovanie", "vratit_kontrola",
                     "Nesedí IBAN.")
    check("uctovnik vratil referentovi", ok_body(r), str(r)[:140])
    check("stav je 'na_kontrolu'", stav_of(zad, fa, "fa_stav_label") == "na_kontrolu",
          stav_of(zad, fa, "fa_stav_label"))

    fa2, r = podaj_fakturu(zad, net_fa, 2500.0, "N-002")
    kontrola(ref, fa2, "pokracovat", dodanie="ciastocne")
    rozhodni(sch, fa2, "t_fa_schvalenie", "fa_rozhodnutie", "schvalit")
    check("nad limit ide riaditelovi", stav_of(zad, fa2, "fa_stav_label") == "u_riaditela",
          stav_of(zad, fa2, "fa_stav_label"))
    st, r = rozhodni(riad, fa2, "t_fa_riaditel", "fa_rozhodnutie", "vratit_stredisko",
                     "Prečo tak drahé?")
    check("riaditel vratil stredisku", ok_body(r), str(r)[:140])
    check("stav je 'na_schvalenie'", stav_of(zad, fa2, "fa_stav_label") == "na_schvalenie",
          stav_of(zad, fa2, "fa_stav_label"))
    check("a schvalovatel strediska ju zase ma", "t_fa_schvalenie" in tasks_raw(sch, fa2),
          sorted(tasks_raw(sch, fa2)))

    print("\n=== 5. pravidlo: schvalenie netreba ===")
    ob, ob_stav = schvalena_objednavka(zad, sch, 7.0)       # 100 ks x 7 = 700 EUR
    check("objednavka je objednana", ob_stav == "objednana", ob_stav)
    fa3, r = podaj_fakturu(zad, net_fa, 700.0, "N-003")
    _, (st, r) = kontrola(ref, fa3, "pokracovat", dodanie="kompletne", objednavka=ob)
    check("kontrola so sparovanim presla", ok_body(r), str(r)[:140])
    check("kryta, kompletna, nie drahsia -> rovno na zauctovanie",
          stav_of(zad, fa3, "fa_stav_label") == "na_zauctovanie",
          stav_of(zad, fa3, "fa_stav_label"))
    fa4, r = podaj_fakturu(zad, net_fa, 700.0, "N-004")
    kontrola(ref, fa4, "pokracovat", dodanie="ciastocne", objednavka=ob)
    check("ciastocne dodanie ide na schvalenie",
          stav_of(zad, fa4, "fa_stav_label") == "na_schvalenie",
          stav_of(zad, fa4, "fa_stav_label"))
    fa5, r = podaj_fakturu(zad, net_fa, 750.0, "N-005")
    kontrola(ref, fa5, "pokracovat", dodanie="kompletne", objednavka=ob)
    check("drahsia nez objednavka ide na schvalenie",
          stav_of(zad, fa5, "fa_stav_label") == "na_schvalenie",
          stav_of(zad, fa5, "fa_stav_label"))

    print("\n=== 6. zauctovanie pripravi XML ===")
    tz = tasks_raw(uct, fa3)["t_fa_zauctovanie"]
    assign(uct, tz)
    set_data(uct, tz, {"fa_uctovanie": {"type": "enumeration_map", "value": "zauctovat"},
                       "fa_doklad": {"type": "text", "value": "DOK-777"}})
    st, r = finish(uct, tz)
    check("zauctovane", ok_body(r), str(r)[:140])
    tp = tasks_raw(zad, fa3)["t_fa_prehlad"]
    d = fields(zad, tp)
    x = d.get("fa_export_xml") or ""
    check("XML je pripravene", x.startswith("<?xml") and "<faktura>" in x, x[:80])
    check("XML nesie doklad aj objednavku", "DOK-777" in x and "OBJ-NASTREL-1" in x, x[:300])
    check("priebeh priznava, ze integracia chyba",
          "čakajú na integráciu" in (d.get("fa_historia") or ""),
          (d.get("fa_historia") or "")[-160:])

    print(f"\nfakcheck: {len(sc.OK)} preslo, {len(sc.FAIL)} zlyhalo")
    for f in sc.FAIL:
        print("  ZLYHALO:", f)
    return 1 if sc.FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
