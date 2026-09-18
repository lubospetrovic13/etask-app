#!/usr/bin/env python3
"""
pfuri - uzly URI (karty v bocnom menu): vypis a odstranenie osirelych.

PRECO TO EXISTUJE. Uzol URI prezije zmazanie sieti aj premenovanie ich
identifikatora a engine na jeho odstranenie NEMA REST (`pfdoc engine E7`).
Po presune appky do inej kategorie tak v menu zostane karta, ktora vedie do
prazdna - a dovod sa neda najst ani v manifeste, ani v Mongu, lebo uzol zije
v ELASTICSEARCHI. Posledny taky presun (`uver` -> `financie/uver`) sa musel
dorobit rucne cez `curl`; toto je ten postup, aby sa nemusel vymyslat znova.

Odstranenie ma DVE casti a obe treba:

  1. dokument v Elasticu (`etask_uri`) - samotny uzol, a odkaz nan
     v `childrenId` rodica; osamoteny uzol by v strome zostal visiet,
  2. riadok v Mongu (`uriNodeData`) - opravnenia karty, ktore si drzi tento
     projekt. Uzol z Elasticu zmizne, riadok tam zostane a pri buducom uzle
     s ROVNAKOU CESTOU sa ticho pouzije. To je ta tichsia polovica.

    python3 tools/pfuri.py                     # vypis strom uzlov
    python3 tools/pfuri.py --drop uver         # zahod uzol 'uver'
    python3 tools/pfuri.py --orphans           # uzly, ktore nema ziadna siet

`--orphans` porovnava cesty uzlov proti identifikatorom NASADENYCH sieti
(`processes.json` + `apps-installed.json`), takze povie, co po presunoch
zostalo. Nemaze nic sam - mazanie je nevratne a patri do ruky cloveka.

Nespustat proti produkcii bez rozmyslu: zmazanie uzla je nevratne.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

ES = os.environ.get("PF_ELASTIC", "http://localhost:9200")
INDEX = os.environ.get("PF_URI_INDEX", "etask_uri")
DB = os.environ.get("PF_DB", "etask")
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.abspath(os.path.join(HERE, ".."))


# ------------------------------------------------------------- Elastic

def es(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(ES + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            t = r.read().decode("utf-8")
            return json.loads(t) if t else None
    except urllib.error.URLError as e:
        sys.exit(f"pfuri: Elasticsearch na {ES} neodpoveda ({e})")


def nodes():
    """Vsetky uzly ako {id: source}."""
    d = es("GET", f"/{INDEX}/_search?size=500&q=*")
    return {h["_id"]: h["_source"] for h in d["hits"]["hits"]}


# --------------------------------------------------------------- Mongo

def mongo(script):
    """Spusti mongosh - najprv v kontejneri, potom lokalne.

    To iste a z toho isteho dovodu ako `pfseed --repair`: na `uriNodeData`
    engine ziadne API nema, je to kolekcia tohto projektu.
    """
    candidates = []
    container = os.environ.get("PF_MONGO_CONTAINER")
    if container:
        candidates.append(["docker", "exec", container, "mongosh", "--quiet", DB,
                           "--eval", script])
    else:
        try:
            out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                                 capture_output=True, text=True, timeout=20)
            for name in out.stdout.split():
                if "mongo" in name:
                    candidates.append(["docker", "exec", name, "mongosh", "--quiet", DB,
                                       "--eval", script])
                    break
        except (OSError, subprocess.TimeoutExpired):
            pass
    candidates.append(["mongosh", "--quiet", DB, "--eval", script])
    for cmd in candidates:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if res.returncode == 0:
            return res.stdout.strip(), None
    return None, "mongosh sa nepodarilo spustit (ani v kontejneri, ani lokalne)"


# ------------------------------------------------------------- manifest

def nasadene_cesty():
    """Cesty, ktore MAJU existovat - z identifikatorov nasadenych sieti.

    Uzol vznika kazdym prefixom identifikatora siete: `financie/uver/uv_ziadost`
    vyrobi `financie` aj `financie/uver`. Preto sa tu zbieraju vsetky prefixy,
    nie len cele identifikatory.
    """
    cesty = {"root"}

    def pridaj(identifikator):
        casti = [c for c in identifikator.split("/") if c]
        # posledna cast je nazov siete, nie uzol
        for i in range(1, len(casti)):
            cesty.add("/".join(casti[:i]))

    try:
        with open(os.path.join(CONFIG, "processes.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
    except OSError:
        return None
    for uri in (manifest.get("uriNodes") or {}):
        cesty.add(uri)
    for item in (manifest.get("bootstrapCase") or []):
        ident = item.get("net") if isinstance(item, dict) else item
        if ident:
            pridaj(ident)

    # Identifikatory su v XML, nie v manifeste - manifest ma len nazvy suborov.
    procesy = os.path.join(CONFIG, "processes")
    if os.path.isdir(procesy):
        for name in os.listdir(procesy):
            if not name.endswith(".xml"):
                continue
            try:
                with open(os.path.join(procesy, name), encoding="utf-8") as fh:
                    head = fh.read(4000)
            except OSError:
                continue
            start = head.find("<id>")
            end = head.find("</id>")
            if start != -1 and end > start:
                pridaj(head[start + 4:end].strip())
    return cesty


# ---------------------------------------------------------------- akcie

def vypis():
    ns = nodes()
    podla_cesty = {s.get("uriPath"): (i, s) for i, s in ns.items()}
    for cesta in sorted(podla_cesty):
        i, s = podla_cesty[cesta]
        deti = len(s.get("childrenId") or [])
        print(f"  {cesta:<32} {i:<24} deti: {deti}")
    print(f"\npfuri: {len(ns)} uzlov v {INDEX}")


def osirele():
    ns = nodes()
    ocakavane = nasadene_cesty()
    if ocakavane is None:
        sys.exit("pfuri: processes.json sa neda precitat")
    zvysne = sorted(s.get("uriPath") for s in ns.values()
                    if s.get("uriPath") not in ocakavane)
    if not zvysne:
        print("pfuri: ziadny osireny uzol - kazda karta ma svoju siet")
        return 0
    print("pfuri: uzly, ktore nema ziadna nasadena siet:")
    for cesta in zvysne:
        print(f"  {cesta}")
    print("\nZahodit: python3 tools/pfuri.py --drop <cesta>")
    return 1


def zahod(cesta):
    ns = nodes()
    ciel = [i for i, s in ns.items() if s.get("uriPath") == cesta]
    if not ciel:
        print(f"pfuri: uzol '{cesta}' v Elasticu nie je")
    else:
        tid = ciel[0]
        # Najprv odpojit od rodica. Opacne poradie necha v strome odkaz na
        # dokument, ktory uz neexistuje - a to sa prejavi az pri vykreslovani.
        for i, s in ns.items():
            kids = s.get("childrenId") or []
            if tid in kids:
                es("POST", f"/{INDEX}/_update/{i}",
                   {"doc": {"childrenId": [k for k in kids if k != tid]}})
                print(f"  odpojeny od rodica '{s.get('uriPath')}'")
        es("DELETE", f"/{INDEX}/_doc/{tid}")
        es("POST", f"/{INDEX}/_refresh")
        print(f"  uzol '{cesta}' ({tid}) zmazany z Elasticu")

    # A opravnenia karty v Mongu - tichsia polovica.
    script = ('var r = db.uriNodeData.deleteMany({uri: %s}); '
              'print("MONGO " + r.deletedCount);' % json.dumps(cesta))
    out, err = mongo(script)
    if err:
        print(f"  ! uriNodeData sa zmazat nepodarilo - {err}")
        print(f"  ! sprav to rucne: mongosh {DB} --eval "
              f"'db.uriNodeData.deleteMany({{uri: \"{cesta}\"}})'")
        return 1
    pocet = 0
    for line in (out or "").splitlines():
        if line.startswith("MONGO"):
            pocet = int(line.split()[1])
    print(f"  uriNodeData: zmazanych {pocet} riadkov")
    return 0


def main(argv):
    if "--orphans" in argv:
        return osirele()
    if "--drop" in argv:
        i = argv.index("--drop")
        if i + 1 >= len(argv):
            sys.exit("pfuri: --drop chce cestu uzla, napr. --drop uver")
        return zahod(argv[i + 1])
    vypis()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
