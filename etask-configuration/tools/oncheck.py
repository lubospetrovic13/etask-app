#!/usr/bin/env python3
"""
oncheck - akceptacny test appky Onboarding (nastup noveho zamestnanca) proti BEZIACEMU
enginu.

Zadanie konci vetou "chceme vediet, ze sa to da prejst, nie ze sa to da
naklikat" - tento test presne tu cestu prejde: podat ziadost, dostat ju vratenu,
doplnit, schvalit, odskrtnut tri ucty a vidiet dokonceny nastup. Popri tom overi
styri pravidla zo zadania, ktore sa z XML ani z importu zistit nedaju:

  1. schvaluje LEN ten jeden vybrany veduci (ostatni ulohu ani neuvidia),
  2. pred schvalenim sa nezaklada NIC (uloha na ucty do vtedy neexistuje),
  3. ziadatel nesmie schvalovat vlastnu ziadost,
  4. vratena ziadost pokracuje ako TEN ISTY pripad, s datami.

A este jednu vec, ktora sa z XML overit neda ani nahodou: ze appka je naozaj
dvojjazycna. Zdroj je po anglicky a slovencina je preklad, takze sa meria oboje
- ten isty formular a tie iste polozky menu v `sk` aj v `en` (kroky 2 a 3b).

Klient a pomocnici su v `tools/pftestlib.py` - aj s pascami, na ktore sa v tomto
repozitari naletelo (prihlasenie vracia 405 s tokenom v hlavicke, telo setData
je zanorene pod id ulohy, odmietnutie prichadza ako 200 s `error` v tele).

Predpoklad: bezi stack (tools/up.sh) a role su pridelene (tools/pfseed.py).

    python3 tools/oncheck.py
    python3 tools/oncheck.py --wipe

Exit 0 = vsetko preslo, 1 = nieco zlyhalo.
"""

import sys
import time

import pftestlib as pf

NET = "onboarding/on_request"
MENU = "onboarding/on_menu"
CARD = "onboarding"

# Kto je kto. Obsadenie nie je kozmetika - ani jeden z hracov nesmie byt
# admin@test.local, lebo `ROLE_ADMIN` obchadza vsetky opravnenia Petriflow
# a na admin ucte sa hranica „schvaluje len vybrany veduci" overit NEDA
# (RUNBOOK 11). Zostavaju tri ucty bez ROLE_ADMIN a rozdelene su takto:
#
#   * personalista je operator@test.local - ma `hr` a ZAROVEN `veduci`.
#     To druhe je zamer: prave na nom sa da overit, ze drzitel roly veduci
#     vlastnu ziadost schvalit nemoze - ani ju v zozname uloh neuvidi.
#   * schvalovatel je druhy@test.local - ma `veduci` a `it_spravca`, takze
#     v kroku 8 zaklada aj ucty. Jeho pravo na `t_on_accounts` pritom prichadza
#     LEN z `it_spravca`, takze to zostava skutocna kontrola.
#   * viewer@test.local nema ziadnu rolu - na nom sa overuje, ze kartu nevidi
#     a ze sa neda vybrat za schvalovatela.
HR_EMAIL = "operator@test.local"
VEDUCI_EMAIL = "druhy@test.local"
NIKTO_EMAIL = "viewer@test.local"

# Klient v pftestlib pouziva `lang="zz"`, takze dostava `defaultValue` - teda
# anglicky nazov. Slovencina je preklad a kontroluje sa vedla neho.
#
# POZOR, kde ten preklad zije: NIE v nazve pripadu polozky menu (`Case.title`
# je obycajny String a je vzdy anglicky), ale na naviazanom `filter` pripade
# v poli `i18n_filter_name` ako `{defaultValue, translations}`. Kontrola cez
# titulok pripadu preto hlasi „neprelozene" aj na perfektne prelozenej appke.
ZOBRAZENIA = {
    "Onboarding request": "Žiadosť o nástup",
    "Onboarding drafts and returns": "Rozpísané a vrátené nástupy",
    "Onboardings to approve": "Nástupy na schválenie",
    "Accounts to create": "Účty na založenie",
    "Completed onboardings": "Dokončené nástupy",
}


def pockaj(vyrob, kym, sekund=40):
    """Skus to znova, kym Elastic dobehne.

    Zoznamy pripadov, polozky menu aj viditelnost kariet idu cez Elasticsearch
    a ten indexuje ASYNCHRONNE. Hned po starte backendu (a po kazdom zapise)
    teda odpoved chvilu nesedi so skutocnostou - test spusteny sekundu po
    bootstrape videl tri polozky menu z piatich a bootstrap case bez suhrnu.
    Nie je to chyba appky a nema zmysel to hlasit ako zlyhanie; treba pockat.
    """
    for _ in range(int(sekund / 2)):
        hodnota = vyrob()
        if kym(hodnota):
            return hodnota
        time.sleep(2)
    return vyrob()


def user_id(boss, email):
    st, r = boss.post("/api/user/search?size=50", {"fulltext": email})
    for u in (r.get("_embedded") or {}).get("users", []) if isinstance(r, dict) else []:
        if (u.get("email") or "").lower() == email.lower():
            return u.get("id") or u.get("stringId")
    return None


def vypln(cl, task, meno, priezvisko, email, pozicia, stredisko, nastup, schvalovatel):
    """Vyplni formular ziadosti. `on_approver` je userList - hodnota je
    ZOZNAM ID UCTOV, nie e-mailov a nie jeden retazec."""
    return pf.set_data(cl, task, {
        "on_first_name": {"type": "text", "value": meno},
        "on_last_name": {"type": "text", "value": priezvisko},
        "on_email": {"type": "text", "value": email},
        "on_position": {"type": "text", "value": pozicia},
        "on_cost_centre": {"type": "text", "value": stredisko},
        "on_start_date": {"type": "date", "value": nastup},
        "on_approver": {"type": "userList", "value": [schvalovatel]},
    })


def main():
    boss = pf.Client("super@netgrif.com", pf.SUPER_PASS)
    if "--wipe" in sys.argv:
        # Aj stare identifikatory: premenovanie siete je NOVA siet a jej stare
        # pripady v novych zobrazeniach nikdy nebudu (RUNBOOK 11). Appka sa
        # pocas vyvoja volala `nastup/na_ziadost` a potom `onboarding/na_ziadost`.
        for stary in ["nastup/na_ziadost", "onboarding/na_ziadost"]:
            pf.wipe_cases(boss, stary, "oncheck")
        return pf.wipe_cases(boss, NET, "oncheck")

    hr = pf.Client(HR_EMAIL, pf.TEST_PASS)
    veduci = pf.Client(VEDUCI_EMAIL, pf.TEST_PASS)
    # Ten isty ucet v dvoch ulohach: schvalovatel a IT spravca. Klient je jeden,
    # mena su dve, aby bolo z testu vidno, ktore pravo sa prave overuje.
    it = veduci
    nikto = pf.Client(NIKTO_EMAIL, pf.TEST_PASS)

    hr_id = user_id(boss, HR_EMAIL)
    veduci_id = user_id(boss, VEDUCI_EMAIL)
    nikto_id = user_id(boss, NIKTO_EMAIL)
    if not (hr_id and veduci_id and nikto_id):
        return pf.check("testovacie ucty sa daju najst", False,
                        f"{HR_EMAIL}={hr_id} {VEDUCI_EMAIL}={veduci_id} {NIKTO_EMAIL}={nikto_id}") \
            or pf.report("oncheck")

    print("=== 1. karta v bocnom menu ===")
    for nazov, cl, ocakavane in [("personalista", hr, True),
                                 ("veduci / IT spravca", veduci, True),
                                 ("ucet bez roli", nikto, False)]:
        paths = pockaj(lambda: pf.uri_paths(cl), lambda p: (CARD in p) == ocakavane)
        pf.check(f"{nazov} {'vidi' if ocakavane else 'nevidi'} kartu '{CARD}'",
                 (CARD in paths) == ocakavane, paths)
        if not ocakavane:
            # Bez tejto kontroly by test presiel aj vtedy, keby ucet nevidel
            # ziadnu kartu - a nedokazoval by nic.
            pf.check("ucet bez roli pritom ine karty vidi", len(paths) > 0, paths)

    print("\n=== 2. zobrazenia a stlpce ===")
    items = pockaj(lambda: pf.menu_items(boss, prefix="on_"),
                   lambda i: all(z in i for z in ZOBRAZENIA))
    for want in ZOBRAZENIA:
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
        preklad = None
        if v.get("filter_case_id"):
            st, fc = boss.get(f"/api/workflow/case/{v['filter_case_id']}")
            for d in (fc.get("immediateData") or []):
                if d.get("allowedNets"):
                    have = set(d["allowedNets"])
                if d.get("importId") == "i18n_filter_name":
                    preklad = ((d.get("value") or {}).get("translations") or {}).get("sk")
        pf.check(f"'{want}' ma v allowedNets siete svojich stlpcov", need <= have,
                 f"treba {sorted(need)}, ma {sorted(have)}")
        # Zdroj je anglicky, slovencina je PREKLAD - a polozka menu ho nesie
        # na svojom `filter` pripade, nie v nazve pripadu.
        pf.check(f"'{want}' ma slovensky nazov '{ZOBRAZENIA[want]}'",
                 preklad == ZOBRAZENIA[want], preklad)

    mt = pockaj(lambda: [c["title"] for c in pf.cases_of(boss, MENU, size=20)],
                lambda t: any("5/5" in x for x in t))
    pf.check("bootstrap case menu hlasi 5/5", any("5/5" in t for t in mt), mt)

    print("\n=== 3. HR zaklada ziadost ===")
    net = pf.newest_net(hr, NET)
    print(f"  siet {net['identifier']} v{net['version']}")
    case_id, case = pf.new_case(hr, net["stringId"])
    t = pf.tasks_of(hr, case_id)
    pf.check("na zaciatku je PRESNE jedna uloha", list(t) == ["t_on_request"], list(t))
    podanie = t.get("t_on_request")
    if not podanie:
        return pf.report("oncheck")

    print("\n=== 3b. slovencina na formulari ===")
    # Ten isty formular v dvoch jazykoch. `sk` je preklad, `en` je default
    # priamo z XML - a musia sediet oba, inak je appka jednojazycna a nikde
    # sa to neohlasi.
    hr_sk = pf.Client(HR_EMAIL, pf.TEST_PASS, lang="sk")
    hr_en = pf.Client(HR_EMAIL, pf.TEST_PASS, lang="en")
    pole_sk = pf.field_map(hr_sk, podanie)
    pole_en = pf.field_map(hr_en, podanie)

    def nazov_pola(mapa, pole):
        f = mapa.get(pole) or {}
        return f.get("name") or f.get("title")

    for pole, sk_txt, en_txt in [("on_first_name", "Meno", "First name"),
                                 ("on_cost_centre", "Stredisko", "Cost centre"),
                                 ("on_approver", "Schvaľujúci vedúci", "Approving manager")]:
        pf.check(f"'{pole}' je na sk portali po slovensky",
                 nazov_pola(pole_sk, pole) == sk_txt, nazov_pola(pole_sk, pole))
        pf.check(f"'{pole}' je na en portali po anglicky",
                 nazov_pola(pole_en, pole) == en_txt, nazov_pola(pole_en, pole))

    opts_sk = ((pole_sk.get("on_status") or {}).get("options") or {})
    pf.check("moznosti stavu su prelozene", opts_sk.get("draft") == "Rozpísaná",
             opts_sk)

    st, r = hr_sk.post("/api/task/search?size=20", {"case": [{"id": case_id}]})
    tsk = [x for x in (r.get("_embedded") or {}).get("tasks", [])
           if x["transitionId"] == "t_on_request"]
    pf.check("nazov ulohy je po slovensky",
             bool(tsk) and tsk[0].get("title") == "Žiadosť o nástup",
             tsk[0].get("title") if tsk else "uloha nenajdena")
    # Vlastny titulok tlacidla sa prekladá rovnako ako vsetko ostatné.
    pf.check("tlacidlo na podanie je po slovensky",
             bool(tsk) and tsk[0].get("finishTitle") == "Podať na schválenie",
             tsk[0].get("finishTitle") if tsk else "uloha nenajdena")

    print("\n=== 3c. podanie ziadosti ===")
    # Odmietnutie prichadza ako HTTP 200 s `error` v tele, nie ako 4xx.
    st, r = pf.finish(hr, podanie)
    pf.check("prazdna ziadost je odmietnuta", pf.err_body(r), str(r)[:110])

    priezvisko = f"Nováková{int(time.time()) % 100000}"
    nastup = "2026-11-02"

    vypln(hr, podanie, "Jana", priezvisko, "jana bez zavinaca",
          "Účtovníčka", "Správa", nastup, veduci_id)
    st, r = pf.finish(hr, podanie)
    pf.check("nezmyselny pracovny e-mail je odmietnuty", pf.err_body(r), str(r)[:110])

    # ŠTVORO OČÍ: zadanie to hovori vyslovne - "the requester must not approve
    # their own request".
    vypln(hr, podanie, "Jana", priezvisko, "jana.novakova@firma.sk",
          "Účtovníčka", "Správa", nastup, hr_id)
    st, r = pf.finish(hr, podanie)
    pf.check("ziadatel sam sebe ako schvalovatel je odmietnuty", pf.err_body(r), str(r)[:130])

    # Clovek bez roly veduci by ziadost schvalit mohol (userRef mu to da), ale
    # nikto ho za veduceho nepovazuje - a bez tejto kontroly by sa to nikde
    # nepovedalo.
    vypln(hr, podanie, "Jana", priezvisko, "jana.novakova@firma.sk",
          "Účtovníčka", "Správa", nastup, nikto_id)
    st, r = pf.finish(hr, podanie)
    pf.check("clovek bez roly veduci ako schvalovatel je odmietnuty", pf.err_body(r), str(r)[:130])

    vypln(hr, podanie, "Jana", priezvisko, "jana.novakova@firma.sk",
          "Účtovníčka", "Správa", nastup, veduci_id)
    st, r = pf.finish(hr, podanie)
    pf.check("podanie na schvalenie preslo", pf.ok_body(r), str(r)[:130])

    # Stlpec „Schvaluje" zo zadania. Vypliia ho `menaUzivatelov(...)` z hodnoty
    # user pickera - a prave tam bola diera: `usersOf` nepoznal `UserFieldValue`,
    # spadol na retazcovy fallback a polozku TICHO zahodil, takze stlpec zostal
    # prazdny a nikde sa nepovedalo preco.
    st, c = hr.get(f"/api/workflow/case/{case_id}")
    meno_schvalovatela = ""
    for d in (c.get("immediateData") or []):
        if d.get("importId") == "on_approver_name":
            meno_schvalovatela = (d.get("value") or "")
    pf.check("stlpec 'Schvaluje' nesie meno vybraneho veduceho",
             "Second Tester" == meno_schvalovatela, repr(meno_schvalovatela))
    pf.check("nazov pripadu nesie meno nastupujuceho, nie stav",
             priezvisko in (c["title"] or "") and "schvál" not in (c["title"] or "").lower(),
             c["title"])

    print("\n=== 4. pred schvalenim sa nezaklada nic ===")
    vsetky = pf.tasks_raw(boss, case_id)
    pf.check("uloha na zakladanie uctov NEEXISTUJE", "t_on_accounts" not in vsetky, list(vsetky))
    pf.check("caka sa na rozhodnutie", "t_on_approval" in vsetky, list(vsetky))
    pf.check("HR po podani nema co robit", list(pf.tasks_of(hr, case_id)) == [],
             list(pf.tasks_of(hr, case_id)))

    print("\n=== 5. schvaluje len ten jeden vybrany veduci ===")
    tv = pf.tasks_of(veduci, case_id)
    pf.check("vybrany veduci ulohu vidi", "t_on_approval" in tv, list(tv))
    # Personalista, ktory ziadost podal, ma SAM rolu `veduci` - a aj tak tu
    # ulohu nevidi. To je oboje naraz: „schvaluje len vybrany" aj „ziadatel
    # neschvaluje sam sebe", tentoraz na urovni opravneni, nie kontroly v akcii.
    pf.check("ziadatel s rolou veduci tu ulohu nevidi",
             "t_on_approval" not in pf.tasks_of(hr, case_id),
             list(pf.tasks_of(hr, case_id)))
    # A nielenze ju nevidi v zozname - nesmie ju ani prevziat.
    st, r = pf.assign(hr, vsetky["t_on_approval"])
    pf.check("ziadatel si ulohu ani neprevezme", st >= 400 or pf.err_body(r),
             f"{st} {str(r)[:90]}")

    print("\n=== 6. vratenie na doplnenie ===")
    rozhodnutie = tv.get("t_on_approval")
    pf.set_data(veduci, rozhodnutie,
                {"on_decision": {"type": "enumeration_map", "value": "returned"}})
    st, r = pf.finish(veduci, rozhodnutie)
    pf.check("vratenie bez duvodu je odmietnute", pf.err_body(r), str(r)[:110])

    pf.set_data(veduci, rozhodnutie, {
        "on_decision": {"type": "enumeration_map", "value": "returned"},
        "on_note": {"type": "text", "value": "Doplň prosím stredisko - toto je iné."}})
    st, r = pf.finish(veduci, rozhodnutie)
    pf.check("vratenie s duvodom preslo", pf.ok_body(r), str(r)[:110])

    t2 = pf.tasks_of(hr, case_id)
    pf.check("ziadost je spat u HR ako TEN ISTY pripad",
             list(t2) == ["t_on_request"], list(t2))
    pf.check("veduci uz rozhodnutie nevidi",
             "t_on_approval" not in pf.tasks_of(veduci, case_id), "")
    podanie2 = t2.get("t_on_request")
    if not podanie2:
        return pf.report("oncheck")
    v = pf.values(hr, podanie2)
    pf.check("vyplnene udaje zostali", v.get("on_last_name") == priezvisko,
             v.get("on_last_name"))
    pf.check("stav je 'returned'", v.get("on_status") == "returned", v.get("on_status"))
    pf.check("HR vidi, co ma doplnit", "stredisko" in ((v.get("on_note") or "")),
             v.get("on_note"))

    print("\n=== 7. doplnenie, schvalenie ===")
    pf.set_data(hr, podanie2, {"on_cost_centre": {"type": "text", "value": "Financie"}})
    st, r = pf.finish(hr, podanie2)
    pf.check("opatovne podanie preslo", pf.ok_body(r), str(r)[:110])

    rozhodnutie2 = pf.tasks_of(veduci, case_id).get("t_on_approval")
    if not rozhodnutie2:
        return pf.check("veduci ma znova rozhodnut", False, "") or pf.report("oncheck")
    pf.set_data(veduci, rozhodnutie2,
                {"on_decision": {"type": "enumeration_map", "value": "approved"}})
    st, r = pf.finish(veduci, rozhodnutie2)
    pf.check("schvalenie preslo", pf.ok_body(r), str(r)[:110])

    print("\n=== 8. IT zaklada ucty ===")
    ucty = pf.tasks_of(it, case_id).get("t_on_accounts")
    pf.check("IT spravca ma ulohu na zalozenie uctov", bool(ucty),
             list(pf.tasks_of(it, case_id)))
    if not ucty:
        return pf.report("oncheck")
    v = pf.values(it, ucty)
    pf.check("IT vidi udaje zo ziadosti bez toho, aby hladal inde",
             v.get("on_email") == "jana.novakova@firma.sk" and v.get("on_cost_centre") == "Financie",
             {k: v.get(k) for k in ("on_email", "on_cost_centre", "on_start_date")})

    pf.set_data(it, ucty, {"on_entra": {"type": "boolean", "value": True},
                            "on_atlassian": {"type": "boolean", "value": True}})
    st, r = pf.finish(it, ucty)
    pf.check("dva ucty z troch nestacia", pf.err_body(r), str(r)[:140])
    pf.check("nedokoncena uloha zostava otvorena",
             "t_on_accounts" in pf.tasks_of(it, case_id), list(pf.tasks_of(it, case_id)))
    v = pf.values(it, ucty)
    pf.check("odskrtnute ucty sa medzitym ulozili", v.get("on_entra") is True, v.get("on_entra"))

    pf.set_data(it, ucty, {"on_portal": {"type": "boolean", "value": True}})
    st, r = pf.finish(it, ucty)
    pf.check("po tretom ucte nastup prechadza do hotovych", pf.ok_body(r), str(r)[:140])

    print("\n=== 9. dokonceny nastup vidia vsetci zainteresovani ===")
    st, c = hr.get(f"/api/workflow/case/{case_id}")
    pf.check("farba pripadu je zelena", c.get("color") == "green", c.get("color"))
    for nazov, cl in [("personalista", hr), ("veduci / IT spravca", veduci)]:
        tt = pf.tasks_of(cl, case_id)
        pf.check(f"{nazov} vidi dokonceny nastup", list(tt) == ["t_on_overview"], list(tt))
    prehlad = pf.tasks_of(hr, case_id).get("t_on_overview")
    if prehlad:
        v = pf.values(hr, prehlad)
        pf.check("stav je 'done'", v.get("on_status") == "done", v.get("on_status"))
        pf.check("je zapisane, kto schvalil", bool(v.get("on_approved_by")), v.get("on_approved_by"))
        pf.check("je zapisane, kto zalozil ucty", bool(v.get("on_accounts_by")),
                 v.get("on_accounts_by"))
        pf.check("priebeh hovori, komu ziadost sla na schvalenie",
                 "approval to Second Tester" in (v.get("on_history") or ""),
                 (v.get("on_history") or "").splitlines()[1:2])
        pf.check("priebeh drzi cely pribeh ziadosti",
                 len((v.get("on_history") or "").splitlines()) >= 5,
                 (v.get("on_history") or "").replace("\n", " | ")[:200])
        # Read-only pohlad nema co dokoncovat - prazdny titulok tlacidlo skryje
        # (`canFinish()` je opravnenie && title !== '').
        #
        # POZOR NA ENDPOINT: titulky udalosti nesie `/api/task/search`, teda to,
        # co pouziva zoznam uloh vo frontende. `/api/task/case/{id}` ich
        # NEVRACIA - vsetky styri pridu ako `null`, takze kontrola na tom
        # endpointe hlasi chybu, ktora v appke nie je.
        st, r = hr.post("/api/task/search?size=20", {"case": [{"id": case_id}]})
        tsk = [x for x in (r.get("_embedded") or {}).get("tasks", [])
               if x["transitionId"] == "t_on_overview"]
        pf.check("prehlad nema tlacidlo DOKONCIT ani ZRUSIT",
                 bool(tsk) and tsk[0].get("finishTitle") == ""
                 and tsk[0].get("cancelTitle") == "",
                 {k: tsk[0].get(k) for k in ("finishTitle", "cancelTitle")} if tsk
                 else "uloha nenajdena")

    print("\n=== 10. zobrazenia filtruju to, co maju ===")
    vsetky_q = f'processIdentifier:"{NET}"'

    def najdi(cl, dopyt):
        st, r = cl.post("/api/workflow/case/search?size=100", {"query": dopyt})
        cases = (r.get("_embedded") or {}).get("cases", []) if isinstance(r, dict) else []
        return [x["stringId"] for x in cases]

    # Podla KLUCA moznosti - popisok sa prekladom meni, kluc nie.
    pf.check("dokonceny nastup je v 'Completed onboardings'",
             case_id in najdi(hr, vsetky_q + ' AND dataSet.on_status.keyValue:"done"'),
             "")
    pf.check("dokonceny nastup uz nie je v 'Onboardings to approve'",
             case_id not in najdi(hr, vsetky_q + ' AND taskIds:"t_on_approval"'), "")
    c2, _ = pf.new_case(hr, net["stringId"])
    pf.check("novy rozpisany nastup je v 'Drafts and returns'",
             c2 in najdi(hr, vsetky_q + ' AND taskIds:"t_on_request"'), "")

    return pf.report("oncheck")


if __name__ == "__main__":
    sys.exit(main())
