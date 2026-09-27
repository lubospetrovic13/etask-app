#!/usr/bin/env python3
"""
pfseed - prideli procesne role podla deklarovaneho cieloveho stavu. Idempotentne.

Preco to existuje: rola ma stringId razene PER VERZIU siete. Po kazdom
re-importe uzivatel na casoch novej verzie pristup strati, aj ked "tu rolu ma".
Za jednu session som siet importoval 12-krat a po kazdom importe musel role
prideliť znova - rucne, cez volania, v ktorych sa lahko spleti id.

Pre cloveka je to otrava. Pre AI agenta je to horsie: po tretej iteracii testuje
na rozbitom stave a nevie o tom. Preto sa cielovy stav deklaruje raz v seed.json
a tento skript ho dopocita.

Dve pasce, ktore to riesi za teba:

  1. POST /api/user/{id}/role/assign role PREPISUJE, nepridava - a berie ciste
     pole id, nie {"roleIds": [...]}. Neuplny zoznam znamena, ze uzivatel
     stratí systemovu rolu `default` a zmiznu mu vsetky zobrazenia. pfseed
     preto role mimo netScope zachova.
  2. REST nikde nevracia importId roli siete, len lokalizovany nazov. Mapovanie
     importId -> nazov sa preto cita z lokalneho XML v processes/ a nazov ->
     stringId z /api/petrinet/{id}/roles.
  3. `role/assign` vrati 2xx aj vtedy, ked ulozene role nezodpovedaju poslanym.
     pfseed preto po kazdom zapise CITA stav znova a porovnava. Bez toho hlasil
     uspech na zapise, ktory sa nestal - typicky ked bezal hned po importe
     a cerstva verzia siete jeste nebola vo vyhladavani; `assign` pritom cely
     zoznam prepisuje, takze tej verzii role zmizli a v appke to vyzeralo, ze
     uzivatelovi zmizla uloha, na ktoru rolu ma.
  4. Zlyhany import siete role vytvori, priradi uzivatelovi a siet nechá
     neexistovat. Taky uzivatel sa potom **neda precitat cez REST vobec** -
     /api/user/search aj /api/user/me na nom vracia 500, lebo serializacia roli
     spadne na chybajucej sieti. Cez API sa to opravit NEDA; --repair to preto
     robi priamo v databaze. Je to jediná cesta, nie skratka.

    python3 tools/pfseed.py
    python3 tools/pfseed.py --dry-run
    python3 tools/pfseed.py --repair          # vycisti osirele role (DB)
    python3 tools/pfseed.py --url http://host:8080 --user a@b.c --pass x

Exit 0 = cielovy stav plati, 1 = nieco zlyhalo, 2 = zle prostredie.
"""

import fnmatch
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSES = ROOT / "processes"
CONFIG = ROOT / "seed.json"


# Locale, ktore engine NEPOZNA - a preto vrati `defaultValue`.
#
# `I18nString.getTranslation(Locale)` je `translations.getOrDefault(
# locale.getLanguage(), defaultValue)`, takze pri neznamom jazyku dostaneme
# presne to, co je v XML ako hodnota elementu. To je jedina hodnota, ktoru
# nastroj vie porovnat s lokalnym XML.
#
# Preco to nemoze zostat nevyplnene: BEZ hlavicky `Accept-Language` pouzije
# Spring locale JVM, co je tu `en` - takze `/api/petrinet/{id}/roles` vratil
# `name: "User administrator"`, kym v XML stalo `Správca používateľov`. Parovanie
# podla nazvu prestalo sediet a `pfseed` ohlasil "cielovy stav plati", pricom
# rolu z najnovsej verzie siete nikomu nepridelil. Ticho: prihlasenie fungovalo,
# karta appky bola vidno, len zoznam uloh bol prazdny.
#
# A preco nie `sk`: to by predpokladalo, ze default value je slovensky. Je -
# taka je tu konvencia - ale neznamy jazyk funguje bez toho predpokladu.
NEUTRAL_LOCALE = "zz"

def http(url, token=None, method="GET", body=None, basic=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept-Language", NEUTRAL_LOCALE)
    if token:
        req.add_header("X-Auth-Token", token)
    if basic:
        import base64
        req.add_header("Authorization", "Basic " + base64.b64encode(basic.encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)
    except OSError as e:
        return 0, str(e), {}


def login(url, email, password):
    # Token pride v hlavicke aj vtedy, ked endpoint vrati 405 - autentifikacny
    # filter enginu bezi pred routovanim. Riadime sa preto hlavickou, nie stavom.
    _, _, headers = http(f"{url}/api/auth/login", method="POST", basic=f"{email}:{password}")
    for k, v in headers.items():
        if k.lower() == "x-auth-token" and v.strip():
            return v.strip()
    return None


def local_role_titles():
    """{net_identifier: {importId: title}} z lokalnych XML."""
    out = {}
    for f in sorted(PROCESSES.glob("*.xml")):
        try:
            root = ET.fromstring(f.read_text(encoding="utf-8"))
        except ET.ParseError:
            continue
        ident = None
        roles = {}
        for child in root:
            tag = child.tag.split("}", 1)[-1]
            if tag == "id" and ident is None:
                ident = (child.text or "").strip()
            elif tag == "role":
                rid = rtitle = None
                for c in child:
                    ct = c.tag.split("}", 1)[-1]
                    if ct == "id":
                        rid = (c.text or "").strip()
                    elif ct == "title":
                        rtitle = (c.text or "").strip()
                if rid:
                    roles[rid] = rtitle or rid
        if ident:
            out[ident] = roles
    return out


def mongo_eval(script):
    """Spusti mongosh. Skusi docker kontejner, potom lokalny mongosh."""
    import subprocess
    db = os.environ.get("PF_DB", "etask")
    container = os.environ.get("PF_MONGO_CONTAINER")
    candidates = []
    if container:
        candidates.append(["docker", "exec", container, "mongosh", "--quiet", db, "--eval", script])
    else:
        try:
            out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                                 capture_output=True, text=True, timeout=20)
            for name in out.stdout.split():
                if "mongo" in name:
                    candidates.append(["docker", "exec", name, "mongosh", "--quiet", db,
                                       "--eval", script])
                    break
        except (OSError, subprocess.TimeoutExpired):
            pass
    candidates.append(["mongosh", "--quiet", db, "--eval", script])
    for cmd in candidates:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if res.returncode == 0:
            return res.stdout.strip(), None
    return None, "mongosh sa nepodarilo spustit (skus PF_MONGO_CONTAINER alebo PF_DB)"


# Dva rozne druhy osirelosti, a druhy nie je zovseobecnenie prveho:
#
#   A) processRole EXISTUJE, ale jeho siet nie. Vznikne zlyhanym importom -
#      ten stihne role vyrobit a siet nechá neexistovat.
#   B) processRole NEEXISTUJE, ale uzivatel nan stale ukazuje. Vznikne
#      zmazanim siete: engine k nej zmaze aj role, ale zaznamy v `user`
#      necha - a serializacia uzivatela potom spadne rovnako ako pri A.
#
# Prve vydanie riesilo len A, takze po zmazani duplicitnych sieti hlasilo
# "osirele role nie su" a uzivatel zostal necitatelny. Obe vetvy musia byt.
REPAIR_SCRIPT = """
var netIds = db.petriNet.find({}, {_id: 1}).toArray().map(function (n) { return String(n._id); });
var orphans = db.processRole.find({}).toArray().filter(function (r) {
    return r.netId && netIds.indexOf(String(r.netId)) < 0;
});
var ids = orphans.map(function (r) { return r._id; });
var users = 0, deleted = 0;
if (ids.length > 0) {
    users += db.user.updateMany({"processRoles._id": {$in: ids}},
                               {$pull: {processRoles: {_id: {$in: ids}}}}).modifiedCount;
    deleted = db.processRole.deleteMany({_id: {$in: ids}}).deletedCount;
}

// B) visiace odkazy z pouzivatela na rolu, ktora uz nie je.
var roleIds = {};
db.processRole.find({}, {_id: 1}).toArray().forEach(function (r) { roleIds[String(r._id)] = 1; });
var dangling = 0;
db.user.find({"processRoles.0": {$exists: true}}, {processRoles: 1}).toArray().forEach(function (u) {
    var bad = (u.processRoles || []).filter(function (r) { return !roleIds[String(r._id)]; })
                                    .map(function (r) { return r._id; });
    if (bad.length === 0) { return; }
    db.user.updateOne({_id: u._id}, {$pull: {processRoles: {_id: {$in: bad}}}});
    dangling += bad.length;
    users += 1;
});
print("ORPHANS " + (ids.length + dangling) + " users " + users + " deleted " + deleted);
"""


def repair_orphans():
    out, err = mongo_eval(REPAIR_SCRIPT)
    if err:
        print(f"pfseed: {err}", file=sys.stderr)
        return 2
    line = [l for l in (out or "").splitlines() if l.startswith("ORPHANS")]
    if not line:
        print(f"pfseed: neocakavana odpoved z mongosh: {out!r}", file=sys.stderr)
        return 2
    parts = line[0].split()
    count = int(parts[1])
    if count == 0:
        print("pfseed: osirele role nie su")
    else:
        print(f"pfseed: vycistenych {count} osirelych rol"
              + (f", upravenych uzivatelov {parts[3]}" if len(parts) > 3 else ""))
    return 0


def main(argv):
    url = os.environ.get("PF_URL", "http://127.0.0.1:8080")
    admin = os.environ.get("PF_USER", "super@netgrif.com")
    password = os.environ.get("PF_PASS", "password")
    dry = "--dry-run" in argv
    if "--repair" in argv:
        return repair_orphans()
    i = 0
    while i < len(argv):
        if argv[i] == "--url": url = argv[i + 1]; i += 2
        elif argv[i] == "--user": admin = argv[i + 1]; i += 2
        elif argv[i] == "--pass": password = argv[i + 1]; i += 2
        elif argv[i] in ("-h", "--help"):
            print(__doc__.strip()); return 0
        else: i += 1

    if not CONFIG.is_file():
        print(f"pfseed: {CONFIG} neexistuje", file=sys.stderr)
        return 2
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    scope = cfg.get("netScope") or []
    wanted_users = cfg.get("users") or []

    token = login(url, admin, password)
    if not token:
        print(f"pfseed: prihlasenie ako {admin} na {url} zlyhalo", file=sys.stderr)
        return 2

    # --- siete v scope, vsetky verzie -----------------------------------
    status, nets, _ = http(f"{url}/api/petrinet/search?size=500", token, "POST", {})
    if status >= 400 or not isinstance(nets, dict):
        print(f"pfseed: zoznam sieti sa nepodarilo ziskat ({status})", file=sys.stderr)
        return 2
    refs = nets.get("_embedded", {}).get("petriNetReferences", [])
    scoped = [n for n in refs
              if any(fnmatch.fnmatch(n.get("identifier", ""), p) for p in scope)]

    titles = local_role_titles()

    # Dopytat sa NA KAZDY lokalny identifikator zvlast a doplnit, co v hromadnom
    # zozname chybalo.
    #
    # Preco: `role/assign` cely zoznam roli PREPISUJE, takze verzia siete, ktoru
    # pfseed nevidi, ostane bez roli - a nikto to nezisti, kym niekomu nezmizne
    # uloha, na ktoru "rolu ma". A nevidiet ju sa da lahko: pfseed sa bezne
    # spusta hned po importe (`pfsync --sync`, `up.sh`), kedy cerstva verzia
    # v hromadnom vyhladavani este nemusi byt. Presne to sa stalo na
    # `schvalovanie/faktury/fa_faktura` v3.0.0: import presel, pfseed hlasil
    # zmeny, a super prisel o vsetky roly tej verzie.
    known = {(n.get("identifier"), n.get("version")) for n in scoped}
    for ident in sorted(titles):
        if not any(fnmatch.fnmatch(ident, pat) for pat in scope):
            continue
        st, one, _ = http(f"{url}/api/petrinet/search?size=100", token, "POST",
                          {"identifier": ident})
        found = (one.get("_embedded", {}).get("petriNetReferences", [])
                 if isinstance(one, dict) else [])
        found = [n for n in found if n.get("identifier") == ident]
        if not found:
            print(f"  ! {ident}: v enginu NIE JE ziadna verzia - siet nie je "
                  f"naimportovana, role sa nemaju na co pridelit")
            continue
        for n in found:
            if (n.get("identifier"), n.get("version")) not in known:
                print(f"  + {ident} v{n.get('version')}: doplnene do rozsahu "
                      f"(v hromadnom zozname nebolo)")
                known.add((n.get("identifier"), n.get("version")))
                scoped.append(n)

    if not scoped:
        print(f"pfseed: netScope {scope} nezodpoveda ziadnej sieti", file=sys.stderr)
        return 1

    # --- importId -> {stringId} cez vsetky verzie ------------------------
    by_import = {}
    warned = set()
    for n in scoped:
        ident, nid = n["identifier"], n["stringId"]
        mapping = titles.get(ident)
        if not mapping:
            if ident not in warned:
                print(f"  ! {ident}: lokalne XML sa nenaslo, role tejto siete preskakujem")
                warned.add(ident)
            continue
        st, roles, _ = http(f"{url}/api/petrinet/{nid}/roles", token)
        if st >= 400 or not isinstance(roles, dict):
            continue
        title_to_id = {}
        for r in roles.get("processRoles", []):
            title_to_id.setdefault(r["name"], []).append(r["stringId"])
        for import_id, title in mapping.items():
            ids = title_to_id.get(title, [])
            if len(ids) > 1 and (ident, title) not in warned:
                print(f"  ! {ident}: nazov roly '{title}' nie je jednoznacny, beriem prvy")
                warned.add((ident, title))
            if ids:
                by_import.setdefault(import_id, set()).add(ids[0])

    print(f"pfseed: {len(scoped)} verzii sieti v scope, "
          f"{len(by_import)} rol podla importId"
          + (" (dry-run)" if dry else ""))

    scoped_idents = {n["identifier"] for n in scoped}
    failed = changed = 0

    for spec in wanted_users:
        email = spec["email"]
        want = spec.get("roles") or []
        st, res, _ = http(f"{url}/api/user/search?size=20", token, "POST", {"fulltext": email})
        users = res.get("_embedded", {}).get("users", []) if isinstance(res, dict) else []
        user = next((u for u in users if (u.get("email") or "").lower() == email.lower()), None)
        if not user:
            if st >= 500:
                print(f"  {email}: NECITATELNY - /api/user/search vratil {st}.")
                print("      Takto sa chova uzivatel s osirelymi rolami po zlyhanom")
                print("      importe siete. Cez REST sa to opravit neda, spusti:")
                print("         python3 tools/pfseed.py --repair")
            else:
                print(f"  {email}: NENAJDENY")
            failed += 1
            continue

        current = {r["stringId"] for r in (user.get("processRoles") or [])}
        # Role mimo scope zachovavame - inak uzivatel strati `default` a s nim
        # vsetky zobrazenia. assign endpoint totiz prepisuje, nepridava.
        preserved = {r["stringId"] for r in (user.get("processRoles") or [])
                     if r.get("netImportId") not in scoped_idents}
        desired = set(preserved)
        for import_id in want:
            desired |= by_import.get(import_id, set())

        if desired == current:
            print(f"  {email}: bez zmeny ({len(current)} rol)")
            continue

        changed += 1
        delta = f"{len(current)} → {len(desired)}"
        if dry:
            print(f"  {email}: zmena {delta}  {sorted(want) or '(ziadne SD role)'}")
            continue

        st, _, _ = http(f"{url}/api/user/{user['id']}/role/assign", token, "POST",
                        sorted(desired))
        if st >= 400:
            print(f"  {email}: CHYBA pri pridelovani ({st})")
            failed += 1
            continue

        # OVERIT, ze to naozaj sedi. Endpoint vrati 2xx aj vtedy, ked ulozene
        # role nezodpovedaju tomu, co sme poslali - a bez tejto kontroly to
        # pfseed hlasil ako uspech.
        #
        # Preco to nie je paranoja: pfseed sa bezne spusta HNED po importe
        # (`pfsync --sync`, `up.sh`), kedy cerstva verzia siete jeste nemusi byt
        # vo vyhladavani. `role/assign` cely zoznam PREPISUJE, takze verzia,
        # ktoru pfseed nevidel, ostane bez roli - a v appke to vyzera tak, ze
        # uzivatelovi zmizla uloha, na ktoru "rolu ma". Stalo sa to na
        # `schvalovanie/faktury/fa_faktura`.
        st, after, _ = http(f"{url}/api/user/search?size=20", token, "POST", {"fulltext": email})
        again = (after.get("_embedded", {}).get("users", []) if isinstance(after, dict) else [])
        fresh = next((u for u in again if (u.get("email") or "").lower() == email.lower()), None)
        stored = {r["stringId"] for r in ((fresh or {}).get("processRoles") or [])}
        missing = desired - stored
        if missing:
            print(f"  {email}: {delta}  {sorted(want) or '(ziadne SD role)'}"
                  f"  ! ULOZENE NESEDI, chyba {len(missing)} rol")
            print("      Najcastejsia pricina: siet bola naimportovana prave teraz")
            print("      a jej verzia sa este neobjavila vo vyhladavani. Spusti")
            print("      pfseed znova - a ak to trva, over `GET /api/petrinet/search`.")
            failed += 1
        else:
            print(f"  {email}: {delta}  {sorted(want) or '(ziadne SD role)'}")

    print()
    if failed:
        print(f"pfseed: {failed} zlyhani")
        return 1
    # Pocet zmien sa vypisuje aj v dry-run, aby sa dal asertovat v pftest.sh.
    suffix = " (dry-run, nic sa nezapisalo)" if dry else ""
    print(f"pfseed: cielovy stav plati, zmien {changed}{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
