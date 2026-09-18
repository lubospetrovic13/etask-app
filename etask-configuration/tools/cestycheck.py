#!/usr/bin/env python3
"""
cestycheck - akceptacny test appky Vyuctovanie pracovnych ciest proti
BEZIACEMU enginu.

Appka zije pod `hr/cesty`. Jej zmyslom nie je vlastne tlacivo, ale CUDZIE:
uctovna firma posiela xlsx zosit, raz za cas ho prepise, a appka don len
doplna hodnoty. Z toho plynie, co sa tu overuje a preco:

  1. KARTA. `hr/cesty` vidi len ten, kto ma rolu appky. Karta, ktoru vidi
     kazdy prihlaseny, je chyba konfiguracie, nie vlastnost.
  2. KALKULACKA. Stravne po casovych pasmach, zrazky za bezplatne jedlo,
     zakladna nahrada a nahrada za PHM. Test si sumy rata SAM, nezavisle od
     siete - inak by overoval len to, ze appka je konzistentna sama so sebou.
  3. STYRI OCI. Schvaluje JEDEN vybrany clovek. Iny nositel roly `veduci`
     tu ulohu nesmie ani vidiet - a prave to sa da lahko pokazit tym, ze sa
     na prechod pridá `roleRef` (roleRef a userRef sa na pravach spajaju).
  4. TLACIVO. Vyplneny zosit sa da stiahnut a su v nom NASE hodnoty
     v spravnych bunkach - a hlavne: VZORCE SABLONY ZOSTALI VZORCAMI.
     To je cela pointa appky. Keby sme ich prepisali vyratanymi cislami,
     kazda oprava sadzieb od uctovnej firmy by sa pri exporte stratila.
  5. PODPIS SA NESIE. Kto ho nahral raz, ma ho aj na dalsom vyuctovani.

Sablona sa vyraba v kode (`xlsx_sablona`), nie ako binarny fixture v gite:
takto je v teste vidno, co presne v nej stoji - vratane toho vzorca, ktory
ma prezit - a nevznika binarny diff, ktory nikto neprecita.

Klient a pomocnici su v `tools/pftestlib.py`.

Predpoklad: bezi stack (tools/up.sh) a role su pridelene (tools/pfseed.py).

    python3 tools/cestycheck.py
    python3 tools/cestycheck.py --wipe

Test ZAKLADA UZIVATELOM PRIPADY - nespustat proti produkcii.

Exit 0 = vsetko preslo, 1 = nieco zlyhalo.
"""

import io
import math
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

import pftestlib as pf

NET = "hr/cesty/pc_vyuctovanie"
MENU = "hr/cesty/pc_menu"
NASTAVENIA = "hr/cesty/pc_nastavenia"
CARD = "hr/cesty"

ZAMESTNANEC = "operator@test.local"   # rola `zamestnanec`
SCHVALOVATEL = "admin@test.local"     # rola `veduci` (aj ROLE_ADMIN)
INY_VEDUCI = "druhy@test.local"       # rola `veduci` BEZ ROLE_ADMIN, aj `mzdy`
NOONE = "viewer@test.local"           # ziadna procesna rola

HAROK = "Tuzemská cesta"              # nazov harku v tlacive (cudzi system)

# Sadzby z `pc_nastavenia`. Test ich drzi ZVLAST a rata s nimi sam - keby si
# ich cital zo siete, overil by len to, ze siet suhlasi sama so sebou.
S1, S2, S3 = 9.30, 13.80, 20.60       # 5-12 h, 12-18 h, nad 18 h
ZR = {"nie": 0.0, "ranajky": 0.25, "obed": 0.40, "vecera": 0.35,
      "ranajky_obed": 0.65, "ranajky_vecera": 0.60, "obed_vecera": 0.75,
      "ranajky_obed_vecera": 1.00}
KM_AUTO, KM_MOTO, KOEF = 0.313, 0.09, 1.1


# ------------------------------------------------------- vlastna kalkulacka

def stravne(minut, strava):
    """To iste pravidlo, napisane nezavisle od siete."""
    if minut <= 300:
        return 0.0
    zaklad = S1 if minut <= 720 else (S2 if minut <= 1080 else S3)
    return max(0.0, zaklad - ZR[strava] * S3)


def cent(x):
    return round(x + 1e-9, 2)


def nahor(x):
    """ROUNDUP na dve desatinne miesta - tak to rata tlacivo."""
    return math.ceil(x * 100 - 1e-9) / 100.0


def ocakavane(cesty, spotreba):
    st = za = ph = ub = ine = 0.0
    for c in cesty:
        km = c["km_tam"] + c["km_spat"]
        st += stravne(c["minut"], c["strava"])
        if c["doprava"] == "auto":
            za += km * KM_AUTO
            ph += km / 100.0 * spotreba * KOEF * c["cena"]
        elif c["doprava"] == "motocykel":
            za += km * KM_MOTO
            ph += km / 100.0 * spotreba * KOEF * c["cena"]
        ub += c["ubytovanie"]
        ine += c["ine"]
    spolu = cent(st) + nahor(za) + nahor(ph) + cent(ub) + cent(ine)
    return {"stravne": cent(st), "zakladna": nahor(za), "phm": nahor(ph),
            "ubytovanie": cent(ub), "ine": cent(ine), "spolu": cent(spolu)}


# ------------------------------------------------------------ xlsx sablona

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def xlsx_sablona():
    """Najmensi platny xlsx s geometriou skutocneho tlaciva.

    Podstatne su tri veci:
      * hárok sa vola tak ako v tlacive,
      * jedna cesta zabera DVA riadky (12/13, 14/15, ...),
      * v stlpci I je VZOREC. Ten musi export prezit - je to to jedine,
        co appka o tlacive naozaj slubuje.
    """
    def bunka(ref, obsah):
        return f'<c r="{ref}" t="inlineStr"><is><t>{obsah}</t></is></c>'

    riadky = [
        '<row r="4"><c r="C4" t="inlineStr"><is><t>?</t></is></c></row>',
        '<row r="6"><c r="C6" t="inlineStr"><is><t>?</t></is></c></row>',
    ]
    for i in range(31):
        zaklad = 12 + i * 2
        # Vzorec zameny nema - je to presne ten, ktory ma prezit.
        riadky.append(
            f'<row r="{zaklad}">'
            f'<c r="I{zaklad}"><f>IF(C{zaklad}="","",1)</f><v>0</v></c>'
            f'<c r="K{zaklad}"><f>IF(F{zaklad}="","",2)</f><v>0</v></c>'
            f'</row>')
        riadky.append(f'<row r="{zaklad + 1}"/>')
    riadky.append('<row r="76"><c r="M76"><v>0</v></c></row>')

    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetData>' + "".join(riadky) + '</sheetData></worksheet>')

    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
          ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
          f'<sheets><sheet name="{HAROK}" sheetId="1" r:id="rId1"/></sheets></workbook>')

    wbrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
              '<Relationship Id="rId2" Target="styles.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"/>'
              '</Relationships>')

    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="xl/workbook.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"/>'
            '</Relationships>')

    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
              '<borders count="1"><border/></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
              '</styleSheet>')

    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          '</Types>')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wbrels)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/styles.xml", styles)
    return buf.getvalue()


def citaj_xlsx(data):
    """{"A12": (hodnota, vzorec)} z prveho harku. Bez openpyxl - zip a XML
    staci a nepribuda zavislost."""
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
    root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    out = {}
    for c in root.iter(NS + "c"):
        v, fx = c.find(NS + "v"), c.find(NS + "f")
        hodnota = None
        if c.get("t") == "s" and v is not None:
            hodnota = shared[int(v.text)]
        elif c.get("t") == "inlineStr":
            isn = c.find(NS + "is")
            hodnota = "".join(x.text or "" for x in isn.iter(NS + "t")) if isn is not None else None
        elif v is not None:
            hodnota = v.text
        out[c.get("r")] = (hodnota, fx.text if fx is not None else None)
    return out, z.namelist()


# ------------------------------------------------------------------ pomoc

def pridaj_cestu(cl, task_id, c):
    """Vyplni formular cesty a stlaci tlacidlo Pridat."""
    pf.set_data(cl, task_id, {
        "pc_c_datum": {"type": "date", "value": c["datum"]},
        "pc_c_od": {"type": "text", "value": c["od"]},
        "pc_c_do": {"type": "text", "value": c["do"]},
        "pc_c_miesto_zac": {"type": "text", "value": c.get("zac", "Bratislava")},
        "pc_c_miesto_kon": {"type": "text", "value": c.get("kon", "Bratislava")},
        "pc_c_rokovanie": {"type": "text", "value": c.get("rokovanie", "Klient")},
        "pc_c_doprava": {"type": "enumeration_map", "value": c["doprava"]},
        "pc_c_strava": {"type": "enumeration_map", "value": c["strava"]},
        "pc_c_km_tam": {"type": "number", "value": c["km_tam"]},
        "pc_c_km_spat": {"type": "number", "value": c["km_spat"]},
        "pc_c_cena_phm": {"type": "number", "value": c["cena"]},
        "pc_c_ubytovanie": {"type": "number", "value": c["ubytovanie"]},
        "pc_c_ine": {"type": "number", "value": c["ine"]}})
    return pf.set_data(cl, task_id, {"btn_pc_pridat": {"type": "button", "value": 1}})


def main():
    boss = pf.Client("super@netgrif.com", pf.SUPER_PASS)
    if "--wipe" in sys.argv:
        return pf.wipe_cases(boss, NET)

    zam = pf.Client(ZAMESTNANEC, pf.TEST_PASS)
    schv = pf.Client(SCHVALOVATEL, pf.TEST_PASS)
    iny = pf.Client(INY_VEDUCI, pf.TEST_PASS)
    nikto = pf.Client(NOONE, pf.TEST_PASS)

    print("=== 1. siete, karta a menu ===")
    net = pf.newest_net(zam, NET)
    pf.check("siet " + NET + " je naimportovana", net is not None, net and net.get("version"))
    if net is None:
        return pf.report("cestycheck")
    pf.check("siet " + NASTAVENIA + " je naimportovana",
             pf.newest_net(boss, NASTAVENIA) is not None)
    pf.check("siet " + MENU + " je naimportovana", pf.newest_net(boss, MENU) is not None)

    karty_zam = pf.uri_paths(zam, deep=True)
    pf.check("zamestnanec vidi kartu " + CARD, CARD in karty_zam, karty_zam)
    karty_nikto = pf.uri_paths(nikto, deep=True)
    pf.check("bez roly sa karta " + CARD + " NEVIDI", CARD not in karty_nikto, karty_nikto)

    polozky = pf.menu_items(boss, prefix="pc_")
    pf.check("menu ma 5 zobrazeni + konfiguraciu", len(polozky) >= 6, sorted(polozky))

    print("\n=== 2. konfiguracia appky ===")
    cfg = pf.cases_of(boss, NASTAVENIA)
    pf.check("konfiguracia ma prave jeden case", len(cfg) == 1, len(cfg))
    if not cfg:
        return pf.report("cestycheck")
    spravca = pf.Client(SCHVALOVATEL, pf.TEST_PASS)   # ma rolu `spravca`
    tcfg = pf.tasks_of(spravca, cfg[0]["stringId"]).get("t_pcn")
    pf.check("spravca vidi nastavenia ciest", bool(tcfg))
    if not tcfg:
        return pf.report("cestycheck")
    vcfg = pf.values(spravca, tcfg)
    pf.check("sadzby stravneho su 9.30 / 13.80 / 20.60",
             [float(vcfg.get(k) or 0) for k in
              ("pcn_strav_5_12", "pcn_strav_12_18", "pcn_strav_nad_18")] == [S1, S2, S3],
             [vcfg.get("pcn_strav_5_12"), vcfg.get("pcn_strav_12_18"), vcfg.get("pcn_strav_nad_18")])
    pf.check("mapovanie buniek je vyplnene", bool((vcfg.get("pcn_mapovanie") or "").strip()))

    # Pasma musia rast - inak by dlhsia cesta dala mensie stravne.
    pf.set_data(spravca, tcfg, {"pcn_strav_nad_18": {"type": "number", "value": 5}})
    st, r = pf.finish(spravca, tcfg)
    pf.check("klesajuce pasma stravneho su odmietnute", pf.err_body(r), str(r)[:140])
    pf.set_data(spravca, tcfg, {"pcn_strav_nad_18": {"type": "number", "value": S3}})

    # Nepouzitelne mapovanie sa musi zachytit TU, a nie az na cudzom vyuctovani.
    pf.set_data(spravca, tcfg, {"pcn_mapovanie": {"type": "text", "value": "{nie je json"}})
    st, r = pf.finish(spravca, tcfg)
    pf.check("rozsypane mapovanie je odmietnute", pf.err_body(r), str(r)[:140])
    pf.set_data(spravca, tcfg, {"pcn_mapovanie": {"type": "text",
                                                  "value": vcfg.get("pcn_mapovanie")}})

    # Sablona: nahra sa zosit s geometriou tlaciva a so vzorcom, ktory ma prezit.
    sablona = xlsx_sablona()
    st, r = pf.upload(spravca, tcfg, "pcn_sablona", "tlacivo.xlsx", sablona)
    pf.check("sablona sa da nahrat", st == 200 and r is not None, st)
    st, r = pf.finish(spravca, tcfg)
    pf.check("nastavenia so sablonou sa ulozia", pf.ok_body(r), str(r)[:140])

    print("\n=== 3. zalozenie a vlastnictvo ===")
    case_id, _ = pf.new_case(zam, net["stringId"])
    t = pf.tasks_of(zam, case_id)
    pf.check("zamestnanec ma ulohu 't_vyplnit'", "t_vyplnit" in t, list(t))
    pf.check("cudzi bez roly case NEVIDI", not pf.tasks_of(nikto, case_id),
             list(pf.tasks_of(nikto, case_id)))
    tid = t.get("t_vyplnit")
    if not tid:
        return pf.report("cestycheck")
    v = pf.values(zam, tid)
    pf.check("obdobie je predvyplnene", bool(v.get("pc_obdobie")), v.get("pc_obdobie"))
    pf.check("stav je 'rozpisane'", v.get("pc_stav_label") == "rozpisane", v.get("pc_stav_label"))
    moznosti = pf.options(zam, tid, "pc_schvalovatel_vyber")
    pf.check("ponuka schvalovatelov nie je prazdna", bool(moznosti), list(moznosti.values())[:4])

    print("\n=== 4. kalkulacka: casove pasma a zrazky ===")
    # Obdobie sa nastavi na pevne, aby test nezavisel od dnesneho datumu.
    obdobie = "07/2026"
    pf.set_data(zam, tid, {"pc_rok": {"type": "number", "value": 2026},
                           "pc_mesiac": {"type": "enumeration_map", "value": "07"},
                           "pc_spotreba": {"type": "number", "value": 8.3},
                           "pc_palivo": {"type": "enumeration_map", "value": "benzin_95"},
                           "pc_spz": {"type": "text", "value": "ZM396CV"},
                           "pc_preddavok": {"type": "number", "value": 50}})
    pf.check("obdobie sa prepocitalo na " + obdobie,
             pf.values(zam, tid).get("pc_obdobie") == obdobie,
             pf.values(zam, tid).get("pc_obdobie"))

    cesty = [
        # 3 h -> pod 5 hodin, stravne NULA, ale km sa platia
        dict(datum="2026-07-01", od="15:00", do="18:00", minut=180, doprava="auto",
             strava="nie", km_tam=70, km_spat=70, cena=1.6, ubytovanie=0, ine=0),
        # 8 h -> prve pasmo, obed zabezpeceny -> zrazka 40 % z NAJVYSSIEHO pasma
        dict(datum="2026-07-02", od="08:00", do="16:00", minut=480, doprava="autobus",
             strava="obed", km_tam=0, km_spat=0, cena=0, ubytovanie=0, ine=12.5),
        # 20 h -> tretie pasmo, motocykel
        dict(datum="2026-07-03", od="06:00", do="02:00", minut=1200, doprava="motocykel",
             strava="ranajky_vecera", km_tam=40, km_spat=40, cena=1.55,
             ubytovanie=65, ine=3.2),
    ]
    for c in cesty:
        st, r = pridaj_cestu(zam, tid, c)
        pf.check("cesta " + c["datum"] + " pridana", pf.ok_body(r), str(r)[:120])

    v = pf.values(zam, tid)
    ocak = ocakavane(cesty, 8.3)
    pf.check("pocet ciest je 3", int(float(v.get("pc_pocet_ciest") or 0)) == 3,
             v.get("pc_pocet_ciest"))
    for kluc, pole in (("stravne", "pc_stravne"), ("zakladna", "pc_zakladna"),
                       ("phm", "pc_phm"), ("ubytovanie", "pc_ubytovanie"),
                       ("ine", "pc_ine"), ("spolu", "pc_spolu")):
        pf.check("sucet " + kluc + " sedi s nezavislym vypoctom",
                 abs(float(v.get(pole) or 0) - ocak[kluc]) < 0.005,
                 f"ocakavam {ocak[kluc]}, mam {v.get(pole)}")
    pf.check("cesta do 5 hodin nedostala stravne",
             abs(ocak["stravne"] - (stravne(480, "obed") + stravne(1200, "ranajky_vecera"))) < 0.005,
             ocak["stravne"])
    pf.check("na vyplatenie = spolu - preddavok",
             abs(float(v.get("pc_doplatok") or 0) - (ocak["spolu"] - 50)) < 0.005,
             v.get("pc_doplatok"))

    # Zmena spotreby musi prepocitat CELY zoznam, nielen dalsiu cestu.
    pf.set_data(zam, tid, {"pc_spotreba": {"type": "number", "value": 10.0}})
    v10 = pf.values(zam, tid)
    pf.check("zmena spotreby prepocitala nahradu za PHM",
             abs(float(v10.get("pc_phm") or 0) - ocakavane(cesty, 10.0)["phm"]) < 0.005,
             f"ocakavam {ocakavane(cesty, 10.0)['phm']}, mam {v10.get('pc_phm')}")
    pf.set_data(zam, tid, {"pc_spotreba": {"type": "number", "value": 8.3}})

    print("\n=== 5. odobranie cesty ide podla ID, nie podla poradia ===")
    vyber = pf.options(zam, tid, "pc_cesty_vyber")
    pf.check("vyber ponuka 3 cesty", len(vyber) == 3, sorted(vyber))
    prostredna = sorted(vyber)[1] if len(vyber) == 3 else None
    if prostredna:
        pf.set_data(zam, tid, {"pc_cesty_vyber": {"type": "multichoice_map",
                                                  "value": [prostredna]}})
        pf.set_data(zam, tid, {"btn_pc_odobrat": {"type": "button", "value": 1}})
        v2 = pf.values(zam, tid)
        pf.check("po odobrani zostali 2 cesty",
                 int(float(v2.get("pc_pocet_ciest") or 0)) == 2, v2.get("pc_pocet_ciest"))
        # Vratime ju spat, nech dalej pracujeme s troma.
        zostala = [c for c in cesty if c["datum"] not in (v2.get("pc_cesty") or "")]
        if zostala:
            pridaj_cestu(zam, tid, zostala[0])
        pf.check("po vrateni su zase 3 cesty",
                 int(float(pf.values(zam, tid).get("pc_pocet_ciest") or 0)) == 3,
                 pf.values(zam, tid).get("pc_pocet_ciest"))

    print("\n=== 6. podanie: validacie a styri oci ===")
    st, r = pf.finish(zam, tid)
    pf.check("bez vybraneho schvalovatela sa podat neda", pf.err_body(r), str(r)[:160])

    # Sam seba si vybrat nemoze - v ponuke ani nie je.
    st, ja = zam.get("/api/user/me")
    moje_id = (ja or {}).get("id") or (ja or {}).get("stringId")
    pf.check("ziadatel NIE JE vo vlastnej ponuke schvalovatelov",
             moje_id not in moznosti, moje_id)

    # Podpis zamestnanca - nahra sa RAZ a ma sa preniest na dalsie vyuctovanie.
    st, r = pf.upload(zam, tid, "pc_podpis_zam", "podpis.png", pf.tiny_png(120, 40))
    pf.check("podpis zamestnanca sa da nahrat", st == 200 and r is not None, st)

    schv_id = None
    for k, popis in moznosti.items():
        schv_id = k
        break
    pf.set_data(zam, tid, {"pc_schvalovatel_vyber": {"type": "enumeration_map",
                                                     "value": schv_id}})
    st, r = pf.finish(zam, tid)
    pf.check("podanie preslo", pf.ok_body(r), str(r)[:160])

    print("\n=== 7. schvaluje LEN vybrany clovek ===")
    vsetky_ulohy = pf.tasks_raw(boss, case_id)
    pf.check("uloha 't_schvalit' vznikla", "t_schvalit" in vsetky_ulohy, list(vsetky_ulohy))
    # `druhy@test.local` ma rolu `veduci`, ale NIE JE vybrany. Nema ROLE_ADMIN,
    # takze na nom sa to overit da - na adminovi nie, ten obchadza vsetko.
    vid_iny = pf.tasks_of(iny, case_id)
    pf.check("iny nositel roly `veduci` ulohu na schvalenie NEVIDI",
             "t_schvalit" not in vid_iny, list(vid_iny))
    ts = vsetky_ulohy.get("t_schvalit")
    st, r = pf.assign(iny, ts)
    pf.check("iny `veduci` si ulohu ani nepriradi",
             pf.err_body(r) or st >= 400, f"{st} {str(r)[:120]}")

    print("\n=== 8. vratenie na opravu a druhy pokus ===")
    pf.set_data(schv, ts, {"pc_rozhodnutie": {"type": "enumeration_map", "value": "vratit"}})
    st, r = pf.finish(schv, ts)
    pf.check("vratenie bez komentara je odmietnute", pf.err_body(r), str(r)[:160])
    pf.set_data(schv, ts, {"pc_rozhodnutie": {"type": "enumeration_map", "value": "vratit"},
                           "pc_komentar": {"type": "text", "value": "Chyba ubytovanie."}})
    st, r = pf.finish(schv, ts)
    pf.check("vratenie preslo", pf.ok_body(r), str(r)[:160])
    t = pf.tasks_of(zam, case_id)
    pf.check("vyuctovanie sa vratilo zamestnancovi", "t_vyplnit" in t, list(t))
    tid2 = t.get("t_vyplnit")
    if tid2:
        pf.check("stav je zase 'rozpisane'",
                 pf.values(zam, tid2).get("pc_stav_label") == "rozpisane",
                 pf.values(zam, tid2).get("pc_stav_label"))
        pf.check("cesty sa vratenim nestratili",
                 int(float(pf.values(zam, tid2).get("pc_pocet_ciest") or 0)) == 3,
                 pf.values(zam, tid2).get("pc_pocet_ciest"))
        # Vratenim vznikla NOVA uloha a tá je nepriradena - `finish` bez
        # `assign` vrati "cannot be finished, because it is not assigned".
        pf.assign(zam, tid2)
        st, r = pf.finish(zam, tid2)
        pf.check("druhe podanie preslo", pf.ok_body(r), str(r)[:160])

    print("\n=== 9. tlacivo: nase hodnoty, cudzie vzorce ===")
    ts2 = pf.tasks_raw(boss, case_id).get("t_schvalit")
    pf.check("schvalovatel ma ulohu znova", bool(ts2))
    vsch = pf.values(schv, ts2) if ts2 else {}
    pf.check("export hlasi, kolko buniek a obrazkov zapisal",
             "could not" not in (vsch.get("pc_export_sprava") or "").lower()
             and "cells" in (vsch.get("pc_export_sprava") or ""),
             vsch.get("pc_export_sprava"))
    pf.check("vyplnene tlacivo je na case-e", bool(vsch.get("pc_vystup")),
             vsch.get("pc_vystup"))

    st, data = pf.download(schv, ts2, "pc_vystup") if ts2 else (0, b"")
    pf.check("tlacivo sa da stiahnut", st == 200 and len(data) > 1000, f"{st}, {len(data)} B")
    if st == 200 and len(data) > 1000:
        bunky, subory = citaj_xlsx(data)
        pf.check("v zosite je obrazok podpisu",
                 any(n.startswith("xl/media/") for n in subory),
                 [n for n in subory if "media" in n or "drawing" in n])
        pf.check("hlavicka: obdobie je v G4", (bunky.get("G4") or (None,))[0] == obdobie,
                 bunky.get("G4"))
        pf.check("hlavicka: SPZ je v M6", (bunky.get("M6") or (None,))[0] == "ZM396CV",
                 bunky.get("M6"))
        pf.check("prva cesta: datum je v A12", (bunky.get("A12") or (None,))[0] is not None,
                 bunky.get("A12"))
        pf.check("prva cesta: dopravny prostriedok je slovom, ktore tlacivo cita",
                 (bunky.get("F12") or (None,))[0] == "Súkromné vozidlo", bunky.get("F12"))
        pf.check("druha cesta je o DVA riadky nizsie (F14)",
                 (bunky.get("F14") or (None,))[0] == "Autobus", bunky.get("F14"))
        # Cislo, nie retazec: POI ho do XML zapise ako "70.0".
        cislo = lambda ref: float((bunky.get(ref) or ("nan",))[0] or "nan")
        pf.check("kilometre tam su v H12, spat v H13",
                 abs(cislo("H12") - 70) < 1e-6 and abs(cislo("H13") - 70) < 1e-6,
                 (bunky.get("H12"), bunky.get("H13")))
        # TOTO JE POINTA APPKY.
        pf.check("VZOREC SABLONY v I12 zostal vzorcom",
                 (bunky.get("I12") or (None, None))[1] is not None, bunky.get("I12"))
        pf.check("vzorec zostal aj na nepouzitom riadku (I70)",
                 (bunky.get("I70") or (None, None))[1] is not None, bunky.get("I70"))
        pf.check("cena PHM v K12 je NASA hodnota, nie vzorec",
                 (bunky.get("K12") or (None, None))[1] is None and
                 abs(float((bunky.get("K12") or ("0",))[0] or 0) - 1.6) < 1e-6,
                 bunky.get("K12"))

    print("\n=== 10. schvalenie a spracovanie ===")
    pf.set_data(schv, ts2, {"pc_rozhodnutie": {"type": "enumeration_map", "value": "schvalit"}})
    pf.upload(schv, ts2, "pc_podpis_schv", "podpis-s.png", pf.tiny_png(120, 40))
    st, r = pf.finish(schv, ts2)
    pf.check("schvalenie preslo", pf.ok_body(r), str(r)[:160])

    ulohy = pf.tasks_raw(boss, case_id)
    pf.check("vznikla uloha 't_spracovat'", "t_spracovat" in ulohy, list(ulohy))
    pf.check("zamestnanec ulohu uctarne NEVIDI",
             "t_spracovat" not in pf.tasks_of(zam, case_id), list(pf.tasks_of(zam, case_id)))
    tsp = pf.tasks_of(iny, case_id).get("t_spracovat")   # `druhy` ma rolu `mzdy`
    pf.check("mzdova uctaren ulohu vidi", bool(tsp), list(pf.tasks_of(iny, case_id)))
    if tsp:
        pf.set_data(iny, tsp, {"pc_poznamka_mzdy": {"type": "text", "value": "Paid with the July payroll."}})
        st, r = pf.finish(iny, tsp)
        pf.check("spracovanie preslo", pf.ok_body(r), str(r)[:160])

    tp = pf.tasks_of(zam, case_id).get("t_prehlad")
    pf.check("zamestnanec ma prehlad az po spracovani", bool(tp),
             list(pf.tasks_of(zam, case_id)))
    if tp:
        vp = pf.values(zam, tp)
        pf.check("stav je 'vybavene'", vp.get("pc_stav_label") == "vybavene",
                 vp.get("pc_stav_label"))
        pf.check("priebeh drzi vsetky kroky",
                 all(x in (vp.get("pc_historia") or "")
                     for x in ("submitted", "sent back", "approved", "processed")),
                 (vp.get("pc_historia") or "")[:200])
        # Komentar z VRATENIA sa nesmie objavit pri schvaleni - schvalovatel
        # ho druhykrat nenapisal a zaznam by tvrdil, ze ano.
        riadok_schvalenia = [r for r in (vp.get("pc_historia") or "").split("\n")
                             if "approved by" in r]
        pf.check("zaznam o schvaleni nenesie komentar z vratenia",
                 riadok_schvalenia and "Chyba ubytovanie" not in riadok_schvalenia[0],
                 riadok_schvalenia[:1])
        # Prazdny titulok udalosti tlacidlo SKRYJE (E3/B23) - to je jediny
        # sposob, ako ho z read-only pohladu dostat prec bez toho, aby sa
        # odobralo `view`. Preto sa overuje titulok, nie opravnenie.
        st, task = zam.get("/api/task/" + tp)
        pf.check("prehlad nema tlacidlo DOKONCIT",
                 (task or {}).get("finishTitle") in ("", None), (task or {}).get("finishTitle"))
        pf.check("prehlad nema tlacidlo ZRUSIT",
                 (task or {}).get("cancelTitle") in ("", None), (task or {}).get("cancelTitle"))

    print("\n=== 11. podpis sa nesie na dalsie vyuctovanie ===")
    case2, _ = pf.new_case(zam, net["stringId"])
    t2 = pf.tasks_of(zam, case2).get("t_vyplnit")
    pf.check("druhe vyuctovanie sa zalozilo", bool(t2))
    if t2:
        v2 = pf.values(zam, t2)
        pf.check("podpis sa preniesol z predchadzajuceho vyuctovania",
                 bool(v2.get("pc_podpis_zam")), v2.get("pc_podpis_zam"))

    print("\n=== 12. jeden clovek, jeden mesiac ===")
    if t2:
        pf.set_data(zam, t2, {"pc_rok": {"type": "number", "value": 2026},
                              "pc_mesiac": {"type": "enumeration_map", "value": "07"},
                              "pc_schvalovatel_vyber": {"type": "enumeration_map",
                                                        "value": schv_id}})
        pridaj_cestu(zam, t2, dict(datum="2026-07-20", od="09:00", do="17:00", minut=480,
                                   doprava="vlak", strava="nie", km_tam=0, km_spat=0,
                                   cena=0, ubytovanie=0, ine=22))
        st, r = pf.finish(zam, t2)
        pf.check("druhe vyuctovanie na to iste obdobie je odmietnute",
                 pf.err_body(r), str(r)[:180])

    return pf.report("cestycheck")


if __name__ == "__main__":
    sys.exit(main())
