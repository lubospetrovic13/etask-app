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

# pflint: musi chytit prekryv v gride. Engine takú siet prijme, `pfcheck`
# prejde - a uloha sa v appke nikdy nevykresli, lebo Angular grid vyhodi
# vynimku do konzoly prehliadaca. Zvonku to vyzera na zaseknuty server.
if $PY tools/pflint.py tools/fixtures/bad-grid.xml >/dev/null 2>&1; then
  bad "pflint neoznacil bad-grid.xml (prekryv v gride)"
else
  ok "pflint chytil bad-grid.xml"
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

# pflint: styri tiche pasce, ktore engine prijme a pfgroovy neuvidi - bodka
# v kluci moznosti (Mongo zahodi ulozenie), `removeRole` (v 6.3.1 nefunguje
# a mlci) a URI cesta polozky menu mimo `uriNodes` (polozka bez karty).
if $PY tools/pflint.py tools/fixtures/bad-lint4.xml >/dev/null 2>&1; then
  bad "pflint neoznacil bad-lint4.xml (kluc s bodkou, removeRole, URI cesta)"
else
  ok "pflint chytil bad-lint4.xml"
fi

# pfi18n: chybajuci preklad je tichy - bez `name` aj bez riadku v bloku `<i18n>`
# sa zobrazi povodna hodnota, import prejde a log mlci. Fixture ma pat sposobov,
# ako to pokazit, vratane `locale="en-US"`, ktory sa naimportuje a nikdy sa
# nepouzije.
if $PY tools/pfi18n.py tools/fixtures/bad-i18n.xml >/dev/null 2>&1; then
  bad "pfi18n neoznacil bad-i18n.xml (locale en-US, chybajuci kluc aj preklad)"
else
  ok "pfi18n chytil bad-i18n.xml"
fi

# a naopak: na sietach repozitara musi byt ticho. Toto je test na FALSE
# POSITIVES - linter, ktory oznacuje funkcny kod, naucí agenta ignorovat vystup.
if $PY tools/pfi18n.py processes/sd_customer.xml processes/sd_intake.xml \
        processes/sd_menu.xml processes/sd_ticket.xml processes/sd_work_item.xml \
        >/dev/null 2>&1; then
  ok "pfi18n neoznacil prelozene siete"
else
  bad "pfi18n oznacil prelozene siete Service Desku"
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

# pfgroovy: NAE hlavicka ma aj `t.` (alias prechodu), nielen `f.`. Bez toho
# padne cela hlavicka do tela ako Groovy a nastroj hlasi chybu na sieti, ktoru
# engine naimportuje. Na startere to nepouziva ziadna siet, takze bez tejto
# kontroly by sa oprava dala nepozorovane vratit.
if $PY tools/pfgroovy.py tools/fixtures/header-transition.xml >/dev/null 2>&1; then
  ok "pfgroovy zvladol alias prechodu (t.) v hlavicke"
else
  bad "pfgroovy oznacil header-transition.xml - hlavicka s `t.` je platna"
fi

# pfapi: inventar sa nesmie rozist s enginom. Neaktualny inventar je presne ta
# chyba, kvoli ktorej cely tento subor existuje - agent siahne po neexistujucej
# metode, alebo si napise vlastnu verziu tej, ktora tam uz je.
if $PY tools/pfapi.py --check >/dev/null 2>&1; then
  ok "pfapi inventar je aktualny"
else
  bad "docs/reference/action-api.md je neaktualny - spusti: $PY tools/pfapi.py > docs/reference/action-api.md"
fi

# pfview: kontroly frontendovej vrstvy. Fixtures nesu presne tri tiche chyby -
# zastaralu kopiu resolvera, kniznicny komponent obchadzajuci vlastny a siet
# s neznamym komponentom/property. Ziadna z nich sa neprejavi na builde, takze
# jedina obrana je, ze tento nastroj na nich naozaj spadne.
if [ -d ../etask-frontend-starter/node_modules/@netgrif ]; then
  if $PY tools/pfview.py --src tools/fixtures/pfview-src \
       --nets tools/fixtures/pfview-nets >/dev/null 2>&1; then
    bad "pfview neoznacil fixtures/pfview-* - tri tiche chyby presli"
  else
    ok "pfview chytil fixtures/pfview-*"
  fi
  # Falosny pozitiv je tu drahsi nez inde: `toggle` na boolean poli je platny
  # (variant sa cita z properties) a naivny inventar ho hlasi 15x.
  if $PY tools/pfview.py >/dev/null 2>&1; then
    ok "pfview neoznacil skutocny frontend a siete"
  else
    bad "pfview oznacil platny frontend - falosny pozitiv"
  fi
else
  skip "pfview: etask-frontend-starter/node_modules chyba (npm ci)"
fi

# --- pfdoc: kapitola musi byt vyrazne lacnejsia nez cely subor -------------
#
# Cely zmysel nastroja je, ze "kapitola 4" stoji zlomok toho, co cely RUNBOOK.
# Ked sa raz rozbije parsovanie nadpisov, vypise sa bud nic (a agent si nacita
# cely subor) alebo vsetko (a neusetri sa nic) - ani jedno sa neprejavi ako chyba.
kap=$($PY tools/pfdoc.py runbook 4 2>/dev/null | wc -c)
cely=$(wc -c < ../docs/RUNBOOK.md)
if [ "$kap" -gt 200 ] && [ "$kap" -lt $((cely / 3)) ]; then
  ok "pfdoc vrati kapitolu (${kap} z ${cely} znakov)"
else
  bad "pfdoc: kapitola ma ${kap} znakov z ${cely} - parsovanie nadpisov je rozbite"
fi

# Dokumentacia je po slovensky, takze hladanie MUSI ist aj bez diakritiky -
# inak nastroj odpovie "nie je to tu" na vec, ktora tam je.
if $PY tools/pfdoc.py hladaj "polozka menu" 2>/dev/null | grep -q 'runbook'; then
  ok "pfdoc hlada bez diakritiky"
else
  bad "pfdoc: 'polozka menu' nenaslo 'položka menu' - hladanie je citlive na diakritiku"
fi

# Neznamy dokument nesmie skoncit tichym uspechom.
if $PY tools/pfdoc.py neexistuje 4 >/dev/null 2>&1; then
  bad "pfdoc: neznamy dokument vratil uspech"
else
  ok "pfdoc odmietne neznamy dokument"
fi

# --- pfnew: skelet, ktory generuje, musi prejst vlastnou retazou ------------
#
# Preco to tu je: `pfnew` je sablona pre kazdu dalsiu appku, takze chyba v nej
# sa rozmnozi. A stalo sa oboje - iniciály odvodene zo slovenskeho nazvu
# ("Skúšobná žiadosť" -> `SŽX`) neprešli vlastnou kontrolou generatora, a skelet
# ucil vzor, ktory sa medzitym ukazal ako nespravny (stav ako `text` a stav
# v nazve pripadu sa NEPREKLADAJU). Ani jedno by ziadny existujuci test
# nezachytil: generator sa nespusta, siete v repozitari su uz opravene.
#
# Generuje sa do docasneho checkoutu, aby to nesahalo na `processes/`
# ani na manifest.
tmp_new=$(mktemp -d)
trap 'rm -rf "$tmp_new"' EXIT
mkdir -p "$tmp_new/tools" "$tmp_new/processes" "$tmp_new/reference"
cp tools/pfnew.py tools/pfi18n.py tools/pflint.py tools/pfgroovy.py tools/pfapi.py \
   tools/pftestlib.py "$tmp_new/tools/"
cp ../docs/reference/action-api.md "$tmp_new/reference/"
printf '{"import":[],"bootstrapCase":[],"uriNodes":{}}\n' > "$tmp_new/processes.json"
printf '{"netScope":[],"users":[]}\n' > "$tmp_new/seed.json"

if (cd "$tmp_new" && $PY tools/pfnew.py skuska ziadost "Skúšobná žiadosť" \
      --role pracovnik >/dev/null 2>&1); then
  ok "pfnew vygeneroval appku aj zo slovenskeho nazvu"
  bad_new=0
  for nastroj in pflint pfgroovy pfi18n; do
    if ! (cd "$tmp_new" && $PY "tools/$nastroj.py" processes/ >/dev/null 2>&1); then
      bad "pfnew: vygenerovana siet neprejde cez $nastroj"
      bad_new=1
    fi
  done
  [ "$bad_new" -eq 0 ] && ok "vygenerovana siet prejde pflint, pfgroovy aj pfi18n"

  # Skelet nesmie ucit vzory, ktore su uz vyvratene: stav ako `text` a stav
  # v nazve pripadu sa neprelozia (RUNBOOK 9).
  siet="$tmp_new/processes/sk_ziadost.xml"
  if grep -q 'type="enumeration_map"[^>]*>' "$siet" \
     && grep -q '<option key="rozpisane"' "$siet"; then
    ok "skelet ma stav ako enumeration_map (prelozitelny)"
  else
    bad "skelet ma stav ako text - v anglickom portali zostane slovensky"
  fi
  if grep -q 'nazov(sk_predmet)' "$siet" && ! grep -q 'nazov(sk_predmet, "' "$siet"; then
    ok "skelet nedava stav do nazvu pripadu"
  else
    bad "skelet dava stav do nazvu pripadu - Case.title sa neprekladá"
  fi
  # Vygenerovany akceptacny test stavia na `pftestlib`. Ked sa rozide sablona
  # s kniznicou (premenovana funkcia, iny podpis), prejavi sa to az u toho, kto
  # si novu appku zalozi - a prejavi sa to ako "test nejde spustit".
  if (cd "$tmp_new/tools" && $PY -c "
import importlib.util, sys
sys.path.insert(0, '.')
spec = importlib.util.spec_from_file_location('gen', 'skuskacheck.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
sys.exit(0 if hasattr(m, 'main') else 1)
" >/dev/null 2>&1); then
    ok "vygenerovany test sa importuje a sedi s pftestlib"
  else
    bad "vygenerovany test sa nedá naimportovat - sablona v pfnew sa rozisla s pftestlib"
  fi

  if grep -q 'pripoj_do_uzla' "$tmp_new/processes/sk_menu.xml"; then
    ok "skelet menu dorovnava URI uzol aj pri nezmenenej polozke"
  else
    bad "skelet menu nedorovnava URI uzol - po vymene ES indexu bude priecinok prazdny"
  fi
else
  bad "pfnew zlyhal na slovenskom nazve appky"
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
