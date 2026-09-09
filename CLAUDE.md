# eTask — pravidlá pre AI agenta

Petriflow-first aplikačný stack. **Aplikačná logika patrí do Petriflow sietí, nie
do Javy a nie do Angularu.** Framework je ~5 500 riadkov, siete ~7 500 — ten
pomer je zámer.

## Než začneš čokoľvek meniť

**Začni `etask-configuration/reference/cheatsheet.md`.** Je to jedna strana:
postup, osem rozhodnutí, ktoré určujú, či to bude fungovať, a zoznam toho, čo
mlčí. Dokumentácia tohto repozitára má 3 700 riadkov a načítať ju celú pred
prvým riadkom kódu je najväčšia jednotlivá položka nákladu na jednu appku —
pričom väčšina z nej odpovedá na otázku, ktorú v danej úlohe nikto nepoloží.
Cheatsheet má v pravom stĺpci napísané, kde presne je zvyšok, keď ho budeš
potrebovať.

Ak sa úloha týka Petriflow sietí, procesov, akcií, oprávnení alebo formulárov,
**načítaj skill `petriflow`**. Je v `.claude/skills/petriflow/SKILL.md` a obsahuje
rozhodovací postup, tiché pasce a odkaz na inventár extension pointov.

**Pre bežné úlohy je hotový recept v `etask-configuration/docs/RUNBOOK.md`** —
neimprovizuj, keď tam je overený postup. Pokrýva to, čo sa na tomto repozitári
reálne žiada:

| úloha | recept |
|---|---|
| rozbehať appku | `etask-configuration/tools/up.sh` (RUNBOOK 1) |
| nová sieť / aplikácia | RUNBOOK 2 |
| logika v Jave volaná z Petriflow | RUNBOOK 3 |
| karta a priečinok v bočnom menu | RUNBOOK 4 |
| úprava vizuálu, téma | RUNBOOK 5 |
| nový field komponent | RUNBOOK 6 |
| noví používatelia a roly | RUNBOOK 7 |
| anonymný / verejný prístup | RUNBOOK 8 |
| dvojjazyčná appka (SK + EN) | RUNBOOK 9 |

Skoro každá z nich má pascu, ktorá sa neprejaví ako chyba — chýbajúci JWT kľúč
vracia 401 bez správy, re-import siete ticho odoberie roly, `nc-task-list`
nezobrazí vlastné polia a build o tom mlčí. Tie pasce sú v RUNBOOKu pri
príslušnom kroku.

## Tri vrstvy

```
1. Petriflow XML          ← default. Stav, prechody, dáta, oprávnenia case-u.
2. Custom action delegate ← I/O, cudzie API, výpočet nevyjadriteľný v akcii.
3. Framework/runtime kód  ← len render, HTTP layer, a čo engine neposkytuje.
```

**Nikdy nezačínaj na vrstve 3.** Prechod nižšie musí byť odôvodnený vetou, ktorá
povie, ktoré primitívum na vyššej vrstve chýba. Ak ju nedokážeš napísať, problém
patrí vyššie.

Vrstva 2 nie je záchranná brzda — **je to miesto, kde rastie jazyk**. Metóda
pridaná do `EtaskActionDelegate` je nové Petriflow primitívum, volateľné menom
z každej siete. Keď ten istý Groovy píšeš v druhej sieti, presuň ho tam.

## Pred písaním novej metódy

Otvor `etask-configuration/reference/action-api.md` — generovaný inventár 169
metód enginu plus vlastných metód projektu, volateľných z akcie menom.

Existujúcu metódu nepíš znova. Delegát je dynamický, takže preklep prejde
parserom aj importom a spadne až za behu; tento zoznam je jediná obrana. Vznikol
preto, že bez neho bola postavená horšia verzia už existujúceho extension pointu
— podrobne v `etask-configuration/docs/AI_STARTER_ANALYSIS.md`, časť 0.

## Nová aplikácia

```bash
cd etask-configuration
python3 tools/pfnew.py mojaapp ziadost "Žiadosť o niečo" --role pracovnik
```

Vygeneruje sieť, menu sieť so zobrazeniami a stĺpcami, doplní `processes.json`
a `seed.json` a napíše akceptačný test proti bežiacemu enginu. Skelet už
obsahuje vzory, ktoré sa inak vymýšľajú znova — stavové pole s `immediate`,
názov prípadu začínajúci stavom, deväť argumentov `createOrUpdateMenuItem`,
`allowedNets` kvôli stĺpcom, read arc zo sinku. Dopisuje sa domenová logika,
nie appka.

Ručne je to `cp examples/skeleton.xml processes/mojaapp.xml` a zápis do
manifestu. Toto je celý postup. **Žiadny zásah do Javy ani do `pom.xml`** — inak by stack
protirečil vlastnému pravidlu, že aplikačná logika patrí do Petriflow. `NetRunner`
číta `processes.json` a identifikátor si berie z `<id>` v XML.

Manifest nesie aj `bootstrapCase` (siete, ktorých má pri štarte existovať jeden
case — typicky tá, čo stavia zobrazenia menu) a `uriNodes` (ikona a viditeľnosť
karty v bočnom menu). Service Desk je príkladová aplikácia postavená len na
týchto troch sekciách; runtime ho nepozná po mene a odstráni sa zmazaním sietí
a ich riadkov v manifeste.

## Overovanie

Po zmene siete, v tomto poradí:

```bash
cd etask-configuration
python3 tools/pflint.py processes/                 # 0,3 s
python3 tools/pfgroovy.py processes/              # 3 s
python3 tools/pfi18n.py processes/                # každý viditeľný text má preklad
python3 tools/pfview.py                           # frontend vykreslí, čo sieť pýta
python3 tools/pfsync.py --sync                    # import + role, len čo sa rozišlo
```

`pfi18n` je v reťazi preto, že chýbajúci preklad je **tichý**: bez atribútu
`name` aj bez riadku v bloku `<i18n>` sa zobrazí pôvodná hodnota a appka vyzerá
funkčne — len je jednojazyčná. Portál sa pritom prepína medzi SK a EN, takže
appka bez prekladov je polovica preloženej obrazovky. Recept je RUNBOOK 9.

**Ground truth je bežiaci engine.** Import endpoint pri chybe vracia holé
`{"status":500}` bez dôvodu — príčina je len v logu servera. Bez importu do
enginu sieť nie je overená.

`pfsync` je ten import: porovná každé XML s tým, čo engine naozaj drží
(`GET /api/petrinet/{id}/file` vracia naimportované XML bajt za bajtom),
rozdielne prežene cez `pfcheck` a potom prideli role cez `pfseed`. Robí to isté
ako tie dva nástroje ručne, ale len pre to, čo sa naozaj zmenilo — a hlavne ti
povie, keď si zabudol.

**Prečo na tom záleží viac, než sa zdá:** `NetRunner` importuje sieť len keď
v databáze **chýba**. Po zmene existujúceho XML sa pri starte nestane nič —
engine ďalej drží starý model, `LATEST` mieri na neho a **nové casy z neho
vznikajú**. Nikde sa to neohlási a v appke to vyzerá tak, že zmena nefunguje.
`tools/up.sh` preto `pfsync --sync` volá sám po starte backendu.

Dve veci, ktoré z toho vyplývajú a stoja každého aspoň jedno ladenie:

* **Case si drží verziu siete, v ktorej vznikol.** Nové prechody a polia doň
  nepribudnú. Kto po zmene testuje na starom case, testuje starý model.
* **Po pridelení rolí sa treba odhlásiť a prihlásiť.** Prihlásená session drží
  staré `stringId` rolí, takže zakladanie casu vráti **403**, hoci cez API tomu
  istému účtu prejde.

`pfview` je to isté pre vrstvu 3, kde `pfsync` ekvivalent nemá: sieť sa
naimportuje aj vtedy, keď si vypýta komponent, ktorý frontend nevie vykresliť.
Angular v tom prípade **nič nenahlási** — vykreslí default alebo prázdne miesto.
Inventár si nástroj číta z `node_modules/@netgrif` pri každom spustení, takže
po povýšení knižnice odpovedá podľa nej, nie podľa zoznamu napísaného rukou.
Chytá tri veci: zastaralú kópiu knižničnej šablóny (nový typ poľa sa v nej
neobjaví a pole zmizne), knižničný komponent použitý namiesto vlastného
(`<nc-task-list>` — najdrahšia chyba v histórii tohto frontendu) a
`<component>` alebo `<property key>`, ktoré nikto nečíta.

Keď si offline nástroj a engine odporujú, **chyba je v nástroji**. Oprav nástroj
a spusti `tools/pftest.sh`.

## Čo nerobiť

* Nepridávať Angular komponent na to, čo sa dá vyjadriť v sieti.
* Nepísať Java servis skôr, než je overené, že delegát to nevie.
* Nedôverovať schéme z hlavičky siete — runtime sa od nej odlišuje.
* Nekontrolovať poradie podelementov `<data>` v nástrojoch (tri zdroje pravdy si
  odporujú, siete porušujú schému a importujú sa).
* Nespúšťať `pfcheck` ani `pfsync --sync` na produkciu — importujú novú verziu
  siete.
* Nezavesiť read-only pohľad na read arc z miesta, ktoré nejaký prechod
  konzumuje. Odmietnuté `finish` na tom prechode tú úlohu zmaže a už ju
  neobnoví (`docs/PETRIFLOW_LEARNINGS.md`, B8b).

## Čerstvý checkout

```bash
etask-configuration/tools/up.sh          # kompletný stack, idempotentne
```

`up.sh` volá `bootstrap.sh` sám. Keď treba len kľúč a nič viac:

```bash
etask-configuration/tools/bootstrap.sh
```

Vygeneruje JWT podpisový kľúč (je gitignored, takže po `git clone` chýba) a vypíše
zvyšok postupu. Bez kľúča engine nepodpíše anonymnú session a **verejné formuláre
vracajú 401** bez chybovej správy, ktorá by to s kľúčom spojila.

`EtaskRunner` pri každom starte skontroluje bezpečnostnú pozíciu — default heslo
admina, vytvorené testovacie účty, chýbajúci kľúč — a nájdené veci vypíše ako
WARN. Keď to v logu vidíš, nie je to šum.

## Prostredie

* Java **11** (nie 17, nie 21 — Groovy 3 na JDK 21 padne).
* `LANG=C.UTF-8` je povinné, inak import procesu s diakritikou v názve zhodí
  `InvalidPathException`.
* `certificates/private.der` je gitignored. Bez neho engine nepodpíše anonymnú
  session a **verejné formuláre vrátia 401** — po čerstvom checkoute ho treba
  vygenerovať (postup v `etask-configuration/docs/SERVICE_DESK.md`).
