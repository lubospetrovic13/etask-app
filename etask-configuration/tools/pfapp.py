#!/usr/bin/env python3
"""
pfapp - nainstaluj alebo odinstaluj Petriflow appku, ktora zije vo vlastnom repe.

PRECO TO EXISTUJE

Appka v tomto stacku je len `processes/*.xml` plus riadky v manifeste - ziadna
Java, ziadny Angular. Da sa teda drzat vo vlastnom repozitari a nasadit do
lubovolneho checkoutu starteru. Co sa ale rucne zliepat neda, je manifest:
`processes.json` ma tri sekcie a `seed.json` stvrtu, musia sedet dokopy, a ked
jedna chyba, NIC TO NEPOVIE.

  * chyba `import`      -> siet sa nenaimportuje, karta v menu vedie do prazdna
  * chyba `bootstrapCase` -> siet je, ale zobrazenia nikto nepostavi
  * chyba `uriNodes`   -> zobrazenia su, ale karta appky nie je vidno
  * chyba `netScope`   -> `pfseed` nepridelí role ani po tom, co si ich niekto
                          do `seed.json` dopise

Kazda z tych stvorice sa prejavi ako "appka nefunguje" bez chybovej spravy.
Preto je to nastroj a nie odsek v README.

CO OD APPKY OCAKAVA

V korenov repa appky `app.json`:

    {
      "name": "dovolenky",
      "import": ["dv_ziadost.xml", "dv_menu.xml"],
      "bootstrapCase": [{"net": "dovolenky/dv_menu", "rebuildOnNewVersion": true}],
      "uriNodes": {"dovolenky": {"icon": "beach_access",
                                 "requiredAuthorities": [],
                                 "requiredProcessRoles": ["zamestnanec"]}},
      "netScope": ["dovolenky/*"],
      "tools": ["dvcheck.py"]
    }

a subory v `processes/` a `tools/`. Format je zamerne ten isty ako v manifeste
starteru - aby sa nemuselo prekladat medzi dvoma tvarmi.

SUBORY SA KOPIRUJU, NEODKAZUJU

`install` siete do starteru **skopiruje**. Nie je to nedbalost - je to jedina
varianta, ktora funguje po `git clone`:

  * `NetRunner` cita siete z classpath, kam ich pom kopiruje z
    `etask-configuration/processes`. Odkaz na cudzi adresar by znamenal zasah do
    `pom.xml` per appka, co je presne to, co tento stack nechce.
  * Manifest je vstup pre runtime a musi byt v jare. Keby v nom appka bola
    a jej subory nie, `NetRunner` by pri starte hlasil "nie je na classpath"
    a nikto by nevedel, ci je to chyba appky alebo checkoutu.

Zdroj pravdy je teda repo appky, a starter drzi nasadenu kopiu - ako kazdy
vendoring. Aby sa kopia nerozisla nepozorovane, `pfapp.py status` porovna obsah
so zdrojom.

POUZITIE

    python3 tools/pfapp.py install /cesta/k/etask-app-dovolenky
    python3 tools/pfapp.py status
    python3 tools/pfapp.py list
    python3 tools/pfapp.py remove dovolenky

Exit 0 = hotovo (pri `status` aj "vsetko sedi"), 1 = chyba alebo rozdiel,
2 = zle pouzitie.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "processes.json"
SEED = ROOT / "seed.json"
PROCESSES = ROOT / "processes"
TOOLS = ROOT / "tools"

# Zoznam nainstalovanych appiek. Drzi sa oddelene od `processes.json` preto, ze
# ten je vstup pre runtime - a odinstalovanie potrebuje vediet, CO presne appka
# pridala, nie hadat to podla prefixu nazvu. Prefix by nestacil: appka moze
# pridat uzol URI, ktory sa nemenuje ako jej siete.
INSTALLED = ROOT / "apps-installed.json"


def load(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def bootstrap_net(entry):
    """Identifikator zo `bootstrapCase` polozky, ktora moze byt string aj objekt."""
    return entry["net"] if isinstance(entry, dict) else entry


def read_app(src):
    app_file = src / "app.json"
    if not app_file.is_file():
        sys.exit(f"pfapp: {app_file} neexistuje - to nie je repo appky")
    app = json.loads(app_file.read_text(encoding="utf-8"))
    name = app.get("name")
    if not name:
        sys.exit("pfapp: app.json nema `name`")
    return app, name


def install(src_arg, dry):
    src = Path(src_arg).resolve()
    app, name = read_app(src)

    installed = load(INSTALLED, {})
    if name in installed:
        sys.exit(f"pfapp: appka `{name}` uz je nainstalovana. "
                 f"Najprv `pfapp.py remove {name}`.")

    nets = app.get("import") or []
    tools = app.get("tools") or []

    # --- najprv skontroluj vsetko, potom zapisuj -----------------------
    #
    # Polovicna instalacia je horsia nez zadna: manifest by uz appku ohlasoval
    # a subory by chybali, takze `NetRunner` by pri starte hlasil
    # "nie je na classpath" a nikto by nevedel, ci je to chyba appky alebo
    # instalacie.
    missing = [f for f in nets if not (src / "processes" / f).is_file()]
    missing += [f for f in tools if not (src / "tools" / f).is_file()]
    if missing:
        sys.exit("pfapp: v repe appky chybaju subory:\n  " + "\n  ".join(missing))

    clashes = [f for f in nets if (PROCESSES / f).exists()]
    clashes += [f for f in tools if (TOOLS / f).exists()]
    if clashes:
        sys.exit("pfapp: v starteri uz existuju (nic neprepisujem):\n  "
                 + "\n  ".join(clashes))

    manifest = load(MANIFEST, {})
    seed = load(SEED, {})

    have_nodes = manifest.get("uriNodes") or {}
    node_clash = [k for k in (app.get("uriNodes") or {}) if k in have_nodes]
    if node_clash:
        sys.exit("pfapp: uzol URI uz v manifeste je: " + ", ".join(node_clash))

    # --- co sa doplni --------------------------------------------------
    added_imports = [f for f in nets if f not in (manifest.get("import") or [])]
    have_boot = {bootstrap_net(e) for e in (manifest.get("bootstrapCase") or [])}
    added_boot = [e for e in (app.get("bootstrapCase") or [])
                  if bootstrap_net(e) not in have_boot]
    added_nodes = dict(app.get("uriNodes") or {})
    added_scope = [p for p in (app.get("netScope") or [])
                   if p not in (seed.get("netScope") or [])]

    plan = [f"processes/{f}" for f in nets] + [f"tools/{f}" for f in tools]
    print(f"pfapp: install `{name}` z {src}")
    for line in plan:
        print(f"  + {line}")
    print(f"  + processes.json: import {added_imports}, "
          f"bootstrapCase {[bootstrap_net(e) for e in added_boot]}, "
          f"uriNodes {list(added_nodes)}")
    print(f"  + seed.json: netScope {added_scope}")
    if dry:
        print("\npfapp: dry-run, nic som nezapisal")
        return 0

    for f in nets:
        shutil.copy2(src / "processes" / f, PROCESSES / f)
    for f in tools:
        shutil.copy2(src / "tools" / f, TOOLS / f)

    manifest.setdefault("import", []).extend(added_imports)
    manifest.setdefault("bootstrapCase", []).extend(added_boot)
    manifest.setdefault("uriNodes", {}).update(added_nodes)
    save(MANIFEST, manifest)

    if added_scope:
        seed.setdefault("netScope", []).extend(added_scope)
        save(SEED, seed)

    installed[name] = {
        "source": str(src),
        "title": app.get("title") or name,
        "processes": nets,
        "tools": tools,
        "bootstrapCase": [bootstrap_net(e) for e in added_boot],
        "uriNodes": list(added_nodes),
        "netScope": added_scope,
    }
    save(INSTALLED, installed)

    print(f"""
pfapp: `{name}` nainstalovana. Dalej:

  python3 tools/pflint.py processes/
  python3 tools/pfgroovy.py processes/
  python3 tools/pfi18n.py processes/
  tools/up.sh                      # manifest sa pakuje do jaru, treba prestavat
  # do seed.json dopis, kto ma dostat role tejto appky (netScope je doplneny)
  python3 tools/pfseed.py
""")
    for f in tools:
        print(f"  python3 tools/{f}")
    return 0


def remove(name, dry):
    installed = load(INSTALLED, {})
    rec = installed.get(name)
    if not rec:
        sys.exit(f"pfapp: `{name}` nie je v {INSTALLED.name}. "
                 f"Nainstalovane: {sorted(installed) or 'nic'}")

    manifest = load(MANIFEST, {})
    seed = load(SEED, {})

    print(f"pfapp: remove `{name}`")
    for f in rec["processes"]:
        print(f"  - processes/{f}")
    for f in rec["tools"]:
        print(f"  - tools/{f}")
    print(f"  - processes.json: import, bootstrapCase {rec['bootstrapCase']}, "
          f"uriNodes {rec['uriNodes']}")
    print(f"  - seed.json: netScope {rec['netScope']}")
    print("""
  POZOR, co sa TYM NEZMAZE:
    * siete uz naimportovane v engine a ich casy,
    * polozky menu (`preference_filter_item`) a filtre, ktore appka postavila,
    * uzol URI - ten zije v Elasticsearchi a REST na jeho zmazanie NEEXISTUJE
      (ENGINE_ISSUES E7), takze karta v menu zostane a bude viest do prazdna.
  Recept na rucne odstranenie je v docs/RUNBOOK.md, cast 2.""")
    if dry:
        print("\npfapp: dry-run, nic som nezmazal")
        return 0

    for f in rec["processes"]:
        (PROCESSES / f).unlink(missing_ok=True)
    for f in rec["tools"]:
        (TOOLS / f).unlink(missing_ok=True)

    manifest["import"] = [f for f in (manifest.get("import") or [])
                          if f not in rec["processes"]]
    manifest["bootstrapCase"] = [e for e in (manifest.get("bootstrapCase") or [])
                                 if bootstrap_net(e) not in rec["bootstrapCase"]]
    for node in rec["uriNodes"]:
        (manifest.get("uriNodes") or {}).pop(node, None)
    save(MANIFEST, manifest)

    if rec["netScope"]:
        seed["netScope"] = [p for p in (seed.get("netScope") or [])
                            if p not in rec["netScope"]]
        save(SEED, seed)

    installed.pop(name)
    save(INSTALLED, installed)
    print(f"\npfapp: `{name}` odinstalovana. Prestav jar: tools/up.sh")
    return 0


def show_list():
    installed = load(INSTALLED, {})
    if not installed:
        print("pfapp: ziadna appka nie je nainstalovana cez pfapp")
        print("       (siete priamo v processes/ tento zoznam nevidi)")
        return 0
    for name, rec in sorted(installed.items()):
        print(f"{name}  ({rec.get('title')})")
        print(f"  zdroj: {rec.get('source')}")
        print(f"  siete: {', '.join(rec['processes'])}")
        if rec["tools"]:
            print(f"  testy: {', '.join(rec['tools'])}")
    return 0


def status():
    """Porovna nasadenu kopiu so zdrojovym repom appky.

    Vendoring bez tejto kontroly je tichy: niekto opravi siet v starteri, appka
    sa nasadi, a v jej vlastnom repe ta oprava nikdy nebude - alebo naopak.
    """
    installed = load(INSTALLED, {})
    if not installed:
        print("pfapp: ziadna appka nie je nainstalovana cez pfapp")
        return 0
    diffs = 0
    for name, rec in sorted(installed.items()):
        src = Path(rec.get("source", ""))
        print(f"{name}  ({rec.get('title')})")
        if not src.is_dir():
            print(f"  ! zdroj {src} nie je dostupny - porovnat sa neda")
            diffs += 1
            continue
        for kind, folder in (("processes", PROCESSES), ("tools", TOOLS)):
            for f in rec.get(kind) or []:
                here, there = folder / f, src / kind / f
                if not there.is_file():
                    print(f"  ! {kind}/{f}: v zdroji uz nie je")
                    diffs += 1
                elif not here.is_file():
                    print(f"  ! {kind}/{f}: v starteri chyba")
                    diffs += 1
                elif here.read_bytes() != there.read_bytes():
                    print(f"  ~ {kind}/{f}: ROZISLO SA so zdrojom")
                    diffs += 1
                else:
                    print(f"  = {kind}/{f}")
    if diffs:
        print(f"\npfapp: {diffs} rozdielov. `install` znova po `remove`, "
              f"alebo prenes zmeny do repa appky.")
        return 1
    print("\npfapp: vsetko sedi so zdrojom")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="pfapp.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["install", "remove", "list", "status"])
    ap.add_argument("target", nargs="?",
                    help="cesta k repu appky (install) alebo jej nazov (remove)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.action == "list":
        return show_list()
    if args.action == "status":
        return status()
    if not args.target:
        ap.error(f"{args.action} potrebuje argument")
    if args.action == "install":
        return install(args.target, args.dry_run)
    return remove(args.target, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
