# Meracie nástroje

> Rozbeh stacku je `tools/up.sh` (jeden príkaz, idempotentný).
> Petriflow nástroje sú v `README-petriflow-tools.md`.
> Recepty na bežné úlohy sú v `../docs/RUNBOOK.md`.


Čistý Node, žiadne závislosti (`sassc.js` si berie `sass` z frontendového `node_modules`).
Postavené preto, že pri práci s cudzou knižnicou sa **kaskáda ani kontrast nedajú odhadnúť** —
a `ng build` je na spätnú väzbu príliš pomalý.

`sassc.js` si frontend nájde sám ako súrodenca (`../../etask-frontend-starter`).
Prepnúť sa dá, ak sa presunie:

```bash
FE_ROOT=C:/path/to/frontend node tools/sassc.js ...
```

## `sassc.js` — kompilácia SCSS ako to robí Angular

```bash
node tools/sassc.js <fe>/src/styles.scss out.css
```

Nastaví `loadPaths` a vlastný importer pre `~`, takže knižničné `@import "quill/..."` a
`~node_modules/...` prejdú. Vypíše `OK bytes=N` alebo `FAIL` s riadkom.

## `cascade.js` — kto vyhrá kaskádu

```bash
node tools/cascade.js out.css white-space ".netgrif-input .mat-hint"
node tools/cascade.js out.css background-color ".app-dark" ".panel-color:hover"
```

Vypíše všetky pravidlá, ktorých selektor obsahuje **všetky** zadané podreťazce, so
špecificitou, `!important` a poradím — a na konci `WINNER`.

Tu sa odhalilo, že dark scope re-emituje knižničné pravidlá s vyššou špecificitou, takže
override fungujúci v light v dark prehráva. Nedá sa to uvidieť čítaním.

**Pozor:** filtruje podreťazcom, takže do výpisu spadnú aj selektory, ktoré sa na daný
element neaplikujú (napr. `.netgrif-input-fix` pri filtri `.netgrif-input`). Víťaza treba
čítať v kontexte toho, ktoré triedy element reálne má.

## `contrast.js` — WCAG audit tokenov

```bash
node tools/contrast.js out.css
```

Načíta `--app-*` z `:root` a z `.app-dark`, spočíta kontrast pre definované páry vrátane
alfa kompozície a vypíše `ok` / `FAIL`. Prah je 4.5:1, okrem `--app-fg-faint` a
`--app-border-interactive`, kde je 3:1 (placeholder váha a okraj ovládacieho prvku).

Páry sú v poli `pairs` — pri pridaní tokenu treba pridať aj pár.

## `css-of.js` — skompilované CSS komponentu z knižnice

```bash
node tools/css-of.js <fe>/node_modules/@netgrif/components/esm2020/lib/panel/panel.component.mjs
```

Angular Package Format má styly ako string v `.mjs`. Toto ich vyparsuje a naformátuje.
Jediný spôsob, ako zistiť, čo komponent naozaj kreslí.

## `extract.js` — originálne zdroje knižnice

```bash
node tools/extract.js <fe>/node_modules/@netgrif/components/esm2020 \
                      <fe>/node_modules/@netgrif/components-core/esm2020  out/
```

Oba balíky majú inline sourcemapy s kompletným `sourcesContent`, takže sa dajú vytiahnuť
originálne `.ts` aj `.html` (~1094 súborov). SCSS tam nie je — na to je `css-of.js`.

Bez tohto sa knižničné šablóny čítať nedajú a človek háda.
