# Overovanie: prečo v tomto poradí

Bežiaci stack (bez neho sa `pfcheck` nemá čoho pýtať):

```bash
etask-configuration/tools/up.sh             # alebo --docker, RUNBOOK 12
```

Po každej zmene siete:

```bash
cd etask-configuration
python3 tools/pflint.py processes/      # 0,3 s  štruktúra, tiché pasce, grid
python3 tools/pfgroovy.py processes/    # 3 s    syntax Groovy
python3 tools/pfi18n.py processes/      #        každý viditeľný text má preklad
python3 tools/pfview.py                 #        vykreslí to frontend?
python3 tools/pfsync.py --sync          #        import do enginu + role
python3 tools/<app>check.py             #        appka robí to, čo má
```

## Prečo `pfsync` a nie reštart

**`NetRunner` importuje sieť len keď v databáze chýba.** Po zmene existujúceho
XML sa pri štarte nestane nič: engine ďalej drží starý model, `LATEST` mieri na
neho a nové casy z neho vznikajú. Nikde sa to neohlási.

`pfsync` porovná každé XML s tým, čo engine naozaj drží
(`GET /api/petrinet/{id}/file` vracia naimportované XML bajt za bajtom),
rozdielne prežene cez `pfcheck` a potom pridelí role cez `pfseed`.

## Čo overuje `pfview`

Jediná kontrola vrstvy 3. Sieť sa naimportuje, aj keď si vypýta
`<component><name>` alebo `<property key>`, ktoré frontend nečíta — Angular to
ticho zahodí a vykreslí default. Rovnako ticho zmizne pole, ktorého typ chýba
v našej kópii knižničného resolvera. Inventár sa číta z `node_modules/@netgrif`
pri každom spustení, nie zo zoznamu v kóde.

## Role a verzie

* Rola má `stringId` **per verziu siete** → po re-importe prideľ role znova
  (`pfsync --sync` to robí; ručne `python3 tools/pfseed.py`).
* Potom sa **odhlás a prihlás**: prihlásená session drží staré `stringId`, takže
  zakladanie casu vráti 403, hoci cez API tomu istému účtu prejde.
* Keď `pfseed` ohlási užívateľa ako nečitateľného (500 z `/api/user/search`), sú
  to osirelé role po zlyhanom importe — `python3 tools/pfseed.py --repair`.
* **Case si drží verziu siete, v ktorej vznikol** vrátane rozloženia formulára.
  Po zmene testuj na novom case.

## Ground truth

Nikdy neoznačuj sieť za hotovú bez importu. Import endpoint pri chybe vracia
holé `{"status":500}` **bez dôvodu** — príčina je len v logu servera a `pfcheck`
ju z neho vytiahne. Engine navyše odmietnutie akcie **nehlási HTTP kódom**:
`finish` blokovaný akciou v `phase="pre"` vráti 200 a dôvod dá do tela ako
`error`. Test, ktorý sa pozerá na stavový kód, taký blok prehliadne.

Keď si offline nástroj a engine odporujú, **chyba je v nástroji** — oprav nástroj
a spusti `tools/pftest.sh`. Stalo sa to dvakrát pri stavbe `pfgroovy`.
