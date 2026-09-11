#!/usr/bin/env bash
#
# bootstrap - pripravi cerstvy checkout na prvy start.
#
# Jedina vec, ktorá po `git clone` naozaj chybi, je JWT podpisovy kluc.
# `src/**/resources/certificates` je v .gitignore (a spravne - kluc sa
# necommituje), takze po checkoute tam nie je nic. Engine potom anonymnu session
# nepodpise a **verejne formulare vracaju 401** - bez chybovej spravy, ktora by to
# s klucom spojila. Presne to zazije kazdy, kto si tuto sablonu naklonuje.
#
#   etask-configuration/tools/bootstrap.sh
#
# Idempotentne: existujuci kluc neprepise.

set -euo pipefail
cd "$(dirname "$0")/../.."

CERT_DIR="etask-backend-starter/src/main/resources/certificates"
CERT="$CERT_DIR/private.der"

if [ -s "$CERT" ]; then
  echo "bootstrap: JWT kluc uz existuje ($CERT)"
else
  command -v openssl >/dev/null || { echo "bootstrap: openssl nie je k dispozicii" >&2; exit 1; }
  mkdir -p "$CERT_DIR"
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT
  openssl genrsa -out "$tmp" 2048 2>/dev/null
  openssl pkcs8 -topk8 -inform PEM -outform DER -in "$tmp" -out "$CERT" -nocrypt
  chmod 600 "$CERT"
  echo "bootstrap: JWT kluc vygenerovany ($CERT)"
fi

echo
echo "Cely stack jednym prikazom (vratane tychto krokov):"
echo "  etask-configuration/tools/up.sh"
echo
echo "Recepty na bezne ulohy: docs/RUNBOOK.md"
echo
echo "Rucne, krok po kroku:"
echo "  1. Java 11 (Groovy 3 na JDK 21 pada):"
echo "       export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64"
echo "  2. Zavislosti, ktore sa nedaju rozresit z verejnych repozitarov:"
echo "       deploy/vendor-deps.sh"
echo "  3. Databazy:"
echo "       cd etask-backend-starter && docker compose up -d"
echo "  4. Backend s UTF-8 (inak import procesu s diakritikou zhodi"
echo "     InvalidPathException):"
echo "       LANG=C.UTF-8 mvn -DskipTests spring-boot:run"
echo "  5. Role a demo stav:"
echo "       cd etask-configuration && python3 tools/pfseed.py"
