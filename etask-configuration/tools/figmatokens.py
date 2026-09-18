#!/usr/bin/env python3
"""
figmatokens - z exportu Figma suboru spravi SCSS s tokenmi `--n-*`.

Netgrif Design System (Figma `DvZiv1wChuQM3Mpr4XjwHH`) NIE JE obrazkova
prezentacia - tokeny su v nom napisane rovno ako CSS premenne, v dvoch
vrstvach:

    --n-font-size-300: 14px                              primitivum
    --n-text-body-md-font-size: var(--n-font-size-325)   semanticka vrstva

Tento nastroj tie tabulky precita a prepise do SCSS. Nie je to preklad,
je to prepis - preto ma zmysel ho mat ako nastroj a nie ako rucne napisany
subor: ked dizajn ozije, prebehne to znova a rozdiel je vidno v git diffe.

    # 1. stiahnut subor (token si sprav v Figma -> Settings -> Security,
    #    staci scope `file_content:read`)
    curl -H "X-Figma-Token: $FIGMA_TOKEN" \
         "https://api.figma.com/v1/files/DvZiv1wChuQM3Mpr4XjwHH" \
         -o .run/figma-tokens.json

    # 2. prepisat
    python3 tools/figmatokens.py .run/figma-tokens.json \
        -o ../etask-frontend-starter/src/styles/_n-tokens.scss

    python3 tools/figmatokens.py .run/figma-tokens.json --tabulka   # len vypis

TRI VECI, KTORE V TOM SUBORE NESEDIA a preto su tu osetrene:

  1. HODNOTA JE O 16 px NIZSIE nez nazov tokenu, nie na tom istom riadku.
     Pri tolerancii "rovnaky riadok" vypadne kazdy piaty token a nic to
     nepovie - zoznam len ticho nema `font-size`.

  2. TABULKA `--n-space-*` SI ODPORUJE SAMA SO SEBOU: riadky 16, 20, 24 a 28
     maju v stlpci Value hodnoty 12, 16, 20 a 24 px, teda posunute o jeden
     riadok, a od 32 sa to zas zrovna. Beru sa NAZVY (16 = 16px): stupnica
     0-2-4-6-8-10-12-16-20-24-28-32 je suvisla, kdezto dvakrat 12px nie je,
     a graficke ukazky v lavom stlpci rastu monotonne. Je to preklep v DS,
     nie zamer - ale je to ich rozhodnutie, nie nase, takze `--kontrola`
     ten rozpor vypise.

  3. `--n-font-size-1000` hodnotu v tabulke nema vobec. Je to display
     velkost pre web, v aplikacii sa nepouzije, takze sa NEDOPLNA odhadom -
     radsej chyba.
"""

import argparse
import json
import re
import sys
from collections import OrderedDict

# Hodnota sedi v tom istom riadku tabulky, ale jej stred je nizsie nez stred
# nazvu. 20 px chyti aj ten posun (16 px), aj bezny riadok, a nedosiahne na
# susedny riadok (rozostup je ~48 px).
RIADOK_TOLERANCIA = 20


def texty(uzol, out=None):
    """Vsetky TEXT uzly podstromu ako {x, y stredu, text}."""
    if out is None:
        out = []
    if uzol.get("type") == "TEXT" and uzol.get("characters") and uzol.get("absoluteBoundingBox"):
        bb = uzol["absoluteBoundingBox"]
        out.append({"x": bb["x"], "y": bb["y"] + bb["height"] / 2,
                    "t": uzol["characters"].strip()})
    for dieta in (uzol.get("children") or []):
        texty(dieta, out)
    return out


def hex_farby(uzol):
    """Prvy viditelny SOLID fill ako #RRGGBB, s alfou ak nie je 1."""
    for f in (uzol.get("fills") or []):
        if f.get("type") != "SOLID" or not f.get("visible", True):
            continue
        c = f["color"]
        rgb = "#%02X%02X%02X" % tuple(round(c[k] * 255) for k in ("r", "g", "b"))
        alfa = f.get("opacity", c.get("a", 1))
        return rgb if alfa >= 0.999 else (rgb, alfa)
    return None


def stranka(dok, meno):
    for c in dok["document"]["children"]:
        if c.get("name") == meno:
            return c
    sys.exit(f"figmatokens: stranka '{meno}' v subore nie je")


def zbierz_tokeny(dt_stranka):
    """{nazov tokenu: hodnota} zo vsetkych tabuliek na stranke Design Tokens."""
    out = OrderedDict()
    rozpory = []
    for ramec in dt_stranka.get("children") or []:
        ts = texty(ramec)
        mena = [t for t in ts if t["t"].startswith("--n-")]
        for m in sorted(mena, key=lambda t: (t["y"], t["x"])):
            vpravo = sorted([t for t in ts
                             if abs(t["y"] - m["y"]) < RIADOK_TOLERANCIA and t["x"] > m["x"] + 5],
                            key=lambda t: t["x"])
            hodnota = vpravo[0]["t"] if vpravo else None
            if hodnota in ("—", "-", ""):
                hodnota = None
            if m["t"] in out and out[m["t"]] != hodnota:
                continue  # ta ista premenna ukazana viackrat (napr. v ukazke)
            out[m["t"]] = hodnota

    # Pasca c. 2: nazov vs. hodnota pri ciselnych stupniciach.
    for meno, hodnota in list(out.items()):
        m = re.match(r"--n-(space|border-radius)-(\d+)$", meno)
        if not m or not hodnota:
            continue
        podla_nazvu = m.group(2)
        podla_hodnoty = re.sub(r"[^\d]", "", hodnota)
        if podla_hodnoty and podla_hodnoty != podla_nazvu:
            rozpory.append((meno, hodnota, podla_nazvu + "px"))
        out[meno] = podla_nazvu + "px"
    return out, rozpory


# Standardny rebrik odtienov. Rampy v DS ho dodrziavaju - az na popisky,
# ktore mu obcas odporuju (viz `zbierz_ramp`).
REBRIK_11 = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"]
REBRIK_12 = ["0"] + REBRIK_11


def zbierz_ramp(paleta):
    """{nazov rampy: [(stupen, hex)]} z ramca Tokens / Color Palette.

    Vracia aj zoznam rozporov: pat ramp ma odtien 700 POPISANY ako 600, takze
    by z nich `-700` vypadol a `-600` by bol v CSS dvakrat (vyhral by ten
    druhy). Ked pocet vzoriek sedi s rebrikom, popisky sa nahradia nim.
    """
    out = OrderedDict()
    rozpory = []
    for skupina in paleta.get("children") or []:
        if not str(skupina.get("name", "")).startswith("Frame"):
            continue
        uzly = []

        def prejdi(n):
            uzly.append(n)
            for c in (n.get("children") or []):
                prejdi(c)
        prejdi(skupina)

        ts = [n for n in uzly if n.get("type") == "TEXT" and n.get("characters")]
        if not ts:
            continue
        nazov = ts[0]["characters"].strip()
        popisky = [t for t in ts[1:] if len(t["characters"].strip()) <= 5]
        vzorky = []
        for n in uzly:
            bb = n.get("absoluteBoundingBox") or {}
            if bb.get("width", 0) > 40 and bb.get("height", 0) > 40 and hex_farby(n):
                vzorky.append(n)
        if not vzorky:
            continue
        vzorky = sorted(vzorky, key=lambda n: n["absoluteBoundingBox"]["x"])
        # Prve tri vzorky su chrom karticky skupiny (biela, biela, tmava),
        # nie odtiene rampy.
        if len(vzorky) > 4:
            vzorky = vzorky[3:]
        popisky = sorted(popisky, key=lambda t: t["absoluteBoundingBox"]["x"])

        # Stupne sa NEPRIRADUJU podla najblizsieho popisku. Popisok stupna 700
        # je v tom subore posunuty tak, ze mu najblizsia vzorka je ta od 600,
        # takze rampa vysla ako 500-600-600-800 a odtien 700 z nej vypadol.
        # Ked je popiskov presne tolko co vzoriek, poradie zlava doprava je
        # jednoznacne a staci ich zipnut.
        if len(popisky) == len(vzorky):
            riadok = [(p["characters"].strip(), hex_farby(v))
                      for p, v in zip(popisky, vzorky)]
        else:
            riadok = []
            for v in vzorky:
                sx = v["absoluteBoundingBox"]["x"]
                blizky = min(popisky, key=lambda t: abs(t["absoluteBoundingBox"]["x"] - sx),
                             default=None)
                riadok.append((blizky["characters"].strip() if blizky else "?", hex_farby(v)))
        stupne = [st for st, _ in riadok]
        rebrik = {11: REBRIK_11, 12: REBRIK_12}.get(len(riadok))
        if rebrik and stupne != rebrik and len(set(stupne)) < len(stupne):
            for i, (st, oc) in enumerate(zip(stupne, rebrik)):
                if st != oc:
                    rozpory.append((f"{nazov} #{i + 1}", st, oc))
            riadok = [(oc, hx) for (st, hx), oc in zip(riadok, rebrik)]
        out[nazov] = riadok
    return out, rozpory


def ako_scss(tokeny, rampy):
    r = []
    r.append("// GENEROVANY SUBOR - needituj rucne.")
    r.append("//")
    r.append("// Prepis Netgrif Design System z Figmy (`Netgrif — Design System`).")
    r.append("// Prepisuje sa nastrojom, nie rukou:")
    r.append("//")
    r.append("//   cd etask-configuration")
    r.append("//   python3 tools/figmatokens.py .run/figma-tokens.json \\")
    r.append("//       -o ../etask-frontend-starter/src/styles/_n-tokens.scss")
    r.append("//")
    r.append("// Je to ZDROJOVA vrstva dizajnu, nie appkova. Nic tu nesmie zavisiet")
    r.append("// od eTasku - vdaka tomu sa tento subor da presunut do")
    r.append("// `@netgrif/components` bez zmeny. Appkove tokeny (`--app-*`) sa")
    r.append("// na tieto len mapuju, v `_tokens.scss`.")
    r.append("")
    r.append(":root {")

    def sekcia(nadpis, vzor):
        polozky = [(k, v) for k, v in tokeny.items() if re.match(vzor, k) and v]
        if not polozky:
            return
        r.append(f"  // {nadpis}")
        for k, v in polozky:
            r.append(f"  {k}: {v};")
        r.append("")

    r.append("  // --- Pismo -------------------------------------------------------")
    sekcia("Rodiny pisma", r"--n-font-family-")
    sekcia("Velkosti pisma (1000 v DS hodnotu nema)", r"--n-font-size-")
    sekcia("Vysky riadku", r"--n-font-line-height-")
    sekcia("Rezy", r"--n-font-weight-")
    sekcia("Prestrkanie", r"--n-font-letter-spacing-")
    sekcia("Odstupy", r"--n-space-")
    sekcia("Zaoblenia", r"--n-border-radius-")

    r.append("  // --- Farebne rampy -----------------------------------------------")
    r.append("  // Brand je vlastna; Neutral/Blue/Purple/Green/Orange/Red su")
    r.append("  // Tailwind gray/blue/violet/emerald/orange/rose. Alpha* su")
    r.append("  // prekryvove stupnice, hodnota je farba + priehladnost.")
    for nazov, riadok in rampy.items():
        kluc = nazov.lower().replace(" ", "-")
        r.append(f"  // {nazov}")
        for stupen, h in riadok:
            if isinstance(h, tuple):
                rgb, alfa = h
                rr, gg, bb = (int(rgb[i:i + 2], 16) for i in (1, 3, 5))
                r.append(f"  --n-color-{kluc}-{stupen}: rgba({rr}, {gg}, {bb}, {alfa:.2f});")
            else:
                r.append(f"  --n-color-{kluc}-{stupen}: {h};")
        r.append("")

    r.append("  // --- Semanticka vrstva -------------------------------------------")
    r.append("  // Odkazuje sa na primitiva vyssie - presne tak, ako je to")
    r.append("  // napisane v DS.")
    for k, v in tokeny.items():
        if k.startswith("--n-text-") and v:
            r.append(f"  {k}: {v};")
    r.append("}")
    r.append("")
    return "\n".join(r)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subor", help="JSON z /v1/files/:key")
    ap.add_argument("-o", "--out", help="kam zapisat SCSS (inak na stdout)")
    ap.add_argument("--tabulka", action="store_true", help="len vypisat nazov -> hodnota")
    ap.add_argument("--kontrola", action="store_true",
                    help="vypisat rozpory medzi nazvom a hodnotou a skoncit")
    a = ap.parse_args(argv)

    with open(a.subor, encoding="utf-8") as fh:
        dok = json.load(fh)

    dt = stranka(dok, "Design Tokens")
    tokeny, rozpory = zbierz_tokeny(dt)
    paleta = [f for f in dt["children"] if f.get("name") == "Tokens / Color Palette"]
    rampy, rozpory_ramp = zbierz_ramp(paleta[0]) if paleta else ({}, [])
    rozpory = rozpory + rozpory_ramp

    if a.kontrola:
        if not rozpory:
            print("figmatokens: nazvy a hodnoty tokenov sedia")
            return 0
        print(f"figmatokens: {len(rozpory)} miest si v DS odporuje (beriem nazov/rebrik):")
        for meno, v_dizajne, pouzite in rozpory:
            print(f"  {meno:28s} v DS: {str(v_dizajne):>8s}   pouzivam: {pouzite}")
        return 1

    if a.tabulka:
        for k, v in tokeny.items():
            print(f"  {k:46s} {v if v else '— (v DS chyba)'}")
        for nazov, riadok in rampy.items():
            print(f"\n  {nazov}: " + ", ".join(f"{s}={h if not isinstance(h, tuple) else h[0]}"
                                               for s, h in riadok))
        return 0

    scss = ako_scss(tokeny, rampy)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(scss)
        chyba = [k for k, v in tokeny.items() if not v]
        print(f"figmatokens: {a.out}")
        print(f"  {len([v for v in tokeny.values() if v])} tokenov, "
              f"{sum(len(r) for r in rampy.values())} odtienov v {len(rampy)} rampach")
        if chyba:
            print(f"  bez hodnoty v DS ({len(chyba)}): {', '.join(chyba)}")
        if rozpory:
            print(f"  nazov != hodnota ({len(rozpory)}), beriem nazov - `--kontrola` vypise ktore")
    else:
        print(scss)
    return 0


if __name__ == "__main__":
    sys.exit(main())
