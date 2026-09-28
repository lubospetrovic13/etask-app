# Dovolenky — Petriflow aplikácia pre eTask starter

Žiadosti o dovolenku: zamestnanec podá, vedúci schválí alebo vráti, zostatok sa
kráti až schválením.

Celá aplikácia je **v Petriflow**. Nie je tu ani riadok Javy, ani Angularu —
`processes/` a jeden akceptačný test. To nie je náhoda: starter je postavený na
tom, že aplikačná logika patrí do sietí, a táto appka je dôkaz, že to platí aj
pre appku so schvaľovaním, výpočtom zostatku a dvoma rolami.

```
processes/dv_ziadost.xml     žiadosť: podanie → schválenie → vybavené
processes/dv_menu.xml        zobrazenia v bočnom menu
tools/dvcheck.py             akceptačný test proti bežiacemu enginu
app.json                     manifest appky (import, uzol menu, netScope)
```

## Inštalácia

Aplikácia sama nebeží — potrebuje eTask starter, ktorý nesie engine, frontend
a rámcový kód. Do checkoutu starteru sa nainštaluje jeho vlastným nástrojom:

```bash
cd /cesta/k/etask-app/etask-configuration
python3 tools/pfapp.py install ../examples/vacations
tools/up.sh
python3 tools/dvcheck.py
```

`pfapp.py` skopíruje siete a test a zlúči `app.json` do `processes.json`
a `seed.json`. Prečo nástroj a nie „skopíruj a dopíš riadok": manifest má štyri
sekcie, ktoré musia sedieť dokopy, a keď jedna chýba, **nič to nepovie** —
appka sa naimportuje a karta v menu vedie do prázdna, alebo karta je a role
nikto nemá. To je presne ten druh ticha, ktorý sa hľadá pol dňa.

Odinštalovanie je `python3 tools/pfapp.py remove dovolenky`.

## Role

`app.json` **nikomu role nepridelí**. Kto má byť `zamestnanec` a kto `veduci`,
je rozhodnutie nasadenia, nie aplikácie. Po inštalácii sa to dopíše do
`seed.json` v starteri a spustí `python3 tools/pfseed.py`.

Karta v bočnom menu je viditeľná pre `zamestnanec` a `veduci`; kto nemá ani
jednu, appku nevidí.

## Dvojjazyčnosť

Siete majú byť slovensky aj anglicky. Kontrola je v starteri:

```bash
python3 tools/pfi18n.py processes/dv_ziadost.xml processes/dv_menu.xml
```

Chýbajúci preklad sa **neprejaví nijako** — zobrazí sa pôvodná hodnota a appka
vyzerá funkčne, len je jednojazyčná. Postup je v starteri, `docs/RUNBOOK.md`,
časť 9.

## Overovanie

V tomto poradí, z checkoutu starteru:

```bash
python3 tools/pflint.py   ../examples/vacations/processes/
python3 tools/pfgroovy.py ../examples/vacations/processes/
python3 tools/pfi18n.py   ../examples/vacations/processes/
python3 tools/pfsync.py --sync
python3 tools/dvcheck.py
```

**Ground truth je bežiaci engine.** Import endpoint pri chybe vracia holé
`{"status":500}` bez dôvodu — príčina je len v logu servera. Bez importu sieť
nie je overená.
