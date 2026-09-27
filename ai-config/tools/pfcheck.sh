#!/usr/bin/env bash
#
# pfcheck - overi Petriflow siet proti BEZIACEMU enginu. Ground truth.
#
# Preco to existuje samostatne od pflint.py:
#
#   pflint kontroluje to, co sa da zistit z XML. Dialekt, ktory engine naozaj
#   prijme, sa z XML zistit NEDA - oficialna XSD, runtime NAE 6.3.1 a nas vlastny
#   zapisnik si v poradi elementov navzajom odporuju (viz tools/README-pflint.md).
#   Jedina pravda je import do enginu.
#
# A preco to nie je jednoduche curl:
#
#   1. Import endpoint pri chybe vracia HOLE {"status":500} bez akehokolvek
#      dovodu. Skutocna pricina je vylucne v logu servera. Bez nej je hlaska
#      nepouzitelna - "500" nepovie, ci je to preklep v id, diakritika v nazve
#      procesu alebo chybajuca rola.
#   2. Zlyhany import NIE JE atomicky. Stihne vytvorit procesne role a priradit
#      ich uzivatelovi; zostane osirely odkaz na neexistujucu siet a
#      PRIHLASENIE zacne vracat 500. Preto sa po kazdom importe overuje login -
#      inak si rozbijes instanciu a nevies o tom.
#
# Pouzitie:
#   tools/pfcheck.sh processes/sd_ticket.xml
#   tools/pfcheck.sh processes/                    # cely priecinok
#   tools/pfcheck.sh --url http://host:8080 --user a@b.c --pass x net.xml
#   tools/pfcheck.sh --log /path/backend.log net.xml       # log ako subor
#   tools/pfcheck.sh --container etask-backend net.xml     # log z kontejnera
#
# Exit 0 = vsetky siete presli, 1 = aspon jedna zlyhala, 2 = zle pouzitie
# alebo engine nedostupny.

set -uo pipefail

URL="${PF_URL:-http://127.0.0.1:8080}"
USER_EMAIL="${PF_USER:-super@netgrif.com}"
USER_PASS="${PF_PASS:-password}"
LOG_FILE="${PF_LOG:-}"
CONTAINER="${PF_CONTAINER:-}"
RELEASE="major"
FILES=()

while [ $# -gt 0 ]; do
  case "$1" in
    --url) URL="$2"; shift 2 ;;
    --user) USER_EMAIL="$2"; shift 2 ;;
    --pass) USER_PASS="$2"; shift 2 ;;
    --log) LOG_FILE="$2"; shift 2 ;;
    --container) CONTAINER="$2"; shift 2 ;;
    --release) RELEASE="$2"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "pfcheck: neznamy prepinac $1" >&2; exit 2 ;;
    *) FILES+=("$1"); shift ;;
  esac
done

[ ${#FILES[@]} -eq 0 ] && { echo "pfcheck: ziadna siet. -h pre pomoc." >&2; exit 2; }

# priecinok -> vsetky .xml v nom
EXPANDED=()
for f in "${FILES[@]}"; do
  if [ -d "$f" ]; then
    while IFS= read -r x; do EXPANDED+=("$x"); done < <(find "$f" -maxdepth 1 -name '*.xml' | sort)
  else
    EXPANDED+=("$f")
  fi
done
[ ${#EXPANDED[@]} -eq 0 ] && { echo "pfcheck: ziadne .xml na kontrolu" >&2; exit 2; }

# ---------------------------------------------------------------- log source
# Ked log necitame, povie sa to nahlas. Tichy "500 bez detailu" je presne to,
# comu sa tento nastroj snazi zabranit.
log_len() {
  if [ -n "$LOG_FILE" ] && [ -r "$LOG_FILE" ]; then wc -l < "$LOG_FILE"
  elif [ -n "$CONTAINER" ]; then docker logs "$CONTAINER" 2>&1 | wc -l
  else echo 0; fi
}
log_since() {
  local from="$1"
  if [ -n "$LOG_FILE" ] && [ -r "$LOG_FILE" ]; then tail -n "+$((from + 1))" "$LOG_FILE"
  elif [ -n "$CONTAINER" ]; then docker logs "$CONTAINER" 2>&1 | tail -n "+$((from + 1))"
  fi
}

# Z haldy stack trace vytiahne to, co je pouzitelne: prvu vynimku a jej pricinu.
root_cause() {
  grep -vE '^\s+at |^\s*\.\.\. ' \
    | grep -oE '[A-Za-z.]*(Exception|Error): [^]]*' \
    | grep -vE 'ErrorReportValve|ExceptionTranslationFilter|dispatcherServlet' \
    | sed -E 's/ with root cause.*//; s/\s+$//' \
    | awk '!seen[$0]++' \
    | head -3
}

if [ -z "$LOG_FILE" ] && [ -z "$CONTAINER" ]; then
  echo "pfcheck: POZOR - bez --log alebo --container sa pricina zlyhania neda zistit."
  echo "         Import endpoint vracia len 500 bez dovodu."
  echo
fi

# ---------------------------------------------------------------- preflight
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$URL/api/auth/login" 2>/dev/null)
if [ "$code" = "000" ]; then
  echo "pfcheck: engine na $URL neodpoveda." >&2
  exit 2
fi

login() {
  curl -s -i --max-time 20 -X POST "$URL/api/auth/login" \
    -H 'Content-Type: application/json' -u "$USER_EMAIL:$USER_PASS" 2>/dev/null \
    | grep -i '^x-auth-token' | tr -d '\r' | awk '{print $2}'
}

TOKEN=$(login)
if [ -z "$TOKEN" ]; then
  echo "pfcheck: prihlasenie ako $USER_EMAIL zlyhalo." >&2
  echo "         Ak to predtym fungovalo, mozno instanciu rozbil predchadzajuci" >&2
  echo "         zlyhany import - viz osirele procesne role v docs/SERVICE_DESK.md." >&2
  exit 2
fi

echo "pfcheck: engine $URL, prihlaseny ako $USER_EMAIL"
echo

# ---------------------------------------------------------------- kontrola
failed=0
passed=0

for net in "${EXPANDED[@]}"; do
  [ -r "$net" ] || { echo "$net: CHYBA nedostupny subor"; failed=$((failed + 1)); continue; }

  before=$(log_len)
  resp=$(curl -s --max-time 120 -X POST "$URL/api/petrinet/import" \
           -H "X-Auth-Token: $TOKEN" \
           -F "file=@$net" -F "releaseType=$RELEASE" 2>/dev/null)

  version=$(printf '%s' "$resp" | grep -o '"version":"[^"]*"' | head -1 | cut -d'"' -f4)
  identifier=$(printf '%s' "$resp" | grep -o '"identifier":"[^"]*"' | head -1 | cut -d'"' -f4)

  if [ -n "$version" ]; then
    # Import presel. Teraz to dolezite: nerozbil login?
    if [ -z "$(login)" ]; then
      echo "$net: CHYBA import presel, ALE PRIHLASENIE PRESTALO FUNGOVAT"
      echo "    → zostali osirele procesne role; instancia je rozbita a treba ju vycistit"
      failed=$((failed + 1))
    else
      echo "$net: OK  $identifier v$version"
      passed=$((passed + 1))
    fi
    continue
  fi

  # Zlyhalo. Telo odpovede je bezcenne, pricina je v logu.
  echo "$net: CHYBA"
  status=$(printf '%s' "$resp" | grep -oE '<status>[0-9]+</status>|"status":[0-9]+' | head -1)
  [ -n "$status" ] && echo "    odpoved: $status (bez detailu - endpoint dovod nevracia)"

  cause=$(log_since "$before" | root_cause)
  if [ -n "$cause" ]; then
    echo "    pricina z logu:"
    printf '%s\n' "$cause" | sed 's/^/      /'
  elif [ -n "$LOG_FILE" ] || [ -n "$CONTAINER" ]; then
    echo "    v logu nic nove - skus vyssi log level alebo pozri log rucne"
  else
    echo "    pricinu neviem - spusti znova s --log alebo --container"
  fi
  failed=$((failed + 1))
done

echo
echo "pfcheck: $passed preslo, $failed zlyhalo"
[ "$failed" -gt 0 ] && exit 1
exit 0
