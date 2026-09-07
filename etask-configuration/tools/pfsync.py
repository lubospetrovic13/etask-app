#!/usr/bin/env python3
"""
pfsync - povie, ktore siete sa rozisli s tym, co drzi bezici engine.

Preco to existuje: `NetRunner` importuje siet len ked v databaze CHYBA. Po
zmene existujuceho XML sa teda pri starte nestane nic - engine dalej drzi staru
verziu, `LATEST` mieri na nu a nove casy vznikaju zo stareho modelu. Nikde sa to
neohlasi. RUNBOOK dlho tvrdil "po zmene siete staci tools/up.sh"; pre novu siet
to platilo, pre zmenenu nie.

Zistuje sa to bezstavovo: `GET /api/petrinet/{id}/file` vrati presne to XML,
ktore bolo naimportovane, bajt za bajtom. Staci ho porovnat s lokalnym suborom -
netreba ziadny marker, checksum subor ani pamat medzi behmi.

    python3 tools/pfsync.py             # co sa rozislo, citatelne
    python3 tools/pfsync.py --list      # len cesty, na rure do pfcheck
    python3 tools/pfsync.py --sync      # rozdielne naimportuje a prideli role

`--sync` vola tools/pfcheck.sh (import + ground truth z logu) a potom
tools/pfseed.py (role maju stringId per verziu siete, takze po re-importe treba
pridelit znova). Presne toto robi aj `tools/up.sh` po starte backendu.

Nespustat proti produkcii - `--sync` importuje nove verzie sieti.

Exit 0 = vsetko sedi (alebo synchronizovane), 1 = nieco sa rozislo (bez --sync),
2 = zle prostredie.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSES = ROOT / "processes"
MANIFEST = ROOT / "processes.json"

URL = os.environ.get("PF_URL", "http://127.0.0.1:8080")
USER = os.environ.get("PF_USER", "super@netgrif.com")
PASS = os.environ.get("PF_PASS", "password")

HAL = "application/hal+json, application/json;q=0.9, */*;q=0.8"


def login():
    req = urllib.request.Request(
        URL + "/api/auth/login", method="GET",
        headers={"Authorization": "Basic " + base64.b64encode(
            f"{USER}:{PASS}".encode()).decode()})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            token = r.headers.get("X-Auth-Token")
    except urllib.error.HTTPError as e:
        # Endpoint vracia 405, ale token uz je v hlavicke - autentifikacny
        # filter bezi pred handlerom. To iste robi pfcheck.sh.
        token = e.headers.get("X-Auth-Token")
    except urllib.error.URLError:
        sys.exit(f"pfsync: engine na {URL} neodpoveda")
    if not token:
        sys.exit(f"pfsync: prihlasenie {USER} zlyhalo")
    return token


def call(token, method, path, body=None, raw=False):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-Auth-Token": token, "Accept": HAL}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(URL + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8")
            return r.status, (text if raw else (json.loads(text) if text else None))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def find_bash():
    """Cesta k bashu, ktory vie spustit tools/*.sh.

    Na Windows `bash` v PATH ukazuje na WSL (C:\\Windows\\System32\\bash.exe)
    a ten padne na `execvpe(/bin/bash) failed`, ak WSL distribucia nie je
    nainstalovana - pricom Git Bash, v ktorom sa tento repozitar realne
    pouziva, je inde. Preto sa System32 preskakuje.
    """
    env = os.environ.get("PFSYNC_BASH")
    if env and Path(env).exists():
        return env
    found = shutil.which("bash")
    if found and "system32" not in found.replace("\\", "/").lower():
        return found
    for candidate in (r"C:\Program Files\Git\bin\bash.exe",
                      r"C:\Program Files\Git\usr\bin\bash.exe",
                      r"C:\Program Files (x86)\Git\bin\bash.exe",
                      "/bin/bash", "/usr/bin/bash"):
        if Path(candidate).exists():
            return candidate
    return found  # nech to padne s citatelnou chybou volajuceho


def identifier_of(path):
    """<id> z XML. Rovnako ako NetRunner: regexom, prvy vyskyt, bez XML parsera -
    v CDATA byva to, co parser nema rad."""
    import re
    xml = path.read_text(encoding="utf-8")
    m = re.search(r"(?s)<document\b.*?<id>\s*([^<\s][^<]*?)\s*</id>", xml)
    return m.group(1) if m else None


def newest(token, identifier):
    st, r = call(token, "POST", "/api/petrinet/search?size=200", {"identifier": identifier})
    if not isinstance(r, dict):
        return None
    refs = [x for x in (r.get("_embedded") or {}).get("petriNetReferences", [])
            if x["identifier"] == identifier]
    if not refs:
        return None
    refs.sort(key=lambda x: [int(n) for n in x["version"].split(".")])
    return refs[-1]


def imports():
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception as e:
        sys.exit(f"pfsync: {MANIFEST} sa neda precitat: {e}")
    return [str(f) for f in manifest.get("import", [])]


def compare():
    """[(path, identifier, stav, verzia)] pre kazdu siet z manifestu."""
    token = login()
    out = []
    for name in imports():
        path = PROCESSES / name
        if not path.exists():
            # Napr. configuration_tiles.xml zije v resources backendu, nie tu.
            continue
        ident = identifier_of(path)
        if ident is None:
            out.append((path, name, "BEZ_ID", "-"))
            continue
        ref = newest(token, ident)
        if ref is None:
            out.append((path, ident, "CHYBA_V_ENGINE", "-"))
            continue
        st, stored = call(token, "GET", f"/api/petrinet/{ref['stringId']}/file", raw=True)
        if st != 200 or not isinstance(stored, str):
            out.append((path, ident, "NEDA_SA_PRECITAT", ref["version"]))
            continue
        local = path.read_text(encoding="utf-8")
        same = stored.replace("\r\n", "\n").strip() == local.replace("\r\n", "\n").strip()
        out.append((path, ident, "SEDI" if same else "ROZISLO_SA", ref["version"]))
    return out


def main(argv):
    only_list = "--list" in argv
    do_sync = "--sync" in argv

    rows = compare()
    changed = [r for r in rows if r[2] != "SEDI"]

    if only_list:
        for path, _, _, _ in changed:
            print(path.relative_to(ROOT).as_posix())
        return 0

    for path, ident, stav, ver in rows:
        mark = "  " if stav == "SEDI" else "->"
        print(f"{mark} {path.name:24s} {ident:28s} v{ver:8s} {stav}")

    if not changed:
        print("\npfsync: vsetky siete sedia s tym, co drzi engine")
        return 0

    print(f"\npfsync: rozislo sa {len(changed)} sieti")
    if not do_sync:
        print("        engine drzi stary model, LATEST mieri na neho a nove casy")
        print("        vzniknu z neho. Zosuladit: python3 tools/pfsync.py --sync")
        return 1

    files = [str(p) for p, _, _, _ in changed]
    print("\n== pfcheck (import + ground truth z logu)")
    log = ROOT.parent / ".run" / "backend.log"
    bash = find_bash()
    if not bash:
        print("pfsync: bash sa nenasiel - nastav PFSYNC_BASH na cestu k bashu")
        return 2
    cmd = [bash, str(ROOT / "tools" / "pfcheck.sh")]
    if log.exists():
        cmd += ["--log", str(log)]
    rc = subprocess.call(cmd + files)
    if rc != 0:
        print("pfsync: import zlyhal, role sa neprideluju")
        return 1

    print("\n== pfseed (rola ma stringId per verziu siete)")
    rc = subprocess.call([sys.executable, str(ROOT / "tools" / "pfseed.py")])
    if rc != 0:
        return 1

    print("\npfsync: hotovo. Prihlasene sessiony drzia stare id roli -")
    print("        v prehliadaci sa treba odhlasit a prihlasit, inak vracia 403.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
