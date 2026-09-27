#!/usr/bin/env python3
"""
pffix - aplikuje opravy, ktore ma `pflint` jednoznacne.

PRECO SAMOSTATNY NASTROJ A NIE `pflint --fix`

`pflint` je kontrola: nic nemeni a da sa mu veriť. Nastroj, ktory aj kontroluje
aj prepisuje, sa raz spusti omylom - a prepis siete sa neprejaví ako chyba,
ale ako iná appka. Delenie je zámerné: `pflint` povie, `pffix` spraví, a obe
sa daju spustit zvlast.

CO OPRAVUJE

Len to, co ma **jednoznacnu** opravu. Ked je viac moznosti, patri to cloveku
(alebo modelu) - `pffix` to necha `pflint`u.

  grid-overlap      dva prvky sa v gride prekryvaju -> posunie nizsie polozene
                    o vysku prekryvu. Toto je najdrahsia z tichych chyb: Angular
                    ulohu NEVYKRESLI, zostane spinner a chyba je len v konzole.
  type-textarea     `<data type="textarea">` -> `type="text"` plus
                    `<component><name>textarea</name></component>`. `textarea`
                    nie je typ, je to komponent; engine pole s tym typom prijme
                    a frontend ho nevykresli.
  button-reads-text textove pole, ktore cita tlacidlo v tom istom dataGroup,
                    dostane `immediate="true"` - blur a klik su jedna
                    poziadavka, takze akcia inak precita hodnotu spred pisania.

CO NEOPRAVUJE A PRECO

  unsafe-nav-property  `u?._id` sa nahradza `userIdsOf(...)`, ale ako presne
                       zavisi od kontextu akcie.
  findcase-stringid    oprava vyzaduje ObjectId a istotu, ze premenna je id.
  option-key-mongo     kluc sa pouziva aj inde v sieti a v datach.
  data-unused          nastroj nevie, ci je pole mrtve alebo ho plni ina siet.

POUZITIE

    python3 tools/pffix.py processes/            # ukaze, co by spravil
    python3 tools/pffix.py processes/ --write    # zapise
    python3 tools/pflint.py processes/           # a potom skontroluj

Exit 0 = hotovo (aj ked nebolo co opravit), 1 = nieco sa nepodarilo, 2 = zle pouzitie.
"""

import io
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def nacitaj(cesta):
    return io.open(cesta, encoding="utf-8", errors="replace").read()


def direct(el, name):
    return [c for c in el if c.tag == name]


def text_of(el, name):
    c = el.find(name)
    return (c.text or "").strip() if c is not None and c.text else ""


# ---------------------------------------------------------------- grid

def oprav_grid(raw):
    """Posunie prvky tak, aby sa v gride neprekryvali.

    Postup je zámerne hlúpy a predvídateľný: ide po prvkoch v poradí, v akom
    su v XML, a ked by novy prvok kolidoval s uz polozenym, posunie ho (a vsetko
    s rovnakym alebo vacsim `y` v tej istej skupine) nadol o tolko, aby kolizia
    zmizla. Ziadne prepakovanie - clovek ma po oprave spoznat svoj formular.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return raw, []

    zmeny = []
    novy = raw
    for trans in root.iter("transition"):
        for group in direct(trans, "dataGroup"):
            gid = text_of(group, "id")
            obsadene = {}
            posuny = {}          # fid -> o kolko sa posunul
            for ref in direct(group, "dataRef"):
                fid = text_of(ref, "id")
                layout = ref.find("layout")
                if layout is None or not fid:
                    continue
                try:
                    x = int(text_of(layout, "x") or 0)
                    y = int(text_of(layout, "y") or 0)
                    rows = max(int(text_of(layout, "rows") or 1), 1)
                    cols = max(int(text_of(layout, "cols") or 1), 1)
                except ValueError:
                    continue

                posun = 0
                while True:
                    kolizia = False
                    for yy in range(y + posun, y + posun + rows):
                        for xx in range(x, x + cols):
                            if obsadene.get((yy, xx), fid) != fid:
                                kolizia = True
                                break
                        if kolizia:
                            break
                    if not kolizia:
                        break
                    posun += 1
                    if posun > 200:          # poistka proti nekonecnu
                        return novy, zmeny

                if posun:
                    posuny[fid] = posun
                    zmeny.append((gid, fid, y, y + posun))
                for yy in range(y + posun, y + posun + rows):
                    for xx in range(x, x + cols):
                        obsadene[(yy, xx)] = fid

            # zapis posunov do textu - po jednom dataRefe, aby sa netrafil cudzi
            for fid, posun in posuny.items():
                novy = posun_dataref(novy, gid, fid, posun)
    return novy, zmeny


def posun_dataref(raw, gid, fid, posun):
    """Zvysi `<y>` v tom `<dataRef>`, ktory ma dane `<id>` v danej skupine."""
    zac_skupiny = raw.find(f"<id>{gid}</id>")
    if zac_skupiny < 0:
        return raw
    zac = raw.find(f"<id>{fid}</id>", zac_skupiny)
    if zac < 0:
        return raw
    koniec = raw.find("</dataRef>", zac)
    if koniec < 0:
        return raw
    usek = raw[zac:koniec]
    m = re.search(r"<y>(\d+)</y>", usek)
    if not m:
        return raw
    novy_usek = usek[:m.start()] + f"<y>{int(m.group(1)) + posun}</y>" + usek[m.end():]
    return raw[:zac] + novy_usek + raw[koniec:]


# ------------------------------------------------------------ textarea

def oprav_textarea(raw):
    """`<data type="textarea">` -> text + komponent."""
    zmeny = []
    out = raw
    for m in list(re.finditer(r'<data type="textarea"([^>]*)>(.*?)</data>', raw, re.S)):
        cely = m.group(0)
        fid = ""
        mid = re.search(r"<id>([^<]+)</id>", m.group(2))
        if mid:
            fid = mid.group(1)
        if "<component>" in m.group(2):
            novy = cely.replace('<data type="textarea"', '<data type="text"', 1)
        else:
            odsadenie = "\t\t"
            komponent = (f"{odsadenie}<component>\n{odsadenie}\t<name>textarea</name>\n"
                         f"{odsadenie}</component>\n")
            novy = (cely.replace('<data type="textarea"', '<data type="text"', 1)
                    .replace("</data>", komponent + "\t</data>", 1))
        out = out.replace(cely, novy, 1)
        zmeny.append(fid or "?")
    return out, zmeny


# --------------------------------------------------------- immediate

def oprav_immediate(raw, polia):
    """Doplni `immediate="true"` textovym poliam, ktore cita tlacidlo."""
    zmeny = []
    out = raw
    for fid in polia:
        m = re.search(r'<data type="text"((?:(?!immediate)[^>])*)>\s*<id>'
                      + re.escape(fid) + r'</id>', out)
        if not m:
            continue
        stary = m.group(0)
        novy = stary.replace('<data type="text"', '<data type="text" immediate="true"', 1)
        out = out.replace(stary, novy, 1)
        zmeny.append(fid)
    return out, zmeny


def polia_citane_tlacidlom(raw):
    """Id textovych poli, ktore cita akcia tlacidla v tom istom dataGroup.

    Pouziva to iste pravidlo ako `pflint` (button-reads-text), len vracia
    zoznam poli namiesto nalezov. Zamerne konzervativne: ked sa siet neda
    rozparsovat, vrati prazdno.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    typy, immediate = {}, {}
    for d in direct(root, "data"):
        fid = text_of(d, "id")
        if fid:
            typy[fid] = d.get("type")
            immediate[fid] = d.get("immediate") == "true"

    out = []
    for trans in root.iter("transition"):
        for group in direct(trans, "dataGroup"):
            v_skupine = {text_of(r, "id") for r in direct(group, "dataRef")}
            editovatelne = set()
            for r in direct(group, "dataRef"):
                logic = r.find("logic")
                if logic is not None and any(
                        (b.text or "").strip() == "editable" for b in logic.iter("behavior")):
                    editovatelne.add(text_of(r, "id"))
            for r in direct(group, "dataRef"):
                fid = text_of(r, "id")
                if typy.get(fid) != "button":
                    continue
                for d in direct(root, "data"):
                    if text_of(d, "id") != fid:
                        continue
                    for act in d.iter("action"):
                        for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\.value\b",
                                             act.text or ""):
                            ref = m.group(1)
                            if (typy.get(ref) == "text" and ref in v_skupine
                                    and ref in editovatelne and not immediate.get(ref)):
                                out.append(ref)
    return sorted(set(out))


# ------------------------------------------------------------------- main

def spracuj(cesta, zapis):
    raw = nacitaj(cesta)
    povodne = raw
    hlasenia = []

    raw, zmeny = oprav_textarea(raw)
    for fid in zmeny:
        hlasenia.append(f"type-textarea: '{fid}' je teraz text + komponent textarea")

    raw, zmeny = oprav_grid(raw)
    for gid, fid, stary_y, novy_y in zmeny:
        hlasenia.append(f"grid-overlap: '{fid}' v '{gid}' posunuty z y={stary_y} na y={novy_y}")

    polia = polia_citane_tlacidlom(raw)
    raw, zmeny = oprav_immediate(raw, polia)
    for fid in zmeny:
        hlasenia.append(f"button-reads-text: '{fid}' dostal immediate=\"true\"")

    if raw != povodne and zapis:
        io.open(cesta, "w", encoding="utf-8", newline="\n").write(raw)
    return hlasenia, raw != povodne


def main(argv):
    zapis = "--write" in argv
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__.strip())
        return 2

    subory = []
    for a in args:
        p = Path(a)
        if not p.is_absolute():
            p = ROOT / a
        if p.is_dir():
            subory.extend(sorted(p.glob("*.xml")))
        elif p.is_file():
            subory.append(p)
        else:
            print(f"pffix: {a} neexistuje", file=sys.stderr)
            return 2

    zmenene = 0
    for cesta in subory:
        hlasenia, zmena = spracuj(cesta, zapis)
        if hlasenia:
            print(f"{cesta.relative_to(ROOT) if ROOT in cesta.parents else cesta}:")
            for h in hlasenia:
                print(f"  {'~' if zapis else 'navrhujem'} {h}")
        if zmena:
            zmenene += 1

    if not zmenene:
        print("pffix: nic na opravu")
        return 0
    if zapis:
        print(f"\npffix: upravenych {zmenene} sieti. Skontroluj:")
        print("  python3 tools/pflint.py processes/")
        print("  python3 tools/pfgroovy.py processes/")
        print("  python3 tools/pfsync.py --sync")
    else:
        print(f"\npffix: {zmenene} sieti by sa zmenilo. Zapis: --write")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
