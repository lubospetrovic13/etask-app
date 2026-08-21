#!/usr/bin/env bash
#
# pftest - regresia nastrojov samotnych.
#
# Nastroj, ktoremu sa neda verit, je horsi nez zadny: naucí agenta ignorovat
# vystup. Fixtures preto nie su ukazky, ale test - kazdy nastroj MUSI na
# rozbitej sieti zlyhat a na platnej prejst.
#
# Historia, preto to existuje: pfgroovy pri prvom spusteni hlasil 47 chyb na
# sietach, ktore engine bez namietky skompiluje. Dvakrat. Prvy raz preto, ze
# NAE hlavicka akcie nie je Groovy, druhy raz preto, ze samostatny parser nema
# classpath enginu. Bez tohto testu by to nikto nezachytil.
#
#   tools/pftest.sh                          # offline nastroje
#   tools/pftest.sh --log /cesta/backend.log # aj pfcheck proti enginu

set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

LOG_ARG=()
[ "${1:-}" = "--log" ] && { LOG_ARG=(--log "$2"); shift 2; }

fail=0
ok() { printf '  OK   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fail=$((fail + 1)); }

echo "pftest: offline nastroje"

# pflint: musi chytit nedeklarovanu rolu
if python3 tools/pflint.py tools/fixtures/bad-role.xml >/dev/null 2>&1; then
  bad "pflint neoznacil bad-role.xml"
else
  ok "pflint chytil bad-role.xml"
fi

# pflint: nesmie oznacit platne siete
if python3 tools/pflint.py processes/ >/dev/null 2>&1; then
  ok "pflint neoznacil platne siete"
else
  bad "pflint oznacil platne siete v processes/ - falosny pozitiv"
fi

# pfgroovy: musi chytit rozbite Groovy
if python3 tools/pfgroovy.py tools/fixtures/bad-groovy.xml >/dev/null 2>&1; then
  bad "pfgroovy neoznacil bad-groovy.xml"
else
  ok "pfgroovy chytil bad-groovy.xml"
fi

# pfgroovy: nesmie oznacit 90 akcii, ktore engine skompiluje
if python3 tools/pfgroovy.py processes/ >/dev/null 2>&1; then
  ok "pfgroovy neoznacil platne akcie"
else
  bad "pfgroovy oznacil akcie, ktore engine skompiluje - falosny pozitiv"
fi

if [ ${#LOG_ARG[@]} -gt 0 ]; then
  echo "pftest: pfcheck proti beziacemu enginu"
  if tools/pfcheck.sh "${LOG_ARG[@]}" tools/fixtures/ok.xml >/dev/null 2>&1; then
    ok "pfcheck naimportoval ok.xml"
  else
    bad "pfcheck nenaimportoval ok.xml"
  fi
  for f in bad-role bad-groovy; do
    if tools/pfcheck.sh "${LOG_ARG[@]}" "tools/fixtures/$f.xml" >/dev/null 2>&1; then
      bad "pfcheck prijal $f.xml"
    else
      ok "pfcheck odmietol $f.xml"
    fi
  done
else
  echo "pftest: pfcheck preskoceny (bez --log)"
fi

echo
[ "$fail" -eq 0 ] && { echo "pftest: vsetko preslo"; exit 0; }
echo "pftest: $fail zlyhani"; exit 1
