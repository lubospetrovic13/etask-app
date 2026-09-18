#!/usr/bin/env python3
"""
pflang - slovenske retazce BEZ PREKLADU v Petriflow akciach.

Default jazyk aplikacie je anglictina (`DEFAULT_LANGUAGE` v `app.component.ts`).
Slovencina je preklad. Titulky, popisy, moznosti `enumeration_map` a nazvy
zobrazeni preklad MAJU - ich slovensky default je v poriadku, engine ho
vymeni podla locale.

Preklad NEMAJU:
  * hodnoty datovych poli zapisane akciou  (`change pole value { "..." }`)
  * nazvy pripadov                          (`Case.title` je String, nie I18nString)
  * chybove hlasky z `throw`
  * riadky priebehu a logov

Slovenska veta medzi nimi sa v anglickom formulari neprejavi ako chyba - len
tam trci. Engine o tom mlci, `pflint` tiez: syntakticky je to platny retazec.
Preto tento nastroj.

Co sa NEHLASI (a preco):
  * `i18n("Slovensky", ["en": "English"])` - to preklad ma,
  * komentare v akciach - tie cita clovek, nie pouzivatel,
  * bloky `<i18n locale="...">` - to su prave tie preklady,
  * riadky medzi `// pflang:off` a `// pflang:on`.

To posledne je vynimka pre jediny pripad, ktory nie je chyba: retazec, ktory
NECITA CLOVEK, ale CUDZI SYSTEM, a ten cudzi system je slovensky. Tak vznikla:
`hr/cesty/pc_vyuctovanie` zapisuje do xlsx tlaciva hodnoty ako "Sukromne
vozidlo", lebo vzorec v harku porovnava stlpec presne na to slovo. Preklad do
anglictiny by tlacivo ticho rozbil - vzorec by prestal davat nahradu za km
a nikde by sa nic neohlasilo.

Vynimka teda NIE JE "tu sa mi to nechce prekladat", ale "toto nie je text
appky". Ked pri nej nie je veta, ktora povie, ktory cudzi system ten retazec
cita, patri tam preklad a nie marker.

    python3 tools/pflang.py                 # VSETKY siete instancie
    python3 tools/pflang.py processes/
    python3 tools/pflang.py processes/fa_faktura.xml

Bez argumentu kontroluje `processes/` AJ `etask-backend-starter/src/main/
resources/petriNets/`. Ta druha cesta je dolezita: `configuration_tiles`
(katalog) zije tam, nie v `processes/`, lebo `NetRunner` ju cita z classpathu.
Prve kolo prekladu ju preto obislo a slovensky nazov katalogu prezil - najiel
sa az pohladom do databazy po `--fresh`.

Exit 0 = ziadny nepreloženy retazec, 1 = nieco zostalo.
"""

import io
import os
import re
import sys

SK_ZNAKY = set("áäčďéíĺľňóôŕšťúýžÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ")

# `i18n(...)` s mapou prekladov - to je prelozene, nezaujima nas.
I18N_VOLANIE = re.compile(r'i18n\(\s*"[^"]*"\s*,\s*\[[^\]]*\]\s*\)', re.S)
KOMENTAR = re.compile(r'//[^\n]*')
CDATA = re.compile(r'<!\[CDATA\[(.*?)\]\]>', re.S)
RETAZEC = re.compile(r'"([^"\n]{2,})"')


def slovenske(text):
    return any(ch in SK_ZNAKY for ch in text)


def prehliadni(cesta):
    """Vrati [(riadok, retazec)] slovenskych literalov bez prekladu."""
    try:
        s = io.open(cesta, encoding="utf-8").read()
    except OSError as e:
        print(f"pflang: {cesta} sa neda precitat ({e})")
        return []

    nalezy = []
    videne = set()
    for m in CDATA.finditer(s):
        telo = m.group(1)
        prvy_riadok = s[:m.start()].count("\n") + 1
        # `i18n(...)` sa odstranuje nad CELYM blokom - vie byt viacriadkove
        # a po riadkoch by ho regex nechytil. Nahrada drzi rovnaky pocet
        # riadkov, aby sedeli cisla v hlaseni.
        telo = I18N_VOLANIE.sub(
            lambda mm: '"I18N"' + "\n" * mm.group(0).count("\n"), telo)
        # Markery sa hladaju PRED odstranenim komentarov - su to komentare.
        # Stav sa resetuje na kazdom bloku CDATA, takze zabudnute `pflang:on`
        # neumlci zvysok siete.
        vypnute = False
        for i, riadok in enumerate(telo.split("\n")):
            if "pflang:off" in riadok:
                vypnute = True
            if "pflang:on" in riadok:
                vypnute = False
                continue
            if vypnute:
                continue
            ocisteny = KOMENTAR.sub("", riadok)
            for lm in RETAZEC.finditer(ocisteny):
                lit = lm.group(1)
                if not slovenske(lit) or lit in videne:
                    continue
                videne.add(lit)
                nalezy.append((prvy_riadok + i, lit))
    return nalezy


# Siete instancie nie su len `processes/`. `configuration_tiles` zije
# v resources backendu, lebo `NetRunner` ju berie z classpathu - a prave preto
# na nu prvy prechod prekladom zabudol.
VSETKY_CESTY = [
    "processes/",
    os.path.join("..", "etask-backend-starter", "src", "main", "resources", "petriNets"),
]


def main(argv):
    ciele = argv or [c for c in VSETKY_CESTY if os.path.isdir(c)]
    subory = []
    for c in ciele:
        if os.path.isdir(c):
            subory.extend(sorted(os.path.join(c, n) for n in os.listdir(c)
                                 if n.endswith(".xml")))
        else:
            subory.append(c)

    spolu = 0
    for cesta in subory:
        nalezy = prehliadni(cesta)
        if not nalezy:
            continue
        spolu += len(nalezy)
        print(f"\n{cesta}")
        for riadok, lit in nalezy:
            skratene = lit if len(lit) <= 76 else lit[:73] + "..."
            print(f"  {riadok:>5}  {skratene}")

    print(f"\npflang: {len(subory)} sieti, {spolu} slovenskych retazcov bez prekladu")
    if spolu:
        print("        Hodnoty poli, nazvy pripadov a hlasky preklad NEMAJU -")
        print("        v anglickom formulari trcia. Prepis ich do anglictiny.")
    return 1 if spolu else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
