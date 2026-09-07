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

# Python: `python3` na Windows (Git Bash) ukazuje na WindowsApps alias, ktory
# len vypise "Python was not found" a vrati nenulovo - takze kazda kontrola
# nizsie by "zlyhala" bez toho, aby sa vobec spustila. Preto sa hlada aj
# `python` a `py -3`, a diakritika sa nesmie zlomit na cp1252.
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import sys" >/dev/null 2>&1; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ] && command -v py >/dev/null 2>&1 && py -3 -c "import sys" >/dev/null 2>&1; then
  PY="py -3"
fi
[ -n "$PY" ] || { echo "python sa nenasiel (skusal som python3, python, py -3)" >&2; exit 2; }
export PYTHONIOENCODING=utf-8

cd "$(dirname "$0")/.." || exit 2

LOG_ARG=()
[ "${1:-}" = "--log" ] && { LOG_ARG=(--log "$2"); shift 2; }

fail=0
ok() { printf '  OK   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1"; fail=$((fail + 1)); }
skip() { printf '  SKIP %s\n' "$1"; }

echo "pftest: offline nastroje"

# pflint: musi chytit nedeklarovanu rolu
if $PY tools/pflint.py tools/fixtures/bad-role.xml >/dev/null 2>&1; then
  bad "pflint neoznacil bad-role.xml"
else
  ok "pflint chytil bad-role.xml"
fi

# pflint: nesmie oznacit platne siete
if $PY tools/pflint.py processes/ >/dev/null 2>&1; then
  ok "pflint neoznacil platne siete"
else
  bad "pflint oznacil platne siete v processes/ - falosny pozitiv"
fi

# pflint: musi chytit preklep vo volani metody delegata. Toto je jediny
# nastroj, ktory to chyti - engine to naimportuje bez namietky, lebo delegat je
# dynamicky, a za behu vrati HTTP 200 a akciu potichu zhodi.
if $PY tools/pflint.py tools/fixtures/bad-call.xml >/dev/null 2>&1; then
  bad "pflint neoznacil bad-call.xml (preklep vo volani delegata)"
else
  ok "pflint chytil bad-call.xml"
fi

# pfgroovy: musi chytit rozbite Groovy
if $PY tools/pfgroovy.py tools/fixtures/bad-groovy.xml >/dev/null 2>&1; then
  bad "pfgroovy neoznacil bad-groovy.xml"
else
  ok "pfgroovy chytil bad-groovy.xml"
fi

# pfgroovy: nesmie oznacit 90 akcii, ktore engine skompiluje
if $PY tools/pfgroovy.py processes/ >/dev/null 2>&1; then
  ok "pfgroovy neoznacil platne akcie"
else
  bad "pfgroovy oznacil akcie, ktore engine skompiluje - falosny pozitiv"
fi

# pfapi: inventar sa nesmie rozist s enginom. Neaktualny inventar je presne ta
# chyba, kvoli ktorej cely tento subor existuje - agent siahne po neexistujucej
# metode, alebo si napise vlastnu verziu tej, ktora tam uz je.
if $PY tools/pfapi.py --check >/dev/null 2>&1; then
  ok "pfapi inventar je aktualny"
else
  bad "reference/action-api.md je neaktualny - spusti: $PY tools/pfapi.py > reference/action-api.md"
fi

if [ ${#LOG_ARG[@]} -gt 0 ]; then
  echo "pftest: pfcheck proti beziacemu enginu"
  if tools/pfcheck.sh "${LOG_ARG[@]}" tools/fixtures/ok.xml >/dev/null 2>&1; then
    ok "pfcheck naimportoval ok.xml"
  else
    bad "pfcheck nenaimportoval ok.xml"
  fi
  # bad-call.xml tu ZAMERNE nie je: engine ho prijme (dynamicky dispatch),
  # takze od pfcheck sa to cakat neda a je to dolezite vedet.
  for f in bad-role bad-groovy; do
    if tools/pfcheck.sh "${LOG_ARG[@]}" "tools/fixtures/$f.xml" >/dev/null 2>&1; then
      bad "pfcheck prijal $f.xml"
    else
      ok "pfcheck odmietol $f.xml"
    fi
  done

  # pfseed: po aplikovani musi druhy beh nahlasit nulu zmien. Neidempotentny
  # seed je horsi nez zadny - agent by po kazdom behu videl iny stav.
  seed_out=$($PY tools/pfseed.py 2>&1)
  if [ $? -eq 0 ]; then
    if $PY tools/pfseed.py --dry-run 2>&1 | grep -q "zmien 0"; then
      ok "pfseed je idempotentny"
    else
      bad "pfseed nie je idempotentny - druhy beh hlasi zmeny"
    fi
  # Vsetky zlyhania su "uzivatel neexistuje" -> cudzia instancia, nie rozbity
  # pfseed. Keby to hlasilo FAIL, agent sa naucí vystup ignorovat a potom
  # prehliadne aj skutocne zlyhanie. Pozor na uplnost zoznamu tokenov: kym tu
  # chybal NECITATELNY, tento test by osirele role zamlcal ako "cudzia instancia".
  elif seed_missing=$(grep -c 'NENAJDENY' <<<"$seed_out")
       seed_failed=$(grep -cE 'NENAJDENY|NECITATELNY|CHYBA' <<<"$seed_out")
       [ "$seed_missing" -gt 0 ] && [ "$seed_failed" -eq "$seed_missing" ]; then
    skip "pfseed: uzivatelia zo seed.json na tejto instancii nie su"
  else
    bad "pfseed zlyhal (osirele role? spusti tools/pfseed.py --repair)"
  fi
else
  echo "pftest: pfcheck preskoceny (bez --log)"
fi

echo
[ "$fail" -eq 0 ] && { echo "pftest: vsetko preslo"; exit 0; }
echo "pftest: $fail zlyhani"; exit 1
