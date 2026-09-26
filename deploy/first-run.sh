#!/usr/bin/env sh
# Jednorazova sluzba `setup` z compose.yaml v koreni repozitara.
#
# `docker compose up` (zeleny trojuholnik v IDEA / VS Code) nepusta up.sh, a bez
# neho sa po zdvihnuti stacku nestane to, co up.sh robi na konci: `pfsync --sync`.
# Na cistej databaze to znamena, ze `pfseed` nepridelil ziadnu rolu, admin sa
# prihlasi, ale zakladanie casu vracia 403 a appka vyzera nenaimportovana.
# Po zmene existujuceho XML zase engine drzi stary model (NetRunner importuje
# len chybajuce siete). Tato sluzba robi presne ten krok a skonci.
#
# Caka na admina, nie na healthcheck: healthcheck backendu prejde, len co
# nabehne web vrstva, kym `EtaskRunner` este zaklada ucty a importuje siete
# (rovnaka past ako v up.sh, commit c84a02d).
set -eu

apk add --no-cache -q bash curl >/dev/null

URL="${PF_URL:-http://backend:8080}"
PASS="${PF_PASS:-password}"

printf 'setup: waiting for the admin account'
i=0
until [ "$(curl -s -o /dev/null -w '%{http_code}' -m 5 -u "super@netgrif.com:$PASS" "$URL/api/auth/login" || true)" = 200 ]; do
  i=$((i + 1))
  [ "$i" -gt 100 ] && { echo; echo "setup: super@netgrif.com cannot sign in, see: docker compose logs backend"; exit 1; }
  printf .
  sleep 3
done
echo " ok"

cd /etask-configuration
python tools/pfsync.py --sync

cat <<EOF

  eTask is running.

  portal   http://localhost:${FRONTEND_PORT:-4200}    super@netgrif.com / $PASS
  e-mail   http://localhost:${MAILPIT_PORT:-8025}

EOF
