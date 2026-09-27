#!/usr/bin/env python3
"""
pfloop - slucka validuj -> oprav -> over, a co sa opravit neda, priprav modelu.

PRECO

Vzor "generuj XML, zvaliduj ho, oprav a zvaliduj znova" je starsi nez tento
repozitar. Zmenil sa validator: dnes to nie je len schema XML, ale aj syntax
akcii, preklady, render vo frontende a nakoniec import do bezuceho enginu.
`pfloop` ten cyklus spaja do jedneho prikazu a hlavne: **oddeluje tri triedy
nalezov**, lebo kazda patri niekomu inemu.

  1. mechanicke     ma jednoznacnu opravu -> aplikuje `pffix` a overi znova
  2. podla hlasenia model vie navrhnut patch, ked dostane chybu AJ prislusnu
                    kapitolu dokumentacie -> `pfloop` mu to napise do zadania
  3. navrhove       "stav patri do enumeration_map", "pohlad ma visiet na
                    mieste, ktore nikto nekonzumuje" - tu automat nezlyha
                    hlucne, zlyha tak, ze appka VYZERA hotovo. Ostava cloveku.

Zadanie pre model sa **nespusta** automaticky. Vystupom je subor, ktory sa da
podat modelu (alebo precitat cloveku) - a je zamerne maly: chyba, kapitola,
a vyrez siete, nie cela dokumentacia.

POUZITIE

    python3 tools/pfloop.py                    # processes/, bez enginu
    python3 tools/pfloop.py --fix              # aj aplikuje mechanicke opravy
    python3 tools/pfloop.py --engine           # aj import do beziaceho enginu
    python3 tools/pfloop.py processes/x.xml --fix

Exit 0 = cisto, 1 = nieco zostalo (zadanie je v .run/pfloop-zadanie.md).
"""

import io
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
PY = sys.executable or "python3"

# Pravidla, ktore `pffix` vie opravit sam.
MECHANICKE = {"grid-overlap", "type-textarea", "button-reads-text"}

# Pravidlo -> kapitola dokumentacie, ktora o tom hovori. Toto je to, co robi
# zadanie pre model pouzitelnym: chyba bez kontextu vedie k opravam, ktore
# odstrania hlasenie a nie pricinu.
KAPITOLY = {
    "unknown-call": ("api", None),
    "unknown-call-typo": ("api", None),
    "unsafe-nav-property": ("learnings", "B1"),
    "findcase-stringid": ("learnings", "B13"),
    "async-swallows": ("learnings", "B10"),
    "role-undeclared": ("runbook", "7"),
    "userref-undeclared": ("runbook", "7"),
    "userref-type": ("runbook", "11"),
    "menu-uri-unknown": ("runbook", "4"),
    "option-key-mongo": ("learnings", "B26"),
    "mongo-map-key": ("learnings", "B26"),
    "type-textarea": ("runbook", "6"),
    "grid-overlap": ("runbook", "6"),
    "button-reads-text": ("runbook", "6"),
    "setdata-unknown-transition": ("learnings", "C4"),
    "engine-remove-role": ("runbook", "7"),
}


def spusti(args):
    p = subprocess.run([PY] + args, cwd=str(ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=600)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def nalezy_pflint(cesta):
    kod, out = spusti(["tools/pflint.py", cesta])
    nalezy, posledny = [], None
    for r in out.splitlines():
        if r.startswith("    → ") and posledny:
            posledny["oprava"] = r[6:].strip()
            continue
        m = re.match(r"^(.*?):(\d+): (ERROR|WARNING|INFO) \[([a-z0-9-]+)\] (.*)$", r)
        if m:
            posledny = {"subor": m.group(1), "riadok": int(m.group(2)),
                        "uroven": m.group(3).lower(), "pravidlo": m.group(4),
                        "sprava": m.group(5), "oprava": ""}
            nalezy.append(posledny)
    return nalezy, out.strip().splitlines()[-1] if out.strip() else ""


def vyrez(subor, riadok, okolo=12):
    cesta = Path(subor)
    if not cesta.is_absolute():
        cesta = ROOT / subor
    if not cesta.is_file():
        return ""
    riadky = io.open(cesta, encoding="utf-8", errors="replace").read().splitlines()
    od = max(0, riadok - okolo)
    do = min(len(riadky), riadok + okolo)
    return "\n".join(f"{i + 1:5}  {riadky[i]}" for i in range(od, do))


def kapitola_textu(pravidlo):
    cielenie = KAPITOLY.get(pravidlo)
    if not cielenie:
        return ""
    dokument, kap = cielenie
    if kap is None:
        return ""
    kod, out = spusti(["tools/pfdoc.py", dokument, kap])
    return out if kod == 0 else ""


def zadanie(nalezy, cesta_zadania):
    """Maly, presny podklad pre model - nie cela dokumentacia."""
    von = ["# Zadanie: nalezy, ktore `pffix` opravit nevie",
           "",
           "Kazdy blok je jeden nalez: co hlasi kontrola, vyrez siete a kapitola,",
           "ktora o tom hovori. Oprav pricinu, nie hlasenie.",
           ""]
    videne_kapitoly = set()
    for n in nalezy:
        von.append(f"## {n['subor']}:{n['riadok']}  [{n['pravidlo']}]")
        von.append("")
        von.append(f"**{n['sprava']}**")
        if n.get("oprava"):
            von.append("")
            von.append(f"> {n['oprava']}")
        von.append("")
        v = vyrez(n["subor"], n["riadok"])
        if v:
            von.append("```xml")
            von.append(v)
            von.append("```")
            von.append("")
        kap = KAPITOLY.get(n["pravidlo"])
        if kap and kap not in videne_kapitoly:
            text = kapitola_textu(n["pravidlo"])
            if text:
                von.append(f"<details><summary>kapitola dokumentacie k `{n['pravidlo']}`</summary>")
                von.append("")
                von.append(text)
                von.append("")
                von.append("</details>")
                von.append("")
            videne_kapitoly.add(kap)
    cesta_zadania.parent.mkdir(parents=True, exist_ok=True)
    io.open(cesta_zadania, "w", encoding="utf-8", newline="\n").write("\n".join(von))


def main(argv):
    fix = "--fix" in argv
    engine = "--engine" in argv
    args = [a for a in argv if not a.startswith("--")]
    cesta = args[0] if args else "processes/"

    print("== 1. pflint")
    nalezy, sumar = nalezy_pflint(cesta)
    print("  " + sumar)

    mechanicke = [n for n in nalezy if n["pravidlo"] in MECHANICKE]
    if mechanicke:
        print(f"\n== 2. mechanicke nalezy: {len(mechanicke)}")
        prikaz = ["tools/pffix.py", cesta] + (["--write"] if fix else [])
        kod, out = spusti(prikaz)
        for r in out.splitlines():
            if r.strip():
                print("  " + r)
        if fix:
            print("\n== 3. pflint znova")
            nalezy, sumar = nalezy_pflint(cesta)
            print("  " + sumar)
        else:
            print("  (spusti s --fix, aby sa to aj zapisalo)")
    else:
        print("\n== 2. mechanicke nalezy: ziadne")

    print("\n== 4. zvysok retaze")
    for nazov, prikaz in (("pfgroovy", ["tools/pfgroovy.py", cesta]),
                          ("pfi18n", ["tools/pfi18n.py", cesta, "--ignore", "single_settings.xml"]),
                          ("pfview", ["tools/pfview.py"])):
        kod, out = spusti(prikaz)
        posledny = out.strip().splitlines()[-1] if out.strip() else "(bez vystupu)"
        print(f"  {'OK ' if kod == 0 else 'ZLE'} {nazov}: {posledny}")

    if engine:
        print("\n== 5. engine (ground truth)")
        kod, out = spusti(["tools/pfsync.py", "--sync"])
        for r in out.splitlines()[-3:]:
            print("  " + r)

    zostava = [n for n in nalezy if n["uroven"] in ("error", "warning")
               and not (fix and n["pravidlo"] in MECHANICKE)]
    cesta_zadania = REPO / ".run" / "pfloop-zadanie.md"
    if zostava:
        zadanie(zostava, cesta_zadania)
        print(f"\npfloop: {len(zostava)} nalezov zostava - zadanie pre model je v "
              f"{cesta_zadania.relative_to(REPO)}")
        print("  (chyba + vyrez siete + prislusna kapitola; spusti sa rucne, zamerne)")
        return 1

    print("\npfloop: cisto" + (" (po oprave)" if fix and mechanicke else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
