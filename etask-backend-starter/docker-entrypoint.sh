#!/bin/sh
#
# Vygeneruje JWT podpisovy kluc, ak chyba, a az potom spusti aplikaciu.
#
# Bez kluca engine nepodpise anonymnu session a VEREJNE FORMULARE vracaju 401 -
# bez chybovej spravy, ktora by to s klucom spojila. Kluc je gitignored, takze
# v obraze nie je a v cerstvom nasadeni by chybal. Generuje sa do /etask/certificates,
# co je volume, takze prezije restart aj vymenu obrazu - inak by sa pri kazdom
# starte zmenil a vsetkym by vypadli sessions.
set -eu

CERT_DIR="${JWT_CERT_DIR:-/etask/certificates}"
CERT="$CERT_DIR/private.der"

if [ ! -s "$CERT" ]; then
  mkdir -p "$CERT_DIR"
  tmp="$(mktemp)"
  openssl genrsa -out "$tmp" 2048 2>/dev/null
  openssl pkcs8 -topk8 -inform PEM -outform DER -in "$tmp" -out "$CERT" -nocrypt
  rm -f "$tmp"
  chmod 600 "$CERT"
  echo "entrypoint: JWT podpisovy kluc vygenerovany ($CERT)"
else
  echo "entrypoint: JWT podpisovy kluc uz existuje ($CERT)"
fi

export JWT_SIGN_CERT="file:$CERT"
exec java ${JAVA_OPTS:-} -jar /app.jar "$@"
