# Nástroje na Petriflow siete

> Stack sa rozbieha cez `tools/up.sh`. Recepty na bežné úlohy (menu, používatelia,
> anonymný prístup, téma, vlastné komponenty) sú v `../docs/RUNBOOK.md`.


Tri kroky, každý má vlastný dôvod existovať. Poradie je od najrýchlejšieho
k najspoľahlivejšiemu:

```
pflint.py     XML: štruktúra, odkazy, tiché pasce      ~0,3 s   bez závislostí
pfgroovy.py   Groovy v akciách: syntax                  ~3 s    JDK + groovy jar
pfcheck.sh    import do bežiaceho enginu = ground truth ~5 s    bežiaci engine
pfseed.py     procesné role do deklarovaného stavu     ~5 s    bežiaci engine
pfapi.py      inventár extension pointov (generátor)   ~2 s    jar enginu
pftest.sh     regresia nástrojov samotných
```

Prečo tri a nie jeden: **každý vidí niečo, čo ostatné nie.** `pflint` nevie
parsovať Groovy, lebo je to text v CDATA. `pfgroovy` nevie, čo engine prijme,
lebo dialekt sa z XML zistiť nedá. `pfcheck` vie všetko, ale potrebuje bežiaci
engine a databázu, takže pri iterácii nad sieťou je najdrahší.

**Ground truth je `pfcheck`.** Keď si offline nástroj a engine odporujú, pravdu
má engine a chyba je v nástroji. Stalo sa to dvakrát pri stavbe `pfgroovy` —
hlásil 47 chýb na sieťach, ktoré engine skompiluje bez námietky. Preto existuje
`pftest.sh`.

---

## pflint.py — statická kontrola XML

```bash
python3 tools/pflint.py processes/
python3 tools/pflint.py --strict processes/   # aj upozornenia končia nenulovo
```

Bez závislostí, len štandardná knižnica Pythonu 3.

### Čo kontroluje a prečo práve to

Petriflow akcie sú Groovy v CDATA vnútri XML. Nič ich pred behom neskontroluje —
ani XSD, ani kompilátor. Chyba sa preto prejaví až za behu a **často ticho**:
akcia spadne v strede, časť zmien je zapísaná, zvyšok nie, a v odpovedi nie je nič.

Linter hľadá presne tie tichosti. Každé pravidlo stálo aspoň jedno kolo ladenia
a je zdokumentované v `docs/PETRIFLOW_LEARNINGS.md`.

| pravidlo | čo sa stane bez toho |
|---|---|
| `unsafe-nav-property` | `?._id` vyhodí `MissingPropertyException` a **zhodí celú akciu v strede** |
| `findcase-stringid` | `findCase { it.stringId… }` vráti vždy null, v logu len INFO |
| `async-swallows` | `async.run` výnimku spolkne — cieľový case zostane prázdny bez stopy |
| `button-reads-text` | button číta editovateľné textové pole bez `immediate` → prečíta prázdno |
| `make-singular` | `on transition` namiesto `on transitions` — ticho nič nespraví |
| `dataref-undeclared` | import spadne, alebo pole ticho zmizne z formulára |
| `role-undeclared` | import spadne na `IllegalArgumentException: Role X not found` |
| `type-textarea` | `type="textarea"` neexistuje, import spadne na NPE |
| `setdata-unknown-transition` | preklep v id transition sa prejaví až za behu |
| `unknown-call-typo` | preklep v názve metódy delegáta — **engine to prijme** a za behu vráti 200, kým akcia padne |
| `action-unknown-field` | akcia berie `f.x`, ktoré neexistuje |

### Čo NEkontroluje a prečo

**Poradie podelementov `<data>`.** Existujú tri zdroje pravdy a odporujú si:

1. oficiálna XSD v1.1.0 (`reference/petriflow.schema.v1.1.0.xsd`):
   `placeholder` → `desc` → … → `init` → … → `component`
2. NAE 6.3.1 za behu: prijme aj `component` pred `init` — všetky siete v tomto
   repozitári to tak majú a importujú sa
3. `PETRIFLOW_LEARNINGS` B5: `desc` hneď za `title`

Linter, ktorý označkuje funkčný kód, naučí agenta linter ignorovať. Poradie preto
patrí do reference knowledge, nie do kontroly.

Rovnako nekontroluje nič, čo závisí od stavu bežiacej instancie — na to je
ground truth import do enginu.

**Naopak jedna vec je tu a v `pfcheck` NIE JE:** kontrola, že volaná metóda
delegáta existuje. Delegát je dynamický, takže engine sieť s preklepom
naimportuje bez námietky. `pflint` porovnáva nahé volania s
`reference/action-api.md`, s funkciami tej siete a s lokálnymi closures; hlási
len to, čo je blízko známeho názvu (preklep), zvyšok ako `INFO`. Pred skenovaním
zahadzuje reťazcové literály — inak by slovenské „Odoslané parametre (bez
obsahu)" vypadalo ako volanie `parametre(...)`.

### Úrovne

- `ERROR` — sieť sa nenaimportuje, alebo sa naimportuje rozbitá. Exit 1.
- `WARNING` — naimportuje sa a bude sa chovať inak, než autor čaká.
- `INFO` — možno v poriadku, treba sa pozrieť. Nemá vplyv na exit kód.

### Pridanie pravidla

Pravidlo pridávaj len keď máš **overený** prípad, kedy to za behu zlyhá, a napíš
do hlásenia aj opravu. Hlásenie bez opravy je pre agenta nepoužiteľné.

---

## pfgroovy.py — syntax Groovy v akciách

```bash
python3 tools/pfgroovy.py processes/
PF_GROOVY_JAR=/cesta/groovy.jar python3 tools/pfgroovy.py processes/net.xml
```

Vyberie z XML všetky `<action>` a `<function>` a dá ich Groovy parseru. Chybu
ohlási s číslom riadku v XML.

Engine akcie pri importe **kompiluje** — sieť s rozbitým Groovy odmietne s
`Could not evaluate action[...] MultipleCompilationErrorsException`. `pfgroovy`
teda nezatvára dieru v pokrytí, **skracuje smyčku**: nepotrebuje engine ani
databázu. Pri iterácii je to rozdiel medzi sekundou a dvoma minútami.

Dve veci, ktoré tam nie sú a je to zámer:

* **NAE hlavička akcie sa odstrihne.** `pole: f.pole, iné: f.iné;` nie je Groovy —
  jednopoložková verzia sa náhodou parsuje ako labeled statement, viacpoložková
  už nie. NAE si ju prekladá sám.
* **Len fáza parsovania, nie semantická analýza.** Tento proces nemá classpath
  enginu, takže `org.bson.types.ObjectId` ani `JsonSlurper` by neresolvoval a
  hlásil by chyby v kóde, ktorý sa v enginu skompiluje. Typy a triedy sú vec
  enginu; `pfgroovy` kontroluje syntax.

Preto neodhalí `totalne_neexistujuca_metoda()` so správnymi zátvorkami — delegát
je dynamický a to spadne až za behu.

---

## pfcheck.sh — import do bežiaceho enginu

```bash
tools/pfcheck.sh --log /cesta/backend.log processes/
tools/pfcheck.sh --container etask-backend processes/sd_ticket.xml
tools/pfcheck.sh --url http://host:8080 --user a@b.c --pass x net.xml
```

Dve veci, kvôli ktorým to nie je jednoduchý `curl`:

**1. Import endpoint pri chybe vracia holé `{"status":500}` bez dôvodu.**
Skutočná príčina je výlučne v logu servera. Bez nej je hláška nepoužiteľná —
„500" nepovie, či je to preklep v id, diakritika v názve procesu alebo chýbajúca
rola. `pfcheck` preto číta log a vytiahne root cause:

```
processes/x.xml: CHYBA
    odpoved: <status>500</status> (bez detailu - endpoint dovod nevracia)
    pricina z logu:
      java.lang.IllegalArgumentException: Role neexistujuca_rola not found
```

Bez `--log` alebo `--container` to povie nahlas, že príčinu nezistí. Tichý
„500 bez detailu" je presne to, čomu sa tento nástroj snaží zabrániť.

**2. Zlyhaný import nie je atomický.** Stihne vytvoriť procesné role a priradiť
ich užívateľovi; zostane osirelý odkaz na neexistujúcu sieť a **prihlásenie
začne vracať 500**. `pfcheck` preto po každom úspešnom importe overí, že sa dá
prihlásiť — inak si rozbiješ instanciu a nevieš o tom.

Pozor: `pfcheck` do instancie **zapisuje** (importuje novú verziu siete). Nie je
to read-only kontrola, nepúšťaj ho na produkciu.

---

## pftest.sh — regresia nástrojov

```bash
tools/pftest.sh                          # offline nástroje
tools/pftest.sh --log /cesta/backend.log # aj pfcheck
```

Sedem testov nad `tools/fixtures/`: každý nástroj musí na rozbitej sieti zlyhať
a na platných sieťach v `processes/` prejsť. Druhá polovica je dôležitejšia —
falošný pozitív naučí agenta ignorovať výstup.

---

## pfseed.py — procesné role do deklarovaného stavu

```bash
python3 tools/pfseed.py              # aplikuj seed.json
python3 tools/pfseed.py --dry-run    # ukáž, čo by sa zmenilo
python3 tools/pfseed.py --repair     # vyčisti osirelé role (DB, nie REST)
```

Rola má `stringId` razené **per verziu siete**. Po každom re-importe užívateľ na
casoch novej verzie prístup stratí, aj keď „tú rolu má". Za jednu session bola
sieť importovaná 12-krát a po každom importe bolo treba role prideliť znova.

Pre človeka je to otrava, pre agenta horšie: po tretej iterácii testuje na
rozbitom stave a nevie o tom. Cieľový stav sa preto deklaruje raz v `seed.json`
pomocou **importId** (nie stringId) a `pfseed` ho dopočíta na všetkých verziách
sietí v `netScope`.

Tri pasce, ktoré rieši za teba:

**1. `role/assign` role prepisuje, nepridáva** — a berie čisté pole id, nie
`{"roleIds": [...]}`. Nekompletný zoznam znamená, že užívateľ stratí systémovú
rolu `default` a zmiznú mu všetky zobrazenia. `pfseed` preto role mimo `netScope`
zachová.

**2. REST nikde nevracia `importId` rolí siete**, len lokalizovaný názov.
Mapovanie `importId → názov` sa preto číta z lokálneho XML v `processes/`
a `názov → stringId` z `/api/petrinet/{id}/roles`. Pri nejednoznačnom názve to
povie.

**3. Zlyhaný import nechá osirelé role — a to sa cez API opraviť nedá.**
Import role vytvorí, priradí užívateľovi a sieť nechá neexistovať. Taký užívateľ
sa potom **nedá prečítať cez REST vôbec**: `/api/user/search` aj `/api/user/me`
na ňom vracajú 500, lebo serializácia rolí spadne na chýbajúcej sieti. `pfseed`
to rozpozná a pomenuje; `--repair` to opraví priamo v databáze, pretože iná
cesta neexistuje.

Overené: po zlyhanom importe (diakritika v názve procesu) mal `super` 6 osirelých
rolí a bol cez REST nečitateľný; `--repair` ho vrátil na 200.

Idempotencia je invariant, nie sľub — `pftest.sh` ju testuje: po aplikovaní musí
druhý beh nahlásiť `zmien 0`.

Pozor: `pfseed` do instancie **zapisuje**. Nepúšťaj ho na produkciu.

---

## pfapi.py — inventár extension pointov

```bash
python3 tools/pfapi.py > reference/action-api.md
python3 tools/pfapi.py --check    # neaktuálny výstup vráti 1
```

Generuje `reference/action-api.md` z jaru enginu (`javap`) a zo zdrojáku
`EtaskActionDelegate`. Generované zámerne: `ActionDelegate` má 169 unikátnych
metód v 407 pretaženiach, ručný zoznam by driftoval s verziou enginu, a nesprávny
zoznam je horší než žiadny. `--check` je preto súčasťou `pftest.sh`.
