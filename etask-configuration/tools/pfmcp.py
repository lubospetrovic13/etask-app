#!/usr/bin/env python3
"""
pfmcp - MCP server nad nastrojmi tohto repozitara.

PRECO

Nastroje su dnes CLI skripty: agent ich spusti cez shell a vystup si precita ako
text. Funguje to, ale:

  * agent musi VEDIET, ze nastroj existuje - a to znamena drzat jeho meno
    v `CLAUDE.md`, ktory sa nacitava vzdy, teda sa plati aj vtedy, ked sa
    nastroj nepouzije,
  * vystup je text pre cloveka, ktory agent parsuje "ocami",
  * kazde volanie plati reziu shellu.

MCP z toho spravi typovane volanie s typovanou odpovedou. Popis nastroja je
sucastou protokolu, takze **nastroj sa ohlasi sam** - to je presne ten problem,
kvoli ktoremu vznikol `docs/reference/action-api.md` ("nemal som ako vediet,
ze to existuje").

CO PONUKA

  pf_doc_list      zoznam dokumentov a kapitol s cenou v tokenoch
  pf_doc           jedna kapitola (namiesto celeho suboru)
  pf_doc_search    v ktorych kapitolach to je (nadpisy, nie telo)
  pf_lint          nalezy v sietach ako STRUKTURA, nie ako text
  pf_fix           opravy, ktore maju jednoznacne riesenie (dry-run default)
  pf_api           vyhladanie primitiva volatelneho z akcie

SPUSTENIE

Server hovori JSON-RPC 2.0 po stdio, bez zavislosti - staci Python 3.
Registracia pre Claude Code je v `.mcp.json` v roote repozitara.

Rucna skuska bez klienta:

    printf '%s\\n' \\
      '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \\
      '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \\
      | python3 tools/pfmcp.py

Ohranicenie: server **nic nemeni**, kym sa nezavola `pf_fix` s `write=true`.
Ziadny nastroj tu nesiaha na engine ani na databazu - to ostava na `pfsync`
a akceptacnych sadach, ktore maju bezat vedome.
"""

import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # etask-configuration
REPO = ROOT.parent
PY = sys.executable or "python3"

PROTOKOL = "2024-11-05"

NASTROJE = [
    {
        "name": "pf_doc_list",
        "description": ("Zoznam dokumentacie: skratka dokumentu, subor, kapitoly "
                        "a cena v tokenoch. Pouzi na zaciatku, ked nevies, kde "
                        "hladat - cela dokumentacia ma ~86 000 tokenov, jedna "
                        "kapitola ~500."),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "pf_doc",
        "description": ("Vrati JEDNU kapitolu dokumentacie namiesto celeho suboru. "
                        "Napr. dokument='runbook', kapitola='4' vrati navod na menu "
                        "(~2 700 tokenov namiesto ~14 500)."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dokument": {"type": "string",
                             "description": "runbook | learnings | engine | frontend | "
                                            "backend | sd | prirucka | analyza | "
                                            "petriflow | cheatsheet | api | claude | skill"},
                "kapitola": {"type": "string",
                             "description": "cislo alebo znacka: '4', 'B8b', 'E20'"},
            },
            "required": ["dokument", "kapitola"],
        },
    },
    {
        "name": "pf_doc_search",
        "description": ("Kde je o com napisane. Vracia NADPISY kapitol s cenou, nie "
                        "telo - telo si vypytaj cez pf_doc. Hlada bez diakritiky."),
        "inputSchema": {
            "type": "object",
            "properties": {"vyraz": {"type": "string"}},
            "required": ["vyraz"],
        },
    },
    {
        "name": "pf_lint",
        "description": ("Skontroluje Petriflow siete a vrati nalezy ako zoznam "
                        "objektov {subor, riadok, uroven, pravidlo, sprava, oprava}. "
                        "Chyta tiche chyby: prekrytie v gride (uloha sa nevykresli), "
                        "preklep vo volani delegata, mrtve polia, race medzi blur "
                        "a klikom na tlacidlo."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cesta": {"type": "string",
                          "description": "default 'processes/' - priecinok alebo subor"},
            },
        },
    },
    {
        "name": "pf_fix",
        "description": ("Aplikuje opravy, ktore maju jednoznacne riesenie "
                        "(prekrytie v gride, type=textarea, chybajuce immediate). "
                        "Bez write=true len ukaze, co by spravil."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cesta": {"type": "string", "description": "default 'processes/'"},
                "write": {"type": "boolean", "description": "default false"},
            },
        },
    },
    {
        "name": "pf_api",
        "description": ("Hlada v inventari metod volatelnych z Petriflow akcie "
                        "(engine + primitiva projektu). Pouzi PRED napisanim novej "
                        "metody - delegat je dynamicky, takze preklep spadne az za "
                        "behu."),
        "inputSchema": {
            "type": "object",
            "properties": {"vyraz": {"type": "string",
                                     "description": "cast mena metody, napr. 'role' alebo 'menu'"}},
            "required": ["vyraz"],
        },
    },
]


# ----------------------------------------------------------------- nastroje

def spusti(args, cwd=ROOT):
    """Spusti nastroj a vrati (kod, vystup). Bez shellu - argumenty su pole."""
    try:
        p = subprocess.run([PY] + args, cwd=str(cwd), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=180)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return 2, f"pfmcp: {args} sa nepodarilo spustit: {e}"


def t_doc_list(_):
    kod, out = spusti(["tools/pfdoc.py", "--json"])
    try:
        return json.loads(out)
    except ValueError:
        return {"chyba": out[:400]}


def t_doc(args):
    dokument = str(args.get("dokument", "")).strip()
    kapitola = str(args.get("kapitola", "")).strip()
    if not dokument or not kapitola:
        return {"chyba": "treba `dokument` aj `kapitola`"}
    kod, out = spusti(["tools/pfdoc.py", dokument, kapitola])
    return {"najdene": kod == 0, "text": out}


def t_doc_search(args):
    vyraz = str(args.get("vyraz", "")).strip()
    if not vyraz:
        return {"chyba": "treba `vyraz`"}
    kod, out = spusti(["tools/pfdoc.py", "hladaj", vyraz])
    kapitoly = []
    for r in out.splitlines():
        # "  3x  nadpis ...  ~2760t  pfdoc.py runbook 4"
        if "pfdoc.py" in r:
            casti = r.rsplit("pfdoc.py", 1)
            prikaz = casti[1].strip().split()
            kapitoly.append({
                "nadpis": casti[0].strip().split("  ", 1)[-1].strip(),
                "dokument": prikaz[0] if prikaz else None,
                "kapitola": prikaz[1].strip('"') if len(prikaz) > 1 else None,
            })
    return {"kapitoly": kapitoly, "vypis": out if not kapitoly else None}


def t_lint(args):
    cesta = str(args.get("cesta") or "processes/")
    kod, out = spusti(["tools/pflint.py", cesta])
    nalezy = []
    aktualny = None
    for r in out.splitlines():
        if r.startswith("    → ") and aktualny:
            aktualny["oprava"] = r[6:].strip()
            continue
        casti = r.split(": ", 1)
        if len(casti) == 2 and ":" in casti[0] and "[" in casti[1]:
            miesto = casti[0].rsplit(":", 1)
            zvysok = casti[1]
            uroven = zvysok.split(" ", 1)[0]
            pravidlo = zvysok.split("[", 1)[1].split("]", 1)[0] if "[" in zvysok else ""
            sprava = zvysok.split("] ", 1)[1] if "] " in zvysok else zvysok
            aktualny = {"subor": miesto[0], "riadok": int(miesto[1]) if miesto[1].isdigit() else 0,
                        "uroven": uroven.lower(), "pravidlo": pravidlo, "sprava": sprava}
            nalezy.append(aktualny)
    sumar = out.strip().splitlines()[-1] if out.strip() else ""
    return {"nalezy": nalezy, "sumar": sumar, "cisto": kod == 0 and not [
        n for n in nalezy if n["uroven"] == "error"]}


def t_fix(args):
    cesta = str(args.get("cesta") or "processes/")
    prikaz = ["tools/pffix.py", cesta]
    if args.get("write"):
        prikaz.append("--write")
    kod, out = spusti(prikaz)
    return {"zapisane": bool(args.get("write")), "vypis": out}


def t_api(args):
    vyraz = str(args.get("vyraz", "")).strip().lower()
    if not vyraz:
        return {"chyba": "treba `vyraz`"}
    cesta = REPO / "docs" / "reference" / "action-api.md"
    if not cesta.is_file():
        return {"chyba": "inventar neexistuje - spusti tools/pfapi.py > docs/reference/action-api.md"}
    najdene = []
    for r in io.open(cesta, encoding="utf-8", errors="replace").read().splitlines():
        if vyraz in r.lower() and (r.startswith("### ") or r.startswith("- `")):
            najdene.append(r.lstrip("#- ").strip())
    return {"metody": najdene[:40], "spolu": len(najdene)}


VYKONAJ = {
    "pf_doc_list": t_doc_list,
    "pf_doc": t_doc,
    "pf_doc_search": t_doc_search,
    "pf_lint": t_lint,
    "pf_fix": t_fix,
    "pf_api": t_api,
}


# ------------------------------------------------------------------ protokol

def odpoved(id_, vysledok):
    return {"jsonrpc": "2.0", "id": id_, "result": vysledok}


def chyba(id_, kod, sprava):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": kod, "message": sprava}}


def spracuj(sprava):
    metoda = sprava.get("method")
    id_ = sprava.get("id")
    params = sprava.get("params") or {}

    if metoda == "initialize":
        return odpoved(id_, {
            "protocolVersion": PROTOKOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "petriflow", "version": "1.0.0"},
        })
    if metoda in ("notifications/initialized", "initialized"):
        return None                      # notifikacia - neodpoveda sa
    if metoda == "tools/list":
        return odpoved(id_, {"tools": NASTROJE})
    if metoda == "tools/call":
        meno = params.get("name")
        args = params.get("arguments") or {}
        fn = VYKONAJ.get(meno)
        if not fn:
            return chyba(id_, -32601, f"neznamy nastroj: {meno}")
        try:
            vysledok = fn(args)
        except Exception as e:                                  # noqa: BLE001
            return odpoved(id_, {"content": [{"type": "text",
                                              "text": f"pfmcp: {meno} zlyhal: {e}"}],
                                 "isError": True})
        return odpoved(id_, {"content": [
            {"type": "text", "text": json.dumps(vysledok, ensure_ascii=False, indent=2)}]})
    if metoda == "ping":
        return odpoved(id_, {})
    if id_ is None:
        return None
    return chyba(id_, -32601, f"neznama metoda: {metoda}")


def main():
    # stdout je protokol, takze cokolvek ine musi ist na stderr - inak sa
    # klientovi rozsype parsovanie a prejavi sa to ako "server nereaguje".
    vstup = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    vystup = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    for riadok in vstup:
        riadok = riadok.strip()
        if not riadok:
            continue
        try:
            sprava = json.loads(riadok)
        except ValueError:
            continue
        odp = spracuj(sprava)
        if odp is not None:
            vystup.write(json.dumps(odp, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
