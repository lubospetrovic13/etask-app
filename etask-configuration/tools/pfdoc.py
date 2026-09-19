#!/usr/bin/env python3
"""
pfdoc - citaj z dokumentacie KAPITOLU, nie cely subor.

PRECO TO EXISTUJE

Najvacsia jednotlivá polozka nákladu na jednu appku nie je pisanie kodu, ale
citanie dokumentacie. Merane na tomto repozitari:

    docs/ + reference/ + CLAUDE.md + skill   ~86 000 tokenov
    z toho RUNBOOK.md                        ~14 500
    z toho petriflow_reference.md            ~27 000

Agent (ani clovek) nema ako precitat "kapitolu 4", lebo nastroje citaju subory.
Otazka "ako pridam kartu do menu?" tak stoji 14 500 tokenov namiesto ~1 000 -
a to iste sa opakuje pri kazdej dalsej otazke v tom istom sedeni.

    python3 tools/pfdoc.py                    # co kde je, s cenou v tokenoch
    python3 tools/pfdoc.py runbook 4          # len kapitola 4
    python3 tools/pfdoc.py learnings B8       # sekcia podla prefixu
    python3 tools/pfdoc.py engine E20
    python3 tools/pfdoc.py hladaj "menu"      # kde o tom je - NADPISY, nie telo
    python3 tools/pfdoc.py --json            # zoznam kapitol s cenou, strojovo

`hladaj` zamerne nevypisuje najdene riadky s kontextom: vypise, v ktorej
kapitole to je, a tá sa potom da vytiahnut cela. Inak by sa grep vystupom
usetrene tokeny hned minuli spat.

Exit 0 = naslo sa, 1 = nenaslo, 2 = zle pouzitie.
"""

import io
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # etask-configuration
REPO = ROOT.parent
# Dokumentacia zije v roote repozitara, nie v etask-configuration:
# ten priecinok je prikazovy (siete, nastroje, manifesty).
DOCS = REPO / "docs"

# Skratka -> subor. Skratky su kratke zamerne: pisu sa castejsie nez nazvy.
DOKUMENTY = {
    "runbook": DOCS / "RUNBOOK.md",
    "learnings": DOCS / "PETRIFLOW_LEARNINGS.md",
    "engine": DOCS / "ENGINE_ISSUES.md",
    "frontend": DOCS / "FRONTEND_LEARNINGS.md",
    "backend": DOCS / "BACKEND.md",
    "sd": DOCS / "SERVICE_DESK.md",
    "onboarding": DOCS / "ONBOARDING.md",
    "prirucka": DOCS / "PRIRUCKA.md",
    "analyza": DOCS / "AI_STARTER_ANALYSIS.md",
    "tabulky": DOCS / "ANALYZA_TABULKY.md",
    "petriflow": DOCS / "petriflow_reference.md",
    "cheatsheet": DOCS / "reference" / "cheatsheet.md",
    "api": DOCS / "reference" / "action-api.md",
    "claude": REPO / "CLAUDE.md",
    "skill": REPO / ".claude" / "skills" / "petriflow" / "SKILL.md",
}


def tokeny(text):
    """Hruby odhad. Presny tokenizer tu nie je a netreba ho - ide o rad velkosti."""
    return len(text) // 4


def kapitoly(text):
    """[(uroven, nadpis, zaciatok, koniec)] pre `##` a `###`.

    Kapitola konci az pred dalsim nadpisom ROVNAKEJ alebo vyssej urovne, takze
    `## 4.` obsahuje aj svoje `###` podkapitoly - to je to, co clovek chce, ked
    pyta "kapitolu 4".
    """
    riadky = text.split("\n")
    najdene = []
    v_kode = False
    for i, r in enumerate(riadky):
        if r.startswith("```"):
            v_kode = not v_kode
        if v_kode:
            continue
        m = re.match(r"^(#{2,3}) +(.*)", r)
        if m:
            najdene.append((len(m.group(1)), m.group(2).strip(), i))
    out = []
    for idx, (uroven, nadpis, zac) in enumerate(najdene):
        kon = len(riadky)
        for uroven2, _, zac2 in najdene[idx + 1:]:
            if uroven2 <= uroven:
                kon = zac2
                break
        out.append((uroven, nadpis, zac, kon))
    return out


def kluc_kapitoly(nadpis):
    """`4. Karta a priečinok` -> '4';  `B8b. Read arc` -> 'b8b';  `E20. Redis` -> 'e20'."""
    m = re.match(r"^([A-Za-z]?\d+[a-z]?)[.)]?\s", nadpis + " ")
    return m.group(1).lower() if m else None


def prehlad():
    print("pfdoc - kapitola miesto celeho suboru\n")
    print(f"{'skratka':12} {'subor':34} {'~tokenov':>9}  kapitol")
    spolu = 0
    for skratka, cesta in DOKUMENTY.items():
        if not cesta.is_file():
            print(f"{skratka:12} {'(chyba)':34}")
            continue
        text = io.open(cesta, encoding="utf-8", errors="replace").read()
        t = tokeny(text)
        spolu += t
        hlavne = [k for k in kapitoly(text) if k[0] == 2]
        print(f"{skratka:12} {cesta.name:34} {t:9}  {len(hlavne)}")
    print(f"\nvsetko dokopy: ~{spolu} tokenov. Preto sa cita po kapitolach:")
    print("  python3 tools/pfdoc.py runbook 4")
    print("  python3 tools/pfdoc.py hladaj \"menu\"")
    print("\nCo v ktorom dokumente je:")
    print("  cheatsheet  jedna strana: postup a osem rozhodnuti  (citaj cely)")
    print("  runbook     recepty na bezne ulohy, cislovane kapitoly")
    print("  learnings   Petriflow pasce, znackovane B1..Bn, C1..Cn")
    print("  engine      chyby enginu, znackovane E1..En")
    print("  frontend    Angular/tema pasce, A1..An, B1..Bn")
    print("  api         generovany inventar volatelnych metod (hladaj v nom)")
    print("  petriflow   jazykova referencia - NIKDY necitaj cela, len hladaj")
    return 0


def vypis(skratka, kluc):
    cesta = DOKUMENTY.get(skratka)
    if cesta is None:
        print(f"pfdoc: neznamy dokument '{skratka}'. Zname: {', '.join(DOKUMENTY)}",
              file=sys.stderr)
        return 2
    if not cesta.is_file():
        print(f"pfdoc: {cesta} neexistuje", file=sys.stderr)
        return 1
    text = io.open(cesta, encoding="utf-8", errors="replace").read()
    riadky = text.split("\n")
    hladane = kluc.lower().rstrip(".")

    trafene = []
    for uroven, nadpis, zac, kon in kapitoly(text):
        k = kluc_kapitoly(nadpis)
        if k == hladane or nadpis.lower().startswith(hladane):
            trafene.append((uroven, nadpis, zac, kon))
    if not trafene:
        # bez kapitoly: vypis zoznam, nech je z coho vyberat
        print(f"pfdoc: v {cesta.name} som kapitolu '{kluc}' nenasiel. Su tam:",
              file=sys.stderr)
        for uroven, nadpis, zac, _ in kapitoly(text):
            if uroven == 2:
                print(f"  {nadpis}", file=sys.stderr)
        return 1

    # najvseobecnejsia trefa staci - `runbook 4` ma dat kapitolu, nie podkapitolu
    uroven, nadpis, zac, kon = sorted(trafene, key=lambda x: (x[0], x[2]))[0]
    telo = "\n".join(riadky[zac:kon]).rstrip()
    print(f"<!-- {cesta.relative_to(REPO)} : riadky {zac + 1}-{kon}, "
          f"~{tokeny(telo)} tokenov (cely subor ~{tokeny(text)}) -->\n")
    print(telo)
    return 0


def bez_diakritiky(text):
    rozlozene = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in rozlozene if not unicodedata.combining(ch))


def hladaj(vyraz):
    """Kde o tom je. Vypisuje NADPISY kapitol, nie riadky - telo si vypytas zvlast.

    Hlada sa BEZ DIAKRITIKY a po slovach: dokumentacia je po slovensky, takze
    `polozka menu` musi najst `položka menu`. Inak by nastroj odpovedal
    "nie je to tu" na vec, ktora tam je - a to je horsie nez ziadny nastroj.
    """
    slova = [bez_diakritiky(w) for w in vyraz.split() if w]
    najdene = 0
    for skratka, cesta in DOKUMENTY.items():
        if not cesta.is_file():
            continue
        text = io.open(cesta, encoding="utf-8", errors="replace").read()
        riadky = text.split("\n")
        for uroven, nadpis, zac, kon in kapitoly(text):
            telo = "\n".join(riadky[zac:kon])
            plocho = bez_diakritiky(telo)
            if not all(w in plocho for w in slova):
                continue
            pocet = min(plocho.count(w) for w in slova)
            # podkapitolu hlas len ked jej rodic nie je uz v zozname
            k = kluc_kapitoly(nadpis)
            prikaz = f"pfdoc.py {skratka} {k}" if k else f"pfdoc.py {skratka} \"{nadpis[:28]}\""
            print(f"{pocet:3}x  {nadpis[:52]:52}  ~{tokeny(telo):5}t  {prikaz}")
            najdene += 1
    if not najdene:
        print(f"pfdoc: '{vyraz}' v dokumentacii nie je. Skus `grep -rn` cez processes/.")
        return 1
    return 0


def json_prehlad():
    """Strojovy zoznam kapitol s cenou - aby si agent vedel naplanovat citanie
    dopredu namiesto toho, aby nacital subor a az potom zistil, co v nom je."""
    import json
    out = {}
    for skratka, cesta in DOKUMENTY.items():
        if not cesta.is_file():
            continue
        text = io.open(cesta, encoding="utf-8", errors="replace").read()
        riadky = text.split("\n")
        out[skratka] = {
            "subor": str(cesta.relative_to(REPO)).replace("\\", "/"),
            "tokenov": tokeny(text),
            "kapitoly": [
                {"kluc": kluc_kapitoly(nadpis), "nadpis": nadpis,
                 "tokenov": tokeny("\n".join(riadky[zac:kon]))}
                for uroven, nadpis, zac, kon in kapitoly(text) if uroven == 2
            ],
        }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main(argv):
    if argv and argv[0] in ("--json", "json"):
        return json_prehlad()
    if not argv:
        return prehlad()
    if argv[0] in ("hladaj", "find", "search"):
        if len(argv) < 2:
            print("pfdoc: hladaj potrebuje vyraz", file=sys.stderr)
            return 2
        return hladaj(" ".join(argv[1:]))
    if len(argv) == 1:
        return vypis(argv[0], "")  # vypise zoznam kapitol daneho dokumentu
    return vypis(argv[0], argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
