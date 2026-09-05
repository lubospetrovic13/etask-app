#!/usr/bin/env bash
#
# up - rozbehne cely stack jednym prikazom.
#
# Existuje preto, ze "rozbehaj mi to" je najcastejsia prva uloha na tomto
# repozitari a kazdy krok ma tichu pascu:
#
#   chybajuci JWT kluc  -> verejne formulare vracaju 401 bez chybovej spravy
#   JDK 17/21           -> Groovy 3 pada na "Unsupported class file major version"
#   bez LANG=C.UTF-8    -> import siete s diakritikou zhodi InvalidPathException
#   stale target/       -> Maven preskoci kopirovanie a jar je bez sieti,
#                          alebo v nom zostane trieda, ktoru uz zdroj nema
#   chybajuci redis     -> Spring spadne az na session store, dlho po starte
#
# Ziadny z nich sa neprejavi ako zrozumitelna chyba, takze su zapisane tu.
#
#   tools/up.sh                  # rozbehne, co nebezi; existujuce data necha
#   tools/up.sh --build          # vynuti cisty rebuild backendu
#   tools/up.sh --fresh          # zahodi databazu a zacne odznova
#   tools/up.sh --frontend       # popri backende spusti aj ng serve
#   tools/up.sh --db mojadb      # ina databaza (default etask)
#
# Nespusta sa proti produkcii - --fresh maze data.

set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2
ROOT=$(pwd)

DB="${DATABASE_NAME:-etask}"
DO_BUILD=0
DO_FRESH=0
DO_FRONTEND=0
LOG_DIR="${ETASK_LOG_DIR:-$ROOT/.run}"

while [ $# -gt 0 ]; do
  case "$1" in
    --build)    DO_BUILD=1; shift ;;
    --fresh)    DO_FRESH=1; shift ;;
    --frontend) DO_FRONTEND=1; shift ;;
    --db)       DB="$2"; shift 2 ;;
    -h|--help)  sed -n '2,30p' "$0"; exit 0 ;;
    *)          echo "up: neznamy argument $1" >&2; exit 2 ;;
  esac
done

step() { printf '\n== %s\n' "$1"; }
die()  { printf 'up: %s\n' "$1" >&2; exit 1; }

mkdir -p "$LOG_DIR"

# --- 1. JWT kluc ------------------------------------------------------------
step "JWT kluc"
etask-configuration/tools/bootstrap.sh >/dev/null || die "bootstrap.sh zlyhal"
echo "ok (etask-backend-starter/src/main/resources/certificates/private.der)"

# --- 2. Java 11 -------------------------------------------------------------
step "Java"
if [ -z "${JAVA_HOME:-}" ] || ! "$JAVA_HOME/bin/java" -version 2>&1 | grep -q '"11'; then
  for candidate in /usr/lib/jvm/java-11-openjdk-* /usr/lib/jvm/*11*; do
    [ -x "$candidate/bin/java" ] || continue
    export JAVA_HOME="$candidate"
    break
  done
fi
[ -x "${JAVA_HOME:-}/bin/java" ] || die "Java 11 sa nenasla. Groovy 3 na JDK 17+ pada na 'Unsupported class file major version'."
"$JAVA_HOME/bin/java" -version 2>&1 | grep -m1 'version' || true

# --- 3. Docker --------------------------------------------------------------
step "Docker"
if ! docker info >/dev/null 2>&1; then
  # V kontajneri bez systemd sa daemon musi spustit rucne.
  command -v dockerd >/dev/null || die "docker daemon nebezi a dockerd nie je k dispozicii"
  echo "daemon nebezi, spustam dockerd..."
  # Po tvrdom reste kontajnera zostane pid subor bez procesu a dockerd sa
  # odmietne spustit s "pid file found, ensure docker is not running".
  if [ -f /var/run/docker.pid ] && ! kill -0 "$(cat /var/run/docker.pid)" 2>/dev/null; then
    rm -f /var/run/docker.pid
  fi
  nohup dockerd </dev/null >"$LOG_DIR/dockerd.log" 2>&1 &
  disown $! 2>/dev/null || true
  for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 2; done
  docker info >/dev/null 2>&1 || die "dockerd sa nepodarilo spustit, pozri $LOG_DIR/dockerd.log"
fi
echo "ok"

# --- 4. Databazy ------------------------------------------------------------
step "Mongo, Elasticsearch, Redis"
(cd etask-backend-starter && docker compose up -d) || die "docker compose up zlyhal"

echo -n "cakam na Elasticsearch"
for _ in $(seq 1 60); do
  curl -sf -m 3 localhost:9200 >/dev/null 2>&1 && break
  echo -n .; sleep 3
done
echo
curl -sf -m 3 localhost:9200 >/dev/null 2>&1 || die "Elasticsearch nenabehol"

MONGO=$(docker ps --format '{{.Names}}' | grep -m1 mongo || true)
[ -n "$MONGO" ] || die "mongo kontajner sa nenasiel"

if [ "$DO_FRESH" = 1 ]; then
  step "--fresh: zahadzujem databazu $DB"
  docker exec "$MONGO" mongosh --quiet --eval "db.getSiblingDB('$DB').dropDatabase()" >/dev/null
  # Indexy URI su v Elasticsearchi, nie v Mongu. Bez ich zmazania by po
  # dropDatabase zostali uzly menu bez sieti, ktore ich vyrobili.
  curl -sf -X DELETE "localhost:9200/${DB}_case,${DB}_task,${DB}_uri" >/dev/null 2>&1
  echo "ok"
fi

# --- 5. Build ---------------------------------------------------------------
step "Backend build"
JAR="etask-backend-starter/target/app.jar"
if [ "$DO_BUILD" = 0 ] && [ -f "$JAR" ]; then
  # Stale target/ je tu najcastejsia tichá chyba: jar vyzera hotovo, ale
  # neobsahuje to, co je v zdrojoch. Radsej prestavat, nez ladit fantoma.
  newer=$(find etask-backend-starter/src etask-configuration/processes \
               etask-configuration/processes.json -newer "$JAR" 2>/dev/null | head -1)
  [ -n "$newer" ] && { echo "zdroje su novsie nez jar ($newer) - prestavujem"; DO_BUILD=1; }
fi

if [ "$DO_BUILD" = 1 ] || [ ! -f "$JAR" ]; then
  echo "mvn clean package (par minut)..."
  (cd etask-backend-starter && JAVA_HOME="$JAVA_HOME" mvn -o -q clean package -DskipTests) \
    || (cd etask-backend-starter && JAVA_HOME="$JAVA_HOME" mvn -q clean package -DskipTests) \
    || die "build zlyhal"
fi
echo "ok ($JAR)"

# --- 6. Backend -------------------------------------------------------------
step "Backend"
if curl -sf -m 3 -o /dev/null "http://localhost:8080/api/auth/login" \
   || curl -s -m 3 -o /dev/null -w '%{http_code}' "http://localhost:8080/api/auth/login" 2>/dev/null | grep -q 401; then
  echo "uz bezi na :8080 (nerestartujem)"
else
  BE_LOG="$LOG_DIR/backend.log"
  # nohup + disown: bez `disown` zostane java v tabulke uloh tohto shellu,
  # bash na nu na konci caka a `up.sh` sa nikdy nevrati do promptu. Skript,
  # ktory nekonci, je horsi nez ziadny - clovek ho preklikne Ctrl-C a zabije
  # s nim aj backend. Vnorene subshelly to neriesia, skusane.
  cd etask-backend-starter || die "chyba etask-backend-starter"
  DATABASE_NAME="$DB" LANG=C.UTF-8 \
    nohup "$JAVA_HOME/bin/java" -Dfile.encoding=UTF-8 -Dsun.jnu.encoding=UTF-8 \
    -jar target/app.jar </dev/null >"$BE_LOG" 2>&1 &
  disown $! 2>/dev/null || true
  cd "$ROOT" || exit 2
  echo -n "cakam na start"
  for _ in $(seq 1 90); do
    grep -q "Started EtaskApplication" "$BE_LOG" 2>/dev/null && break
    grep -q "Application run failed" "$BE_LOG" 2>/dev/null && {
      echo; echo "--- posledna chyba:"; grep -A 3 "Application run failed" "$BE_LOG" | head -5
      die "backend nenabehol, cely log: $BE_LOG"
    }
    echo -n .; sleep 3
  done
  echo
  grep -q "Started EtaskApplication" "$BE_LOG" || die "backend nenabehol, log: $BE_LOG"
  # Runnery bezia az po starte kontextu, takze na ne treba chvilu pockat.
  # Cakame na "finished", nie na "Calling ...": posledny runner este par sekund
  # pracuje a inak by sumar nizsie vysiel neuplny.
  for _ in $(seq 1 40); do
    grep -q "BootstrapCaseRunner finished" "$BE_LOG" && break
    sleep 3
  done
  echo "--- co spravili runnery:"
  grep -E "Importujem siet|Uri node |Bootstrap case" "$BE_LOG" | sed 's/.*: /  /' || true
  echo "log: $BE_LOG"
fi

# --- 7. Frontend ------------------------------------------------------------
if [ "$DO_FRONTEND" = 1 ]; then
  step "Frontend"
  [ -d etask-frontend-starter/node_modules ] || (cd etask-frontend-starter && npm ci)
  FE_LOG="$LOG_DIR/frontend.log"
  cd etask-frontend-starter || die "chyba etask-frontend-starter"
  nohup npm start </dev/null >"$FE_LOG" 2>&1 &
  disown $! 2>/dev/null || true
  cd "$ROOT" || exit 2
  echo -n "cakam na ng serve"
  for _ in $(seq 1 100); do
    grep -qE "Compiled successfully|Angular Live Development Server" "$FE_LOG" 2>/dev/null && break
    echo -n .; sleep 3
  done
  echo
  echo "http://localhost:4200  (log: $FE_LOG)"
fi

# --- 8. Kam dalej -----------------------------------------------------------
step "Hotovo"
cat <<EOF
  backend    http://localhost:8080
  swagger    http://localhost:8080/swagger-ui.html
  databaza   $DB

Prihlasenie: super@netgrif.com / password  (default admin enginu)

Testovacie ucty (admin@test.local a spol.) sa vytvoria len ked je nastavene
ETASK_TEST_PASSWORD - bez nej ich EtaskUserCreator preskoci a pfseed ich
nahlasi ako NENAJDENY. Ak ich chces:

  ETASK_TEST_PASSWORD=test1234 tools/up.sh --fresh

Procesne roly po (re)importe:  cd etask-configuration && python3 tools/pfseed.py
Bezne ulohy krok po kroku:     etask-configuration/docs/RUNBOOK.md
EOF
