#!/usr/bin/env python3
"""
appsdemo - naplni vetvu `apps` ukazkovymi pouzivatelmi a pripadmi, aby portal
na predvadzanie nebol prazdny.

Toto NIE JE akceptacny test (tie su oncheck, dvcheck, cestycheck, sccheck,
fakcheck). Skript cez normalne API prechody zalozi desat ludi z Netgrifu
a pod ich menami realisticky mix stavov vo vsetkych styroch appkach:
rozpisane, cakajuce na schvalenie, vratene aj hotove.

Heslo demo uctov sa NEZADAVA v kode: berie sa z ETASK_DEMO_PASSWORD.

    ETASK_DEMO_PASSWORD=... python3 tools/appsdemo.py

Je idempotentny len v zakladani uctov (existujuci ucet preskoci); pripady
zaklada pri kazdom behu znova, takze sa spusta raz, na cistej instancii.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pftestlib as pf

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
HESLO = os.environ.get("ETASK_DEMO_PASSWORD", "")

SPRAVCA = ["spravca"]
# meno, priezvisko, e-mail, authority, roly (importId; `rola@vzor` = len v tych sietach)
USERS = [
    ("Ľuboš", "Petrovič", "petrovic@netgrif.com", ["ROLE_USER", "ROLE_ADMIN"],
     ["spravca", "hr", "approver", "it_admin", "zamestnanec", "zadavatel"]),
    ("Gabriel", "Juhás", "juhas@netgrif.com", ["ROLE_USER"],
     ["riaditel", "veduci", "approver", "schvalovatel"]),
    ("Milan", "Mladoniczky", "mladoniczky@netgrif.com", ["ROLE_USER"],
     ["veduci", "approver", "it_admin", "schvalovatel", "schv_hotel", "schv_restauracia",
      "schv_wellness", "schv_udrzba", "schv_marketing", "schv_sprava"]),
    ("Milan", "Šamaj", "samaj@netgrif.com", ["ROLE_USER"],
     ["referent", "zamestnanec", "zadavatel"]),
    ("Martin", "Makáň", "makan@netgrif.com", ["ROLE_USER"],
     ["uctovnik", "mzdy", "zamestnanec"]),
    ("Lucia", "Šamajová", "samajova@netgrif.com", ["ROLE_USER"],
     ["hr", "zamestnanec", "zadavatel"]),
    ("Dominik", "Vozár", "vozar@netgrif.com", ["ROLE_USER"],
     ["it_admin", "zamestnanec", "zadavatel"]),
    ("Jakub", "Kovář", "kovar@netgrif.com", ["ROLE_USER"],
     ["zamestnanec", "zadavatel"]),
    ("Michaela", "Popovičová", "popovicova@netgrif.com", ["ROLE_USER"],
     ["zamestnanec", "zadavatel"]),
    ("Matej", "Chvostek", "chvostek@netgrif.com", ["ROLE_USER"],
     ["zamestnanec"]),
]

FAKTURA = "financie/faktury/fa_faktura"
OBJEDNAVKA = "financie/objednavky/ob_objednavka"


def task_by_transition(cl, transition):
    st, r = cl.post("/api/task/search?size=50", {"transitionId": [transition]})
    tasks = (r.get("_embedded") or {}).get("tasks", []) if isinstance(r, dict) else []
    return tasks[0]["stringId"] if tasks else None


def user_id(cl, email):
    st, r = cl.post("/api/user/search?size=20", {"fulltext": email})
    for u in (r.get("_embedded") or {}).get("users", []) if isinstance(r, dict) else []:
        if (u.get("email") or "").lower() == email.lower():
            return u.get("id") or u.get("stringId")
    return None


def zaloz_ucty(boss):
    print("=== pouzivatelia ===")
    for meno, priezvisko, email, auth, _ in USERS:
        if user_id(boss, email):
            print(f"  {email}: uz existuje")
            continue
        tid = task_by_transition(boss, "t_pu_novy")
        pf.set_data(boss, tid, {
            "zl_meno": {"type": "text", "value": meno},
            "zl_priezvisko": {"type": "text", "value": priezvisko},
            "zl_email": {"type": "text", "value": email},
            # heslo tak, ako ho posiela formular - v base64 (pucheck)
            "zl_heslo": {"type": "text", "value": base64.b64encode(HESLO.encode()).decode()},
            "zl_authority": {"type": "multichoice_map", "value": auth}})
        st, r = pf.finish(boss, tid)
        print(f"  {email}: {'zalozeny' if pf.ok_body(r) else 'CHYBA ' + str(r)[:120]}")


def pridel_roly():
    print("=== roly (pfseed) ===")
    seed = json.loads((ROOT / "seed.json").read_text(encoding="utf-8"))
    demo = {"netScope": seed["netScope"],
            "users": [{"email": u[2], "roles": u[4]} for u in USERS]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(demo, f, ensure_ascii=False)
    env = dict(os.environ, PF_SEED=f.name, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "pfseed.py")], env=env,
                       capture_output=True, text=True, encoding="utf-8")
    print("  " + (r.stdout.strip().splitlines() or ["?"])[-1])
    os.unlink(f.name)


def klient(email):
    return pf.Client(email, HESLO)


# ------------------------------------------------------------------ dovolenky

def dovolenky(veduci):
    print("=== dovolenky ===")
    net = pf.newest_net(veduci, "hr/dovolenky/dv_ziadost")["stringId"]
    plan = [
        # e-mail, od, do, dovod, co s tym veduci
        ("kovar@netgrif.com", "2026-10-12", "2026-10-16", "Jesenné prázdniny s deťmi.", None),
        ("makan@netgrif.com", "2026-11-02", "2026-11-06", "Sťahovanie.", None),
        ("popovicova@netgrif.com", "2026-08-10", "2026-08-21", "Letná dovolenka - Chorvátsko.", "schvalena"),
        ("samaj@netgrif.com", "2026-12-23", "2026-12-31", "Vianoce.", "schvalena"),
        ("chvostek@netgrif.com", "2026-10-26", "2026-10-30", "Dovolenka.", "vratena"),
        ("vozar@netgrif.com", "2026-11-16", "2026-11-20", "", "koncept"),
    ]
    for email, od, do, dovod, rozhodnutie in plan:
        cl = klient(email)
        cid, _ = pf.new_case(cl, net)
        t = pf.tasks_of(cl, cid)["t_dv_podanie"]
        pf.set_data(cl, t, {"dv_od": {"type": "date", "value": od},
                            "dv_do": {"type": "date", "value": do},
                            "dv_dovod": {"type": "text", "value": dovod or "Oddych."}})
        if rozhodnutie == "koncept":
            print(f"  {email}: rozpisana")
            continue
        pf.finish(cl, t)
        if rozhodnutie:
            r = pf.tasks_raw(veduci, cid)["t_dv_rozhodnutie"]
            pf.assign(veduci, r)
            vals = {"dv_rozhodnutie": {"type": "enumeration_map", "value": rozhodnutie}}
            vals["dv_poznamka"] = {"type": "text", "value":
                                   "Schválené." if rozhodnutie == "schvalena"
                                   else "Prosím posuň o týždeň, v tom termíne je release."}
            pf.set_data(veduci, r, vals)
            pf.finish(veduci, r)
        print(f"  {email}: {rozhodnutie or 'caka na schvalenie'}")


# ------------------------------------------------------------------ onboarding

def onboarding(hr, veduci, it):
    print("=== onboarding ===")
    net = pf.newest_net(hr, "onboarding/on_request")["stringId"]
    schv = user_id(hr, "mladoniczky@netgrif.com")
    plan = [
        ("Peter", "Novák", "Backend developer", "Vývoj", "2026-10-15", "caka"),
        ("Zuzana", "Kráľová", "UX designérka", "Produkt", "2026-10-01", "ucty"),
        ("Tomáš", "Baláž", "Obchodník", "Obchod", "2026-09-15", "hotovo"),
    ]
    for meno, priezvisko, pozicia, stredisko, nastup, stav in plan:
        cid, _ = pf.new_case(hr, net)
        t = pf.tasks_of(hr, cid)["t_on_request"]
        pf.set_data(hr, t, {
            "on_first_name": {"type": "text", "value": meno},
            "on_last_name": {"type": "text", "value": priezvisko},
            "on_email": {"type": "text", "value": f"{priezvisko.lower().replace('á', 'a').replace('ľ', 'l')}@netgrif.com"},
            "on_position": {"type": "text", "value": pozicia},
            "on_cost_centre": {"type": "text", "value": stredisko},
            "on_start_date": {"type": "date", "value": nastup},
            "on_approver": {"type": "userList", "value": [schv]}})
        st, r = pf.finish(hr, t)
        if stav != "caka":
            a = pf.tasks_raw(veduci, cid)["t_on_approval"]
            pf.assign(veduci, a)
            pf.set_data(veduci, a, {"on_decision": {"type": "enumeration_map", "value": "approved"}})
            pf.finish(veduci, a)
        if stav == "hotovo":
            u = pf.tasks_raw(it, cid)["t_on_accounts"]
            pf.assign(it, u)
            pf.set_data(it, u, {"on_entra": {"type": "boolean", "value": True},
                                "on_atlassian": {"type": "boolean", "value": True}})
            pf.finish(it, u)
        print(f"  {meno} {priezvisko}: {stav}")


# ------------------------------------------------------------------ pracovne cesty

def cesta(datum, od, hodin, doprava, strava, km=0, cena=0, ubytovanie=0, ine=0,
          zac="Bratislava", kon="Žilina", rokovanie="Stretnutie u klienta"):
    return {
        "pc_c_zaciatok": {"type": "dateTime", "value": f"{datum}T{od}:00"},
        "pc_c_trvanie": {"type": "number", "value": hodin},
        "pc_c_miesto_zac": {"type": "text", "value": zac},
        "pc_c_miesto_kon": {"type": "text", "value": kon},
        "pc_c_rokovanie": {"type": "text", "value": rokovanie},
        "pc_c_doprava": {"type": "enumeration_map", "value": doprava},
        "pc_c_strava": {"type": "enumeration_map", "value": strava},
        "pc_c_km_tam": {"type": "number", "value": km},
        "pc_c_km_spat": {"type": "number", "value": km},
        "pc_c_cena_phm": {"type": "number", "value": cena},
        "pc_c_ubytovanie": {"type": "number", "value": ubytovanie},
        "pc_c_ine": {"type": "number", "value": ine}}


def cesty(veduci, mzdy):
    print("=== pracovne cesty ===")
    net = pf.newest_net(veduci, "hr/cesty/pc_vyuctovanie")["stringId"]
    plan = [
        ("kovar@netgrif.com", "rozpisane", [
            cesta("2026-09-08", "07:00", 11, "auto", "nie", km=200, cena=1.62, zac="Bratislava", kon="Žilina"),
            cesta("2026-09-17", "08:30", 6, "vlak", "nie", ine=18.4, kon="Trnava")]),
        ("popovicova@netgrif.com", "podane", [
            cesta("2026-09-03", "06:00", 14, "auto", "obed", km=320, cena=1.59, kon="Košice"),
            cesta("2026-09-04", "07:00", 10, "auto", "nie", km=0, ubytovanie=79, kon="Košice")]),
        ("chvostek@netgrif.com", "schvalene", [
            cesta("2026-08-26", "09:00", 5.5, "autobus", "nie", ine=9.8, kon="Nitra")]),
    ]
    for email, stav, jazdy in plan:
        cl = klient(email)
        cid, _ = pf.new_case(cl, net)
        t = pf.tasks_of(cl, cid)["t_vyplnit"]
        pf.set_data(cl, t, {"pc_rok": {"type": "number", "value": 2026},
                            "pc_mesiac": {"type": "enumeration_map", "value": "09"},
                            "pc_spotreba": {"type": "number", "value": 6.8},
                            "pc_palivo": {"type": "enumeration_map", "value": "nafta"},
                            "pc_spz": {"type": "text", "value": "BA123XY"}})
        for j in jazdy:
            pf.set_data(cl, t, j)
            pf.set_data(cl, t, {"btn_pc_pridat": {"type": "button", "value": 1}})
        if stav == "rozpisane":
            print(f"  {email}: rozpisane ({len(jazdy)} cesty)")
            continue
        pf.upload(cl, t, "pc_podpis_zam", "podpis.png", pf.tiny_png(120, 40))
        moznosti = pf.options(cl, t, "pc_schvalovatel_vyber")
        juhas = user_id(veduci, "juhas@netgrif.com")
        vyber = juhas if juhas in moznosti else next(iter(moznosti), None)
        pf.set_data(cl, t, {"pc_schvalovatel_vyber": {"type": "enumeration_map", "value": vyber}})
        st, r = pf.finish(cl, t)
        if stav == "schvalene":
            s = pf.tasks_raw(veduci, cid).get("t_schvalit")
            if s:
                pf.assign(veduci, s)
                pf.set_data(veduci, s, {"pc_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
                pf.finish(veduci, s)
        print(f"  {email}: {stav}" + ("" if pf.ok_body(r) else f" (podanie: {str(r)[:100]})"))


# ------------------------------------------------------------------ objednavky a faktury

def objednavka(zad, sch, riad, predmet, dodavatel, stredisko, polozky, cislo=None, stav="objednana"):
    net = pf.newest_net(zad, OBJEDNAVKA)["stringId"]
    ob, _ = pf.new_case(zad, net)
    z = pf.tasks_of(zad, ob)["t_ob_ziadost"]
    pf.set_data(zad, z, {
        "ob_predmet": {"type": "text", "value": predmet},
        "ob_dodavatel": {"type": "text", "value": dodavatel},
        "ob_termin": {"type": "date", "value": "2026-10-31"},
        "ob_stredisko": {"type": "enumeration_map", "value": stredisko},
        "ob_zdovodnenie": {"type": "text", "value": "Plánovaný nákup podľa rozpočtu."}})
    for nazov, ks, jedn, cena in polozky:
        pf.set_data(zad, z, {"ob_p_nazov": {"type": "text", "value": nazov},
                             "ob_p_mnozstvo": {"type": "number", "value": ks},
                             "ob_p_jednotka": {"type": "text", "value": jedn},
                             "ob_p_cena": {"type": "number", "value": cena}})
        pf.set_data(zad, z, {"btn_ob_pridat": {"type": "button", "value": 0}})
    if stav == "koncept":
        return ob
    pf.finish(zad, z)
    if stav == "na_schvalenie":
        return ob
    s = pf.tasks_raw(sch, ob)["t_ob_schvalenie"]
    pf.assign(sch, s)
    pf.set_data(sch, s, {"ob_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
    pf.finish(sch, s)
    r = pf.tasks_raw(riad, ob).get("t_ob_riaditel")
    if r:
        if stav == "u_riaditela":
            return ob
        pf.assign(riad, r)
        pf.set_data(riad, r, {"ob_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
        pf.finish(riad, r)
    if stav == "na_objednanie":
        return ob
    o = pf.tasks_raw(zad, ob)["t_ob_objednanie"]
    pf.assign(zad, o)
    pf.set_data(zad, o, {"ob_cislo": {"type": "text", "value": cislo or "OBJ-2026-100"}})
    pf.finish(zad, o)
    return ob


def faktura(zad, ref, sch, riad, uct, dodavatel, cislo, suma, stredisko, predmet, az_po):
    net = pf.newest_net(zad, FAKTURA)["stringId"]
    fa, _ = pf.new_case(zad, net)
    t = pf.tasks_of(zad, fa)["t_fa_zapis"]
    pf.set_data(zad, t, {
        "fa_dodavatel": {"type": "text", "value": dodavatel},
        "fa_cislo": {"type": "text", "value": cislo},
        "fa_suma": {"type": "number", "value": suma},
        "fa_datum_vystavenia": {"type": "date", "value": "2026-09-15"},
        "fa_datum_splatnosti": {"type": "date", "value": "2026-10-15"},
        "fa_stredisko": {"type": "enumeration_map", "value": stredisko},
        "fa_predmet": {"type": "text", "value": predmet}})
    if az_po == "koncept":
        return
    pf.finish(zad, t)
    if az_po == "kontrola":
        return
    k = pf.tasks_raw(ref, fa)["t_fa_kontrola"]
    pf.assign(ref, k)
    pf.set_data(ref, k, {"fa_kontrola_volba": {"type": "enumeration_map", "value": "pokracovat"},
                         "fa_dodanie": {"type": "enumeration_map", "value": "kompletne"}})
    pf.finish(ref, k)
    if az_po == "schvalenie":
        return
    s = pf.tasks_raw(sch, fa).get("t_fa_schvalenie")
    if s:
        pf.assign(sch, s)
        pf.set_data(sch, s, {"fa_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
        pf.finish(sch, s)
    r = pf.tasks_raw(riad, fa).get("t_fa_riaditel")
    if r:
        if az_po == "riaditel":
            return
        pf.assign(riad, r)
        pf.set_data(riad, r, {"fa_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
        pf.finish(riad, r)
    if az_po == "zauctovanie":
        return
    z = pf.tasks_raw(uct, fa)["t_fa_zauctovanie"]
    pf.assign(uct, z)
    pf.set_data(uct, z, {"fa_uctovanie": {"type": "enumeration_map", "value": "zauctovat"},
                         "fa_doklad": {"type": "text", "value": "DF-" + cislo[-4:]}})
    pf.finish(uct, z)


def financie():
    print("=== objednavky a faktury ===")
    ref, sch, riad, uct = (klient(e) for e in ("samaj@netgrif.com", "mladoniczky@netgrif.com",
                                               "juhas@netgrif.com", "makan@netgrif.com"))
    kovar, vozar, popov = (klient(e) for e in ("kovar@netgrif.com", "vozar@netgrif.com",
                                               "popovicova@netgrif.com"))
    objednavka(vozar, sch, riad, "Notebooky pre nových kolegov", "Datacomp s.r.o.", "sprava",
               [("Notebook 14\"", 2, "ks", 1290)], stav="u_riaditela")
    objednavka(kovar, sch, riad, "Uteráky a župany", "Textil Hotel s.r.o.", "wellness",
               [("Uterák 70×140", 120, "ks", 4.2), ("Župan", 30, "ks", 18.9)],
               cislo="OBJ-2026-118")
    objednavka(popov, sch, riad, "Tlač letákov na veľtrh", "Print&Co s.r.o.", "marketing",
               [("Leták A5", 2000, "ks", 0.12)], stav="na_schvalenie")
    objednavka(kovar, sch, riad, "Káva do kuchynky", "Kaskády Gastro s.r.o.", "restauracia",
               [("Zrnková káva 1 kg", 10, "kg", 21.5)], stav="na_objednanie")
    print("  objednavky: 4 (u riaditela, objednana, na schvalenie, na objednanie)")
    plan = [
        ("Textil Hotel s.r.o.", "2026-0412", 912.60, "wellness", "Uteráky a župany", "hotovo"),
        ("Kaskády Gastro s.r.o.", "2026-0457", 1452.60, "restauracia", "Potraviny - september", "riaditel"),
        ("TechServis s.r.o.", "TS-26-0931", 348.00, "udrzba", "Servis klimatizácie", "schvalenie"),
        ("Print&Co s.r.o.", "PC-2026-077", 186.30, "marketing", "Vizitky", "zauctovanie"),
        ("Datacomp s.r.o.", "DC-26-1180", 2580.00, "sprava", "Notebooky", "kontrola"),
        ("Orange Slovensko a.s.", "OR-9981203", 74.90, "sprava", "Mobilné služby 09/2026", "kontrola"),
        ("WellSpa Supplies a.s.", "WS-2026-310", 430.00, "wellness", "Masážne oleje", "koncept"),
    ]
    for i, (dod, cislo, suma, stred, predmet, az_po) in enumerate(plan):
        zad = [kovar, vozar, popov][i % 3]
        faktura(zad, ref, sch, riad, uct, dod, cislo, suma, stred, predmet, az_po)
    print(f"  faktury: {len(plan)} (hotova, u riaditela, na schvalenie, na zauctovanie, na kontrolu, rozpisana)")


def main():
    if not HESLO:
        print("appsdemo: nastav ETASK_DEMO_PASSWORD (heslo demo uctov)", file=sys.stderr)
        return 2
    boss = pf.Client("super@netgrif.com", pf.SUPER_PASS)
    zaloz_ucty(boss)
    pridel_roly()
    veduci = klient("mladoniczky@netgrif.com")
    dovolenky(veduci)
    onboarding(klient("samajova@netgrif.com"), veduci, klient("vozar@netgrif.com"))
    cesty(klient("juhas@netgrif.com"), klient("makan@netgrif.com"))
    financie()
    print("appsdemo: hotovo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
