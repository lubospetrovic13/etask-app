# Runbook: bežné úlohy na tomto repozitári

Toto je to, čo na eTasku ľudia reálne robia — v poradí, v akom to zvyknú robiť.
Každý recept má tvar **čo zmeniť → ako overiť → čo tam po ceste hryzie**, lebo
skoro každá z týchto úloh má aspoň jednu pascu, ktorá sa neprejaví ako chyba.

Petriflow ako jazyk je v `.claude/skills/petriflow/SKILL.md` a v
`docs/petriflow_reference.md`. Tu je infraštruktúra okolo.

---

## 1. Rozbehať aplikáciu

```bash
etask-configuration/tools/up.sh
```

Jeden príkaz: JWT kľúč, Java 11, docker daemon, Mongo + Elasticsearch + Redis,
build, backend. Je idempotentný — čo beží, nechá bežať.

```bash
tools/up.sh --build       # vynúti čistý rebuild
tools/up.sh --restart     # zastaví bežiaci backend a spustí znova
tools/up.sh --stop        # len zastaví backend
tools/up.sh --fresh       # zahodí databázu a začne odznova
tools/up.sh --frontend    # popri backende aj ng serve na :4200
tools/up.sh --db mojadb   # iná databáza
```

**Po zmene siete stačí `tools/up.sh` znova** — zdroje sú novšie než jar, takže
sa prestaví, backend sa **reštartuje sám** a nakoniec sa siete **dorovnajú
s enginom** (krok „Siete vs. engine“). Kým to skript nerobil, prestavil jar
a nechal bežať starý proces: pridal si sieť, dostal „už beží" a pozeral na appku
bez nej. Žiadna chybová správa, len nesedeli veci.

To dorovnanie je druhá polovica tej istej pasce a je horšia, lebo prežije aj
reštart: **`NetRunner` importuje sieť len keď v databáze chýba.** Po zmene
existujúceho XML sa pri starte nestane nič — engine ďalej drží starý model,
`LATEST` mieri na neho a **nové casy vznikajú zo starého modelu**. Presne takto
sa nová možnosť v tasku javí ako nefunkčná. `up.sh` preto na konci pustí
`tools/pfsync.py --sync`, ktorý porovná každé XML s tým, čo engine naozaj drží,
rozdielne prežene cez `pfcheck` a potom prideli role cez `pfseed`.

Keď to nechceš (napr. siete meníš ručne v appke a nechceš ich prepísať
z repozitára): `ETASK_NO_SYNC=1 tools/up.sh`.

Ak backend zabíjaš ručne, **nie `pkill -f "target/app.jar"`** — tá vzorka sedí aj
na vlastný príkazový riadok a zabiješ si shell, z ktorého to spúšťaš. Použi
`tools/up.sh --stop`.

Prihlásenie: `super@netgrif.com` / `password`.

**Prečo to je skript a nie odsek v READMe.** Každý krok má tichú pascu:

| pasca | ako sa prejaví |
|---|---|
| chýbajúci `certificates/private.der` | verejné formuláre vracajú **401**, bez správy, ktorá by to spojila s kľúčom |
| JDK 17/21 | `Unsupported class file major version` — Groovy 3 na novšej Jave padá |
| bez `LANG=C.UTF-8` | import siete s diakritikou v názve zhodí `InvalidPathException` |
| stale `target/` | Maven preskočí kopírovanie zdrojov: jar bez sietí, alebo s triedou, ktorú zdroj už nemá |
| chýbajúci Redis | Spring spadne až na session store, dlho po štarte |

### Windows: python nástroje padajú na diakritike uprostred behu

Nástroje v `tools/` píšu po slovensky a Windows konzola je `cp1252`, takže prvé
`č` alebo `→` v tlačenom výstupe zhodí celý skript:

```
UnicodeEncodeError: 'charmap' codec can't encode character 'č'
```

Nebezpečné je to tým, **kedy** to padne: nie na začiatku, ale až pri tom riadku
— takže `pfseed.py` stihne role prideliť a až potom spadne, a seedovací skript
stihne polovicu prípadov. Vyzerá to ako chyba nástroja, je to kódovanie terminálu.

```bash
PYTHONIOENCODING=utf-8 python3 tools/pfseed.py
```

A ešte jedna vec, ktorá s tým chodí v páre: v Git Bashi na Windows je `python3`
(aj `python`) obvykle **WindowsApps stub**, ktorý len otvorí Microsoft Store.
`where python` ukáže ten pravý interpreter; volaj ho plnou cestou, alebo si
nastav alias.
| sieť zmenená, nie znovu naimportovaná | engine drží starý model, nové casy z neho vznikajú, nikde ani slovo (rieši `pfsync`) |

**Na Windows (Git Bash)** má `up.sh` štyri miesta, kde sa zadrhne, a všetky
mlčia rovnako ako to ostatné:

| pasca | ako sa prejaví |
|---|---|
| `pgrep` v Git Bash neexistuje | `--restart` bežiaci backend nenájde, nezastaví ho, `mvn clean` narazí na zamknutý `app.jar` a build spadne. Zastav JVM ručne (PowerShell `Stop-Process`) |
| `JAVA_HOME` sa hľadá v `/usr/lib/jvm/*` | nenájde Windows JDK — `export JAVA_HOME="/c/Program Files (x86)/jdk-11"` pred spustením |
| python nástroje padajú na vlastnom výpise | `UnicodeEncodeError` na `→` a diakritike — `PYTHONIOENCODING=utf-8` |
| `bash` v PATH je WSL | `execvpe(/bin/bash) failed` pri volaní `.sh` z pythonu; `pfsync` to obchádza sám, inak `PFSYNC_BASH` |
| jar spustený ručne bez `-Dsun.jnu.encoding=UTF-8` | sieť s diakritikou v `<title>` sa **naimportuje do Mongu, ale jej XML sa neuloží** do `storage/uploadedModels`. `GET /api/petrinet/{id}/file` potom navždy vracia 500 a `pfsync` ju hlási ako `NEDA_SA_PRECITAT`. Rieši sa re-importom zo správne spusteného JVM |
| jar spustený ručne z koreňa repozitára | `PdfRunner` asserts na relatívne `src/main/resources/...` a **aplikácia nenaskočí** — siete sa pritom naimportujú, takže log vyzerá polovične úspešne. Jar sa spúšťa z `etask-backend-starter/` |

Obe posledné dve platia len pri ručnom spúšťaní; `up.sh` to robí správne. Preto
sa naň vyplatí držať.

`up.sh` porovnáva čas zdrojov s časom jaru a keď sú novšie, prestaví — tá tretia
pasca stála v tomto repozitári tri ladenia.

**Nespúšťať proti produkcii**, `--fresh` maže dáta. To isté platí pre `pfcheck`
a `pfseed` — importujú a prepisujú.

---

## 2. Nová aplikácia (sieť)

```bash
cd etask-configuration
cp examples/skeleton.xml processes/mojaapp.xml   # prepíš <id>, <initials>, <title>
# dopíš "mojaapp.xml" do processes.json → "import"
python3 tools/pflint.py processes/mojaapp.xml
```

**Pridanie appky Javu nevyžaduje.** `NetRunner` číta manifest a identifikátor
si berie z `<id>` v XML.

Overenie po každej zmene siete, v tomto poradí:

```bash
python3 tools/pflint.py processes/        # 0,3 s — štruktúra, tiché pasce
python3 tools/pfgroovy.py processes/     # 3 s   — syntax Groovy
tools/pfcheck.sh --log .run/backend.log processes/mojaapp.xml   # ground truth
```

**Ground truth je bežiaci engine.** Import endpoint pri chybe vracia holé
`{"status":500}` bez dôvodu — príčina je len v logu servera a `pfcheck` ju
odtiaľ vytiahne. Bez neho sieť nie je overená.

`NetRunner` importuje sieť **len keď v databáze chýba**. Po zmene existujúcej
siete ju treba nahrať znova — `tools/up.sh` to už robí sám (`pfsync`), ručne je
to `pfcheck`, alebo Nahrať proces v appke.

**Case si drží verziu siete, v ktorej vznikol.** Nové prechody a polia doň
nepribudnú, takže po re-importe testuješ na starom modeli, ak testuješ na starom
case — a nová možnosť v tasku vyzerá, že nefunguje. Nové casy sú v poriadku:
frontend si net vyžiada ako `LATEST`, takže „+“ zakladá vždy z najnovšej
naimportovanej verzie. Zosúladiť sa dá len zahodením starých casov.

```bash
python3 tools/pfsync.py            # ktoré siete sa rozišli s enginom
python3 tools/pfsync.py --sync     # dorovnať (import + role)
```

### Appka do vlastného repa (`extract`)

Starter je šablóna: framework, infraštruktúra, správa používateľov a jedna
príkladová appka. Keď v ňom vznikne klientska appka, patrí do vlastného repa:

```bash
cd etask-configuration
python3 tools/pfapp.py extract objednavky-faktury ../../etask-app-objednavky-faktury \
    --title "Objednávky a faktúry" \
    --nets fa_faktura.xml ob_objednavka.xml sc_menu.xml sc_nastavenia.xml \
    --tools sccheck.py --docs PRIRUCKA.md \
    --boot schvalovanie/sc_menu:rebuild nastavenia/sc_nastavenia:rebuild \
    --nodes schvalovanie schvalovanie/faktury schvalovanie/objednavky nastavenia \
    --scope "schvalovanie/*" "nastavenia/*" --dry-run     # najprv nasucho
```

`extract` spraví **obe strany naraz**: napíše repo appky (`app.json`,
`processes/`, `tools/`, `docs/`, `README.md`) a odoberie ju z manifestu starteru
rovnakou cestou ako `remove`. To je celý dôvod, prečo je to nástroj — manifest
má štyri sekcie v dvoch súboroch a keď jedna z nich zostane, **nič to nepovie**:
sieť je v `import` bez `uriNodes` (karta nie je vidno) alebo naopak (karta vedie
do prázdna).

Bežiace nasadenie tým nezmizne — siete v engine, prípady, položky menu ani
uzol URI sa nemažú. Keď má appku mať aj tento checkout, nainštaluj ju späť
z nového repa:

```bash
python3 tools/pfapp.py install ../../etask-app-objednavky-faktury
python3 tools/pfapp.py status     # nasadená kópia vs. zdroj
```

Inštalácia mení `processes.json` a `seed.json`. Tie zmeny sú **stav nasadenia**,
nie šablóny — do commitu šablóny nepatria.

### Premenovanie alebo odstránenie appky

Vyhodenie zo `processes.json` **nič nezmaže** — manifest hovorí, čo sa má
naimportovať, nie čo má existovať. Po premenovaní tak v instancii zostane stará
appka aj so svojou kartou a jej zobrazenia sa miešajú s novými (rovnaké názvy).
Poriadok treba spraviť v štyroch krokoch a v tomto poradí:

```bash
# 1. položky menu starej appky + ich `filter` casy   (najprv položka, potom filter)
# 2. casy starých sietí                              DELETE /api/workflow/case/{id}
# 3. samotné siete, všetky verzie                    DELETE /api/petrinet/{id}
# 4. uzol URI                                        nie je REST, viď nižšie
```

Prvé tri idú cez REST. **Uzol URI (karta v menu) nezmizne ani po zmazaní sietí** —
je to samostatný dokument v **Elasticsearchi**, nie v Mongu, a nikde sa negeneruje
znova:

```bash
curl -s "localhost:9200/etask_uri/_search?size=50"      # nájdi id podľa uriPath
# vyhoď ho z childrenId koreňa a potom zmaž
curl -s -X POST "localhost:9200/etask_uri/_update/<ROOT_ID>" -H 'Content-Type: application/json'   -d '{"script":{"source":"ctx._source.childrenId.removeIf(c -> c == params.dead)","params":{"dead":"<NODE_ID>"}}}'
curl -s -X DELETE "localhost:9200/etask_uri/_doc/<NODE_ID>"
curl -s -X POST "localhost:9200/etask_uri/_refresh"
```

Kto to preskočí, vidí v menu kartu, ktorá vedie do prázdna, a nenájde dôvod ani
v manifeste, ani v Mongu. Alternatíva je `tools/up.sh --fresh`, ktorý zahodí
všetko — vrátane toho, čo si nechať chcel.

---

## 3. Logika v Jave, volaná z Petriflow

Metóda pridaná do `EtaskActionDelegate` je **nové Petriflow primitívum** —
volateľné z akcie menom, bez importu, bez wiringu, z každej siete.

```groovy
// etask-backend-starter/src/main/groovy/com/netgrif/etask/EtaskActionDelegate.groovy
@Component
class EtaskActionDelegate extends ActionDelegate {

    /** Jedna veta, na čo to je - pfapi ju vytiahne do inventára. */
    List<String> mojePrimitivum(Object vstup, String param = null) { ... }
}
```

```groovy
// v akcii ktorejkoľvek siete
def x = mojePrimitivum(pole.value, "parameter")
```

Potom regeneruj inventár, inak o metóde nebude vedieť ani `pflint`, ani ďalší
agent:

```bash
cd etask-configuration && python3 tools/pfapi.py > docs/reference/action-api.md
```

**Najprv sa pozri do `docs/reference/action-api.md`.** Je to generovaný zoznam 169
metód enginu plus vlastných metód projektu. Bez neho tu už raz vznikla horšia
verzia extension pointu, ktorý v enginu tri roky bol — príbeh je v
`AI_STARTER_ANALYSIS.md`, časť 0.

**Cena za dynamický dispatch:** preklep v názve metódy prejde parserom aj
importom a spadne až za behu na `MissingMethodException`, keď akciu niekto
spustí. Odpoveď je HTTP 200 a v logu nič užitočné. Jediné, čo to chytí, je
`pflint` proti inventáru.

**Pravidlo promócie:** keď ten istý Groovy píšeš v druhej sieti, nepíš ho po
tretie — presuň ho do delegáta.

---

## 4. Karta a priečinok v bočnom menu

Tri nezávislé veci, ktoré sa dajú ľahko zameniť:

| čo | odkiaľ vzniká |
|---|---|
| **priečinok** (uzol stromu) | z identifikátora siete — `mojaapp/faktury` vyrobí uzol `mojaapp` |
| **ikona a viditeľnosť karty** | `uriNodes` v `processes.json` |
| **zobrazenia pod kartou** | casy procesov `filter` a `preference_filter_item`, ktoré stavia akcia siete cez `createFilterInMenu` |

Uzol URI sám o sebe **žiadne zobrazenia nenesie**. Karta bez nich existuje, ale
vedie do prázdneho panelu.

```json
// etask-configuration/processes.json
"uriNodes": {
  "mojaapp": {
    "icon": "receipt_long",
    "requiredAuthorities": [],
    "requiredProcessRoles": ["ucctovnik"]
  }
},
"bootstrapCase": ["mojaapp/mojaapp_menu"]
```

`requiredProcessRoles` sú **importId** rolí (z `<role><id>` v sieti), nie
stringId — stringId sa razí per verziu siete, takže re-import by zoznam ticho
vyprázdnil. Prázdne oboje = uzol vidí každý prihlásený.

Zobrazenia stavia sieť, lebo `createFilterInMenu` je na action delegate
a z runnera sa zavolať nedá. `BootstrapCaseRunner` len zabezpečí, že existuje
case, z ktorého sa akcia spustí. Vzor je `processes/sd_menu.xml` — vrátane
obídenia toho, že engine **nevie filter aktualizovať** (`createOrUpdateMenuItem`
volá neexistujúce `updateFilter`), takže pri zmene dopytu treba položku zahodiť
a postaviť znova.

Pozor na poradie argumentov: `createFilterInMenu("service_desk", id, nazov,
dopyt, "Case", ...)` — **prvá je URI cesta, nie identifikátor**.

**A ešte dôležitejšie: `createFilterInMenu` nevie nastaviť `allowedNets`.**
Zobrazenie potom vyzerá hotovo, ale tlačidlo „+“ v ňom vráti **„Žiadne povolené
siete“** a používateľ si case nemá ako založiť. Build ani import o tom mlčia,
zoznam sa tvári správne — vidno to až kliknutím. Na zobrazenie, z ktorého sa má
dať zakladať, použi projektovú `createOrUpdateMenuItem` so **7 argumentmi**
(iné poradie — prvé je id, až potom URI):

```groovy
createOrUpdateMenuItem(id, "mojaapp", "Case", dopyt, ikona, nazov,
                       ["mojaapp/mojaapp_ziadost"])   // <- allowedNets
```

`sd_menu.xml` túto pascu má — Service Desk sa zakladá cez verejný eForm, takže
tam „+“ nikto nepotreboval.

A ešte dve veci na tej istej položke menu, ktoré `createOrUpdateMenuItem` berie
a nikde inde sa nedajú nastaviť:

* **deviaty argument `roles`** (`[importId: "identifikator/siete"]`) obmedzí, kto
  položku v menu vôbec uvidí. Uloží sa ako `allowed_roles` s kľúčom
  `importId:identifikator` a filtruje ju drawer aj počítadlá. Nie je to
  bezpečnostná hranica — tou zostáva `perform` na prechode — je to poriadok
  v menu. Potrebné to je vtedy, keď zobrazenie typu Case ukazuje casy, ktoré
  používateľ smie *vidieť*, ale nie na nich nič robiť.
* **dialóg „Vyplňte názov prípadu“** pri „+“ sa vypína poľom
  `enable_case_title` na prechode `view` položky menu. Nie je to argument, takže
  sa dopisuje zvlášť:

```groovy
setData("view", menuItem, [
        "enable_case_title"             : ["value": false, "type": "boolean"],
        "case_require_title_in_creation": ["value": false, "type": "boolean"]
])
```

Bez toho si názov casu vymýšľa človek a zoznam vyzerá tak, ako sa komu chcelo
písať. S tým ho skladá `create` akcia siete — a vyplatí sa začať stavom, nie
skončiť ním: stĺpec Názov sa v zozname skracuje a to, čo je na konci, odpadne
prvé.

A ešte: po `createFilterInMenu` sa zápis do vlastného casu (ani `change`, ani
`setData`) neuchová — engine medzitým zakladal iné casy a výsledok zahodí.
`changeCaseProperty("title")` prežije.

### Názov položky musí byť v celom portáli jedinečný

Položky menu sú prípady **jednej** siete `preference_filter_item` pre celý
portál. Priečinok je len `parentId`, takže dva rovnaké názvy v dvoch
priečinkoch engine prijme bez slova — a pokazí to dve veci, ktoré obe mlčia:

* **Dashboard** kreslí karty naplocho, bez priečinka. Dve karty „Rozpísané
  a vrátené" sa nedajú odlíšiť a klik vedie raz sem, raz tam.
* **Kód, ktorý si položku hľadá podľa názvu**, dostane tú, ktorá v odpovedi
  prišla druhá. `dvcheck` takto kontroloval stĺpce faktúry proti očakávaniam
  dovolenky a zlyhal na appke, ktorej sa nikto nedotkol.

Preto názov nesie **domenu** („Rozpísané faktúry", nie „Rozpísané"), a kód sa
opiera o `menu_item_identifier` — id, ktoré si razíš sám, je stabilné cez
preklady a `menu_item(id)` ho vracia priamo. Kolíziu chytí `tools/sccheck.py`
kontrolou „ziadne dve zobrazenia v menu sa nevolaju rovnako".

### Prázdny priečinok: položky menu sú v Mongu, URI uzly v Elasticsearchi

Priečinok v bočnom paneli je, dá sa na ňom kliknúť — a **nie je v ňom nič**.
Cez API sa pritom všetky zobrazenia nájdu a každý používateľ ich vidí.

Dôvod je rozdelenie úložísk:

| čo | kde žije | ako sa ráta id |
|---|---|---|
| položka menu (`preference_filter_item`) | Mongo | ObjectId, prežije reštart aj prenos |
| URI uzol (priečinok) | **Elasticsearch** | id indexu, vzniká pri vytvorení uzla |

Frontend hľadá položky priečinka dopytom `uriNodeId: <id uzla>`
(`UriService.getCasesOfNode`). Keď sa ES index vymení — `up.sh --fresh`,
prenos na iný stroj, čistý volume v Dockeri — `UriNodeDataRunner` uzly vytvorí
**znova a s novými id**, kým položky v Mongu držia staré. Dopyt potom nesedí
a priečinok je prázdny. Nikde sa to neohlási: uzol existuje, položky existujú,
oprávnenia sú v poriadku.

Opravuje to primitív `pripoj_do_uzla(existing, uri)`, ktorý každá menu sieť volá
**aj vo vetve „položka je nezmenená"**:

```groovy
if (currentQuery == v.query && currentNets == wantNets && sameName) {
    nastav_zobrazenie(existing, v.nets as List, v.headers)
    pripoj_do_uzla(existing, v.uri as String)   // <- bez tohto zostane na starom uzle
    unchanged << id
    return
}
```

`createOrUpdateMenuItem` `uriNodeId` dorovnáva samo, ale do tejto vetvy sa
nedostane — dopyt, siete ani názov sa nezmenili, takže sieť položku „nechá byť".

Chytá to `tools/sccheck.py` kontrolou „priečinok faktúr má pod sebou
zobrazenia": hľadá presne tak, ako hľadá frontend, teda podľa `uriNodeId`.

### Zmena položky sa prejaví až novým prípadom menu siete

Akcia staviaca menu je v udalosti `create`, teda beží **raz za prípad**.
`pfsync --sync` naimportuje novú verziu, ale prípad pre ňu nezaloží — to robí
`bootstrapCase` pri starte backendu. Kým prípad novej verzie nie je, v portáli
je stará položka a vyzerá to, že re-import nefunguje. Bez restartu:

```bash
curl -s -X POST localhost:8080/api/workflow/case \
     -H "X-Auth-Token: $TOK" -H "Content-Type: application/json" \
     -d '{"netId":"<stringId NAJNOVSEJ verzie>","title":null,"color":""}'
```

To je presne to, čo robí `bootstrapCase`.

### Stĺpce zoznamu a vyhľadávanie podľa dátových polí

Zoznam casov ukazuje predvolene len metadáta. Vlastné stĺpce sa nastavujú
poľom `default_headers` na tom istom prechode `view` — comma-separated
`HeaderColumn.uniqueId`:

```groovy
setData("view", menuItem, ["default_headers": [
        "value": "meta-title" +
                 ",mojaapp/mojaapp_ziadost-stav_label" +
                 ",mojaapp/mojaapp_ziadost-datum_od",
        "type": "text"]])
```

Metadáta majú tvar `meta-<nieco>` (`meta-title`, `meta-creationDate`), dátové
pole `<identifikator/siete>-<idPola>`. `GroupNavigationComponentResolverService`
to prečíta a vloží ako `NAE_DEFAULT_HEADERS` do injektora práve tohto
zobrazenia, takže každé zobrazenie môže mať iné stĺpce. **Žiadny zásah do
Angularu to nepotrebuje** — je to dátové pole na prípade menu.

**Stĺpec z dátového poľa sa ale zobrazí len na zobrazení, ktoré má ten net
v `allowedNets`.** `CaseHeaderService` skladá ponuku stĺpcov z povolených sietí
a `initializeDefaultHeaderState` v nej každé `uniqueId` len **vyhľadá**; čo
nenájde, nechá prázdne a **nič nezaloguje**. Zobrazenie bez `allowedNets` teda
ukáže iba `meta-*` stĺpce, hoci `default_headers` má v dátach uložené správne
a `pfsync` aj `pfcheck` sú zelené. Vyzerá to presne ako „nastavil som stĺpce
a nefunguje to".

Overené na štyroch zobrazeniach tej istej siete — korelácia je úplná:

| zobrazenie | `allowedNets` | vykreslené stĺpce |
|---|---|---|
| Žiadosti o dovolenku | `[dv_ziadost]` | Názov, Stav, Dátum od, Dátum do |
| Rozpísané a vrátené | `[dv_ziadost]` | Názov, Stav, Dátum od, Dátum do |
| Na schválenie | `[]` | len Názov |
| Vybavené | `[]` | len Názov |

`allowedNets` sa teda oplatí dať aj zobrazeniu, z ktorého sa zakladať nemá —
inak si vyberáš medzi tlačidlom „+“ a stĺpcami.

Kde to hľadať, keď to nesedí: na položke menu (`preference_filter_item`)
`allowedNets` **nie je**. Je na naviazanom `filter` case, v poli `filter`:

```
GET /api/workflow/case/{filter_case_id}  →  immediateData[].allowedNets
```

Dve pasce pri prestavbe položky, obe tichšie než tá pôvodná:

* **Strážna podmienka musí porovnávať aj `allowedNets`, nielen dopyt.** Dopyt aj
  `allowedNets` idú do konštruktora a na existujúcej položke sa zmeniť nedajú.
  Kto porovnáva len dopyt, pridá sieť, dopyt sa nezmení — a prestavba položku
  vyhlási za nezmenenú a nechá tak. Vyzerá to, že zmena v sieti nefunguje.
* **Poradie mazania je povinné: najprv `deleteMenuItem`, potom `deleteFilter`.**
  Naopak to padne na `IllegalArgumentException: Could not find Case with id`,
  lebo `deleteMenuItem` si filter ešte raz načíta podľa id uloženého na položke.
  Referenciu na filter si drž vopred, aby si ho po zmazaní položky mal čím
  zmazať — inak ostane osirelý.

Dátové pole sa do zoznamu aj do vyhľadávania dostane, len keď má
`immediate="true"`. Vtedy ho engine indexuje do Elasticu pod `dataSet.<idPola>`
s podpoľami podľa typu:

```
dataSet.<id>.textValue          .textValue.keyword   .fulltextValue
dataSet.<id>.numberValue        .dateValue           .timestampValue
dataSet.<id>.booleanValue
dataSet.<id>.keyValue           <- enumeration_map / multichoice_map
```

**`enumeration_map` je výnimka a je to tichá pasca.** Kľúč možnosti je
v `.keyValue`; `.textValue` drží **preložené popisky, všetky jazyky naraz**
(`["Nastúpil", "Onboarded"]`). Dopyt na kľúč cez `.textValue` preto nenájde
**nikdy nič** — engine vráti 200 a prázdny zoznam, zobrazenie je prázdne
a nikde sa nič nezaloguje. Overené za behu (NAE 6.3.1):

```
dataSet.stav_label.keyValue:"nastupil"    -> 2 prípady
dataSet.stav_label.textValue:"nastupil"   -> 0 prípadov
```

Takže priečinok „Vybavené" je obyčajný dopyt nad dátovým poľom, nie nová sieť:

```groovy
def query = "processIdentifier:\"mojaapp/mojaapp_ziadost\"" +
            " AND dataSet.stav_label.keyValue:(\"schvalena\" OR \"zamietnuta\")"
```

Pozor, `immediate` polia majú `initial=false`, takže sa **samy od seba stĺpcom
nestanú** — bez `default_headers` ich používateľ musí zapnúť ručne pri každom
zobrazení. To je presne to, čo vyzerá ako „nefunguje to".

Tri pasce, ktoré na tomto stáli ladenie:

* **Toto nie je to isté ako Mongo.** `findCases { it.dataSet... }` v Groovy
  akcii **nefunguje** (`MissingPropertyException`, viď `petriflow_reference.md`).
  Vyššie uvedené je Elastic dopyt vo `filter` casu, čo je iná cesta k dátam.
* **Diakritiku v dopyte neposielaj cez query string zo shellu.** Testovanie cez
  `curl ...?query=Schválená` vráti 0 výsledkov, hoci dopyt je správny — reťazec
  sa cestou zmrší. Cez JSON telo `POST /api/workflow/case/search` vráti to, čo
  má. Stálo ma to nesprávny záver, že sa dátové polia hľadať nedajú.
* **`deleteMenuItem` nechá `filter` case osirelý.** Tie sa hromadia a
  `getFilterFromMenuItem` potom vracia nesprávny z nich, takže podmienka
  „zmenil sa dopyt?" prestane platiť. Pred `deleteMenuItem` treba zavolať
  `deleteFilter(getFilterFromMenuItem(existing))`.

---

## 5. Úprava vizuálu

Knižnice sú npm závislosti pinnuté na 6.3.1. Meniť `node_modules` je zbytočné.
**Update-safe seam je téma** — `@netgrif/components` posiela SCSS ako zdroj:

```
etask-frontend-starter/src/styles/themes/_palettes.scss        farby
etask-frontend-starter/src/styles/themes/custom-themes.scss    light + dark
etask-frontend-starter/src/styles.scss                         globálne prepisy
```

Všetko, čo `nae-lib-theme` generuje, sú **globálne** pravidlá, takže sa dajú
prepísať zvonku a prežije to update knižnice — na rozdiel od zmien v šablónach.

Kaskádové pasce (celé v `FRONTEND_LEARNINGS.md`, časť B), skrátene:

* dark scope re-emituje knižničné pravidlá s **vyššou špecificitou**, takže
  prepis, ktorý funguje v light, v dark nemusí;
* knižničné `background` shorthandy s `!important` resetujú `background-image`;
* Material 13 je **pre-MDC** — `define-dark-theme` vracia plochy dvakrát;
* `nae.json` → `theme.pallets` je **mŕtva konfigurácia**, nič nerobí.

Nástroje na meranie kaskády sú v `tools/` (`cascade.js`, `contrast.js`,
`css-of.js`) — `tools/README.md` hovorí, kedy ktorý.

### Dve vrstvy tokenov

Farby ani veľkosti sa **nepíšu ručne**. Od septembra 2026 sú v dvoch súboroch
a to rozdelenie je jediné, čo drží dizajn a aplikáciu oddelene:

| súbor | čo je v ňom | kto ho mení |
|---|---|---|
| `src/styles/_n-tokens.scss` | `--n-*` — prepis Netgrif Design System z Figmy | **generátor**, nie človek |
| `src/styles/_tokens.scss` | `--app-*` — na čo tie tokeny appka používa | človek, a meria pri tom kontrast |

```bash
cd etask-configuration
curl -H "X-Figma-Token: $FIGMA_TOKEN"      "https://api.figma.com/v1/files/DvZiv1wChuQM3Mpr4XjwHH" -o .run/figma-tokens.json
python3 tools/figmatokens.py .run/figma-tokens.json --kontrola   # čo si v DS odporuje
python3 tools/figmatokens.py .run/figma-tokens.json     -o ../etask-frontend-starter/src/styles/_n-tokens.scss
node tools/sassc.js ../etask-frontend-starter/src/styles.scss .run/out.css
node tools/contrast.js .run/out.css                              # musí byť zelené
```

`_n-tokens.scss` zámerne nevie o eTasku — dá sa presunúť do
`@netgrif/components` bez zmeny, keby sa tam dizajn raz mal implementovať.

**Odtieň z rampy sa vyberá meraním, nie okom.** Neutrálna rampa DS nemá stupeň
medzi 2.60:1 a 4.84:1 na bielej, takže placeholder (`--app-fg-faint`) sa berie
z alfa stupnice. Kto vymení odtieň bez `contrast.js`, dostane formulár bez
viditeľných polí — presne ten, kvôli ktorému `--app-border-interactive` vznikol.

**`contrast.js` rozbaľuje `var()`.** Bez toho by od zavedenia `--n-*` vypisoval
samé `(unparsed)` a vyzeralo by to, že je všetko v poriadku.

---

## 6. Nový field komponent

```
EtaskTaskPanelComponent → EtaskTaskContentComponent
  → EtaskFieldComponentResolverComponent → vlastné polia
```

Resolver je **hardcoded `ngSwitch` bez registry**, takže vlastný komponent
znamená vlastniť šablónu resolvera. Aktuálne vlastníme `boolean` a `button`.

Konfigurácia ide cez `<component><properties>`, ktoré knižnica ignoruje, ale
`DataField.component` ich prenesie:

```xml
<component>
    <name>toggle</name>
    <properties><property key="variant">section</property></properties>
</component>
```

### Uloženie poľa bez odkliknutia (`saveWhileTyping`)

Pole sa štandardne uloží, **až keď stratí fokus**. Nie je to rozhodnutie
ukladacej vrstvy, je to jeden riadok knižnice:

```
AbstractDataFieldComponent:  new FormControl('', {updateOn: 'blur'})
```

Reťaz je `input` → (blur) → `FormControl.valueChanges` → `DataField.value` →
`TaskDataService.updateTaskDataFields()` → `POST /api/task/{id}/data`. Medzi DOM
a serverom teda netreba meniť nič — hodnota len do blur neopustí input. Ten
`FormControl` vzniká v privátnom poli knižničnej triedy a **injection token na
neho nie je**, takže `updateOn: 'change'` sa zvonku vypýtať nedá. To je tá veta,
ktorá túto vec posúva na vrstvu 3.

Pole si to vypýta zo siete:

```xml
<data type="text">
    <id>poznamka</id>
    <component>
        <properties>
            <property key="saveWhileTyping">true</property>
        </properties>
    </component>
</data>
```

`<component>` **bez `<name>`** je v poriadku — engine to prijme (overené
importom) a `pfview` meno nekontroluje, keď tam nie je. Pri poli, ktoré už
komponent má (`textarea`), sa `<properties>` pridá doňho.

Robí to `EtaskFieldComponentResolverComponent`: počúva `input` udalosť, ktorá
bublá z knižničného `<input>`, po 600 ms bez písania zapíše hodnotu do
`DataField.value` — a tým sa ďalej ide **knižničnou** cestou (validácia,
changed fields, POST). Žiadna knižničná šablóna sa nekopíruje.

Typ poľa sa pritom pýta cez `getElementType()`, nie cez `instanceof TextField`:
v produkčnom builde je trieda minifikovaná (`E4e`), takže `instanceof` proti
importovanému symbolu ticho vráti `false` a funkcia nerobí nič. `DataField` nemá
za behu ani `type`. Podrobne FRONTEND_LEARNINGS A4.

**Je to voliteľné a zámerne nie default.** Čo to stojí:

| cena | prečo |
|---|---|
| každý commit je požiadavka, ktorá na serveri spustí `set` akcie prechodu | v tomto stacku tie akcie robia skutočnú prácu (prepočty, upozornenia, render položiek) — pole, do ktorého sa píše desať sekúnd, znamená ~15 behov namiesto jedného |
| **odpoveď servera sa zapisuje späť do inputu** (`registerFormControl`: `_value` → `formControl.setValue`) | pri poli, ktoré akcia normalizuje (trim, formát čísla, prepočet), ten zápis príde **počas písania** a preloží kurzor alebo prepíše text. Na blur je to neviditeľné, pri písaní nie |
| dve požiadavky môžu byť naraz vo vzduchu a `setData` nemá verziu | vyhrá pomalšia odpoveď; debounce to robí zriedkavým, nie nemožným |
| `required` a pattern validácie začnú svietiť uprostred slova | |

**Nezapínaj to na poli, ktoré nejaká akcia prepisuje.** To je celé pravidlo.

Čo to kupuje: pole sa uloží, aj keď z neho človek nikdy neodíde — zavrie úlohu,
alebo klikne na tlačidlo v tom istom formulári. To druhé je reálna pasca, na
ktorú tento repozitár má lint (`pflint`, pravidlo `button-reads-text`): blur
a klik sú pre prehliadač **jedna** požiadavka, takže akcia za tlačidlom prečíta
hodnotu spred písania. Pravidlo `saveWhileTyping` uznáva ako opravu.

Kde to je zapnuté a prečo:

| pole | dôvod |
|---|---|
| `sd_intake.req_description` | verejný formulár, najdlhší text — píše sa doň minútu a dá sa odoslať bez odkliknutia |
| `fa_faktura.fa_dodavatel`, `fa_cislo` | tlačidlo „Načítať z prílohy" v tom istom formulári tie polia číta (`dopln_ak_prazdne` sa podľa nich rozhoduje) |

**Najdrahšia chyba v histórii tohto frontendu:** `nc-task-list` renderuje
knižničný panel a teda knižničný resolver — vlastné polia sa nezobrazia
**vôbec** a build to neodhalí. Správne je `<app-etask-task-list>`.

Odvtedy to odhalí `tools/pfview.py`. Spusti ho po každom zásahu do frontendu
alebo do `<component>` v sieti — je to jediná kontrola tejto vrstvy:

```bash
python3 tools/pfview.py              # tri kontroly
python3 tools/pfview.py --inventory  # čo frontend vôbec pozná
```

| kontrola | čo chytí | ako by to vyzeralo bez nej |
|---|---|---|
| A | kópia knižničnej šablóny zaostala | nový typ poľa sa vykreslí ako prázdne miesto |
| B | `<nc-x>` tam, kde vlastníme `<app-etask-x>` | vlastné polia sa nezobrazia vôbec |
| C | `<component><name>` alebo `<property key>`, ktoré nikto nečíta | ticho sa vykreslí default |

Kontrola A je dôvod, prečo hlavička skopírovaného súboru **musí** obsahovať
vetu `Copy of @netgrif/components <pôvodný-súbor>.component.html` — nástroj
podľa nej nájde originál v balíku a porovná vetvy `ngSwitch`. Bez tej vety
súbor nikto nesleduje.

Kontrola C nekontroluje `<component><name>` pri type, ktorého komponent
vlastníme a `component.name` vôbec nečíta (`boolean` číta variant
z `<properties>`). Kontrolujú sa tam kľúče properties — preklep v `key`
je tichý presne tak isto.

`change <field>` podporuje na úrovni enginu iba `value`, `choices`, `options`,
`allowedNets` a `validations`. `placeholder` ani ikona sa z akcie meniť nedajú —
obchádza sa to paritou hodnoty (vzor je vlastný button).

---

## 7. Noví používatelia

Dve úplne oddelené veci, ktoré sa pletú:

**Systémové authorities** (`ROLE_ADMIN`, `ROLE_USER`) rozhodujú o prístupe
k viewom podľa `nae.json`. Deklarujú sa v `application.properties`:

```properties
etask.users.novy.email=novy@firma.sk
etask.users.novy.name=Nový Používateľ
etask.users.novy.password=${NOVY_PASSWORD:}
etask.users.novy.authorities=ROLE_USER
```

`EtaskUserCreator` ich vytvorí pri štarte a existujúce preskočí. **Bez
nastavenej premennej sa účet nevytvorí** — používateľ s prázdnym heslom sa
preskakuje, aby v šablóne nebolo natvrdo žiadne heslo. Presne preto testovacie
účty na čerstvej databáze chýbajú, kým nie je `ETASK_TEST_PASSWORD`:

```bash
ETASK_TEST_PASSWORD=test1234 tools/up.sh --fresh
```

**Používateľa vie založiť aj proces**, nielen properties — a to celé v Petriflow,
bez Javy. Delegát na to má primitíva:

```groovy
def u = createNewUser(meno, priezvisko, email, heslo, ["ROLE_USER"])

// Vyber v dvoch krokoch: proces -> jeho role a jeho verzie.
def procesy = processOptions()                          // "appka/siet" -> "Názov"
def roly    = processRoleOptions("dovolenky/dv_ziadost")  // importId -> "Názov roly"
def verzie  = processVersionOptions("dovolenky/dv_ziadost")

setProcessRole(u.stringId, "zamestnanec", "dovolenky/dv_ziadost", "", true)
```

`createNewUser` **bez** zoznamu authorities dáva `ROLE_USER`. Nie je to kozmetika:
bez authorities sa používateľ prihlási a **nevidí nič** — prístup k viewom riadi
`nae.json` podľa authorities, nie podľa procesných rolí. Sú to dve oddelené veci,
ktoré sa pletú, a prázdna množina sa neprejaví ako chyba, len ako prázdna appka.

**Prideľovanie rolí už engine má** — `assignRole(importId, siet, user)` plošne na
všetkých verziách a `assignRole(importId, siet, Version, user)` na jednej. Projekt
k tomu pridáva len `setProcessRole(...)`, a to z dvoch dôvodov: `Version` je
objekt (akcia má verziu ako reťazec) a enginová varianta pri neznámom `importId`
hodí `NullPointerException`. **Odoberanie enginové nepoužívaj vôbec** — v 6.3.1
je rozbité a mlčí (`PETRIFLOW_LEARNINGS.md`, C1).

`processVersionOptions` dáva ako prvú voľbu **všetky verzie** a to je aj to, čo
človek chce skoro vždy: rola má `stringId` razené per verziu, takže pridelenie
na jednej verzii na casoch inej verzie neplatí. Kľúče sú zaslugované (`1_0_0`),
lebo bodka v kľúči `options` zhodí ukladanie do Monga
(`petriflow_reference.md`, C17).

Tri veci, ktoré na takom procese treba spraviť vedome:

* **Účet nedrž ako objekt cez viac zmien.** Každá zmena je `read – mutuj – save`
  celého dokumentu, takže druhá prepíše výsledok prvej. Prejavilo sa to tak, že
  heslo sa zmenilo, ale meno, oprávnenia aj odobraná rola sa **ticho vrátili** do
  pôvodného stavu — a `finish` vrátil `success`. Pracuj s `userId` a použi
  primitíva, ktoré si účet načítajú samy.
* **Heslo z dát prípadu vymaž** v tej istej `post` akcii, ktorá účet založila
  (`change heslo_pole value { "" }`). Inak ostane v čitateľnej podobe v `dataSet`
  a v histórii prípadu.
* **Read-only prehľad zaves na read arc zo sinku**, alebo ho nemaj samostatný.
  Miesto, ktoré nejaký prechod konzumuje, na to nestačí — odmietnuté `finish` tú
  úlohu zmaže a už ju neobnoví (`PETRIFLOW_LEARNINGS.md`, B8b).

A ešte tri, ktoré nie sú o používateľoch, ale bijú práve tu:

* **Skryté pole musí byť v `dataGroup` prechodu.** Nie preto, aby ho niekto
  videl — `GET /api/task/{id}/data` vracia len polia z dataGroup, takže inak ho
  nevidí ani test, ani nikto, kto sa prípadu pýta cez API.
* **Zdieľaná úloha nesmie mať `assignPolicy=auto`** a nesmie mať zakázaný
  `cancel` (`PETRIFLOW_LEARNINGS.md`, B21).
* **Možnosti poľa nastavuj tam, kde zapisuješ hodnotu**, nie v `create`
  udalosti prípadu — tam sa neuchovajú (B20).

**Entita verzus úkon.** Keď appka spravuje niečo, čo existuje aj bez nej —
používateľské účty, zariadenia, zmluvy — prípad má byť **na tú entitu**, nie na
úkon. Prípad na úkon znamená, že o tej istej entite máš päť otvorených
rozpísaných prípadov a žiadny z nich nie je ten pravý. Z toho vyplýva aj to,
že entity, ktoré vznikli inak, potrebujú **zosúladenie** (idempotentné
doplnenie prípadu) — a že zviazanie prípadu s entitou má byť na jednom mieste,
odkiaľ si prípad zvyšok dotiahne sám. Zdrojom pravdy je entita, nie to, čo
niekto poslal do formulára.

Hotová sieť, ktorá toto celé robí — validácie v `pre`, založenie aj úprava účtu,
dvojkrokový výber rolí s `autocomplete`, voľba verzie procesu a karta v menu
s vlastnými stĺpcami — je na vetve `claude/uzivatelia-app`
(`processes/pu_pouzivatel.xml`), aj s akceptačným testom `tools/pucheck.py`
(59 kontrol), ktorý overuje, že sa účet naozaj **prihlási**, že nové heslo funguje
a staré nie, a že odobraná rola je naozaj odobraná.

**Procesné roly** (`agent`, `specialist`, …) rozhodujú o prístupe k taskom
a casom. Deklaratívny cieľový stav pre dev a seedovanie je v `seed.json`:

```bash
cd etask-configuration && python3 tools/pfseed.py
```

**Rolu treba prideliť znova po každom re-importe siete.** Rola má `stringId`
razené per verziu, takže po re-importe používateľ na casoch novej verzie
prístup stratí — bez chybovej správy. Oprávnenie cez `userRef` re-import
prežije, cez `roleRef` nie.

**Po `pfseed` sa treba odhlásiť a prihlásiť.** Prihlásená session drží staré
`stringId` rolí, takže na novej verzii siete nemá nič a zakladanie casu vráti
**403** — hoci cez API tomu istému účtu prejde. Nie je to chyba oprávnení siete.

Keď `pfseed` ohlási používateľa ako `NECITATELNY` (500 z `/api/user/search`), sú
to osirelé roly po zlyhanom importe. Cez API sa to opraviť nedá:

```bash
python3 tools/pfseed.py --repair
```

---

## 8. Anonymný (verejný) prístup

Na verejný formulár treba tri veci naraz. Chýbajúca ktorákoľvek sa prejaví ako
401 alebo prázdna obrazovka, nie ako zrozumiteľná chyba.

**1. JWT podpisový kľúč.** Bez neho engine nepodpíše token anonymnej session:

```bash
etask-configuration/tools/bootstrap.sh    # idempotentné, existujúci neprepíše
```

`certificates/` je v `.gitignore` — po `git clone` tam nie je nič. V produkcii
sa kľúč nastavuje cez `JWT_SIGN_CERT` a nikdy sa necommituje.

**2. Sieť musí anonyma pustiť.** V hlavičke:

```xml
<anonymousRole>true</anonymousRole>
```

**3. Zakladanie casu je zvlášť právo.** `createCase` v akcii beží v kontexte
prihláseného používateľa — pri podaní z verejného formulára je to anonym.
Cieľová sieť preto potrebuje na úrovni procesu:

```xml
<roleRef>
    <id>anonymous</id>
    <caseLogic><create>true</create></caseLogic>
</roleRef>
```

URL verejného formulára (routy sú v `etask-frontend-starter/nae.json`,
`access: public`):

```
/process/<petriNetId>/<caseId>/<transitionId>    jeden task, bez hlavičky
/process/<petriNetId>/<caseId>                   celý case
```

Dve veci, ktoré stoja za vedomie dopredu:

* Anonym **vie zakladať casy**. To je spamovacia plocha — rate limiting na
  verejný formulár je nutnosť, nie vylepšenie.
* Podformuláre so `system` roleRef sa anonymovi v zozname taskov nezobrazia,
  ale cez `taskRef` sa vykreslia **a sú editovateľné**. To je mechanizmus, na
  ktorom stojí viackrokový eForm bez klikania DOKONČIŤ (`sd_intake.xml`).

---

## 9. Dvojjazyčná appka (SK + EN)

Portál sa prepína medzi slovenčinou a angličtinou. Appka sa prepne s ním len
vtedy, keď má preklady v sieti — inak zostane jednojazyčná a nikde sa to
neohlási.

### Ako to funguje

Prekladá **server**. `Accept-Language` z požiadavky (posiela ho
`TranslateInterceptor` knižnice) rozhodne, ktorý reťazec sa vráti. Mechanizmus
je dvojdielny:

1. Preložiteľný element potrebuje atribút **`name`** — to je kľúč prekladu.
2. Pre každý kľúč musí byť riadok v bloku **`<i18n locale="...">`**.

```xml
<title name="zd_dovod_title">Dôvod</title>
...
<i18n locale="en">
    <i18nString name="zd_dovod_title">Reason</i18nString>
</i18n>
```

**Chýbajúca polovica sa neprejaví nijako.** Bez `name` aj bez riadku v `i18n`
sa zobrazí pôvodná hodnota, import prejde a log mlčí. Appka vyzerá funkčne
a je jednojazyčná.

**Kód jazyka musí byť dvojpísmenový.** `locale="en-US"` sa naimportuje a nikdy
sa nepoužije — kľúč sa ukladá verbatim, ale hľadá sa cez `Locale.getLanguage()`
(`ENGINE_ISSUES.md` E15).

### Postup

```bash
cd etask-configuration
python3 tools/pfi18n.py --init processes/mojaapp.xml   # doplní name= a blok i18n
# prelož TODO riadky
python3 tools/pfi18n.py processes/                     # 0 chýb, 0 upozornení
python3 tools/pfsync.py --sync
```

`--init` je mechanická práca, nie preklad: kľúče odvodí z id elementov a do
bloku napíše slovenskú hodnotu s prefixom `TODO `. Tie `TODO` hlási kontrola
ako upozornenie — preklad, ktorý nikto nepreložil, má byť vidno, inak sa
„dvojjazyčná" appka odlišuje od jednojazyčnej len tým, že má dvakrát to isté.

### Čo sa pri prepnutí neprekreslí hneď

Prepnutie jazyka prekreslí chróm portálu, názvy priečinkov aj názvy zobrazení
v ľavom menu. **Hlavičky stĺpcov z dátových polí sa prepnú až po načítaní
stránky.** Knižnica si nabídku stĺpcov (`AbstractHeaderService.fieldsGroup`)
načíta raz a nemá verejný spôsob, ako ju obnoviť; namerané — po prepnutí
zostalo „Stav | Dátum od", po reloade bolo „Status | Date from".

Nechané tak zámerne. Alternatívy sú horšie: `location.reload()` pri prepnutí
zahodí rozpísaný formulár v otvorenej úlohe, a prebiť knižničný servis by
znamenalo držať kópiu jeho stavu. Zastaraná hlavička stĺpca je menšia škoda než
stratené dáta. Zapísané ako `ENGINE_ISSUES.md` E17.

### Nástroje a testy musia pripnúť locale

Bez hlavičky `Accept-Language` engine **neodpovedá default hodnotou z XML** —
odpovedá v jazyku JVM (tu `en`). Každý nástroj alebo test, ktorý porovnáva
reťazec z modelu s lokálnym XML, preto posiela locale, ktoré engine nepozná:

```python
req.add_header("Accept-Language", "zz")     # => defaultValue
```

Nie `sk` — to by predpokladalo, že default hodnota je slovenská. Neznámy jazyk
funguje bez toho predpokladu. Detail a ako sa to prejavilo je
v `PETRIFLOW_LEARNINGS.md` B24; `pfseed` a `pucheck` to už robia.

### Čo prekladať netreba

`<label>` na `<place>`. Engine ho preloží rovnako, ale klientovi ho neposiela
žiadny endpoint — payload siete je len referencia bez uzlov.

### Čo sa preložiť NEDÁ

* **Názov prípadu.** `Case.title` je obyčajný `String`. `defaultCaseName` sa
  preloží raz, jazykom toho, kto prípad zakladá, a tak zamrzne — anglicky
  hovoriaci používateľ uvidí názvy, ktoré vyrobil slovenský kolega. Preto do
  názvov prípadov nepatrí próza ani stav, ale **dáta**: číslo, dátum, meno,
  suma.
* **Text v `text` poli.** `TextField extends Field<String>`, takže to má ten
  istý problém ako názov prípadu — a keďže sa doň zvykne písať stav, je to
  v praxi najčastejší zdroj jednej slovenskej veci na anglickom formulári.
* **Názov uzla URI** (karta priečinka). Nie je `I18nString` vôbec —
  `UriService` mu nastaví názov ako `String` z cesty. Prekladá sa na frontende:
  kľúč `uriNode.<segment>` v `etask-frontend-starter/src/assets/i18n/*.json`,
  pipe `uriNodeTitle`. Uzol bez záznamu spadne na skrášlený segment.
* **Hodnota, ktorú vypočíta akcia.** `change pole value { "Aktívny" }` zapíše
  reťazec a ten je jednojazyčný. Ak sa má prepínať, musí to byť pole s
  možnosťami a preložené `options`, alebo `i18n(...)`:
  `change pole options { ["a": i18n("Aktívny", ["en": "Active"])] }`.

**Stav preto nie je `text`, ale `enumeration_map`.** To je jediné textové pole,
ktoré appka prepisuje pri každom prechode, a zároveň to, čo používateľ v zozname
číta najčastejšie. Ako `enumeration_map` má popisky možností v `<i18n>`, akcia
zapisuje **kľúč** a engine zobrazí preklad:

```xml
<data type="enumeration_map" immediate="true">
  <id>fa_stav_label</id>
  <title name="fa_stav_label_title">Stav</title>
  <options>
    <option key="koncept" name="fa_stav_opt_koncept">Rozpísaná</option>
    <option key="zauctovana" name="fa_stav_opt_zauctovana">Zaúčtovaná</option>
  </options>
</data>
```

```groovy
change fa_stav_label value { "zauctovana" }   // kluc, nie popisok
```

Vedľajší zisk: dopyty v menu potom filtrujú podľa kľúča
(`dataSet.fa_stav_label.keyValue:"zauctovana"` — **`keyValue`**, nie
`textValue`; to drží preložené popisky), takže nezávisia od jazyka ani
od preformulovania popisku. Kým bol stav `text`, stačilo zmeniť jeho znenie
a zobrazenie „Uzavreté" prestalo nachádzať čokoľvek — bez chyby.

A keď stav nesie pole aj stĺpec, **do názvu prípadu už nemá čo pridať** — tam
by bol jediná neprekladaná vec v každom zozname. Názov nesie dáta: dodávateľa,
číslo, sumu, a kým nie sú, `visualId`.

Merať sa to dá jedným dopytom, hádať netreba:

```bash
curl -s "localhost:8080/api/task/<id>/data" \
     -H "X-Auth-Token: $TOK" -H "Accept-Language: en" | grep -o '"name":"[^"]*"'
```

`tools/sccheck.py` to robí v kroku 21 pre celý formulár faktúry: v `en` nesmie
byť **žiadny** popisok s diakritikou a stav musí mať anglické možnosti. To je
kontrola, ktorú `pfi18n` spraviť nedokáže — vidí XML, nie odpoveď enginu.

### Názvy zobrazení v ľavom menu

Potrebujú obe strany. Sieť ich musí poslať ako `I18nString`:

```groovy
createFilterInMenu("mojaapp", "ma_vsetky",
        i18n("Všetky žiadosti", ["en": "All requests"]),
        dopyt, "Case", [], [:], [:], [], "list", "public")
```

a frontend ich musí prečítať — knižnica si berie `defaultValue` a preklad
zahodí (`ENGINE_ISSUES.md` E16). V tomto repozitári to rieši `view-title.ts`,
takže netreba nič doplniť; v inom projekte to treba prebiť.

**Pozor na idempotenciu.** Ak si sieť stráži „už existuje, preskoč" iba podľa
dopytu, nasadená inštancia preklady **nikdy nedostane** — položky tam sú s tým
istým dopytom, takže sa vždy vyhodnotia ako nezmenené. Do porovnania patrí aj
názov vrátane prekladov (vzor je v `processes/sd_menu.xml`).

A druhá pasca na tom istom mieste: akcia stavajúca menu býva v udalosti
`create`, teda beží **raz za prípad**. Prípad si drží verziu siete, takže po
re-importe menu siete sa nová verzia akcie nespustí, kým nevznikne nový prípad.
`BootstrapCaseRunner` preto hľadá prípad pre **tú verziu**, nie len pre
identifikátor.

### Portál

Prepínač je v ľavom paneli a na prihlasovacej stránke; ponúka práve tie jazyky,
ktoré sú v `EtaskLanguageSelectorComponent`. Pridať tretí znamená doplniť aj
`assets/i18n/<kod>.json`, `uriNode.*` kľúče a `<i18n locale="<kod>">` do
**každej** siete — ponúknuť jazyk je prísľub, že v ňom je celá obrazovka.

Jazyk sa pamätá v preferenciách používateľa a v `localStorage['Language']`.
Aplikácia nastavuje default **len keď si používateľ nikdy nevybral**;
bezpodmienečné `setLanguage(...)` pri starte prepíše obnovenú voľbu a prepínač
prestane fungovať po reloade.

---

## 10. Čítanie faktúry z prílohy (e-faktúra, PDF, OCR)

```groovy
// v akcii ktorejkoľvek siete
def r = precitajFakturu(fa_skan, useCase.stringId)
//  r.zdroj  = xml | text | ocr | nic
//  r.dodavatel r.cislo r.suma r.mena r.splatnost r.vystavenie
//  r.ico r.dic r.iban r.vs r.chyba r.poznamka r.nedocitane
```

Vzor je tlačidlo **Načítať z prílohy** v `processes/fa_faktura.xml`
(`btn_fa_nacitat`). Logika je v `com.netgrif.etask.doc`:
`DocumentTextService` (text z dokumentu) a `InvoiceReaderService` (polia
z textu alebo z XML). Delegát len presmeruje a vyrieši, kde príloha na disku
leží.

**Tri cesty a nie sú rovnocenné:**

| príloha | ako sa čítajú polia | istota |
|---|---|---|
| XML e-faktúra (UBL 2.1 / CII podľa EN 16931, ISDOC) | **čítajú sa** z elementov | presné |
| PDF s textovou vrstvou | hádajú sa podľa popiskov („Celkom k úhrade“) | dobré |
| sken, fotka | OCR (`tesseract`), potom tie isté popisky | odhad |

Poradie je zámerne také, že OCR beží **len keď textová vrstva nie je**.
Väčšina došlých faktúr je digitálne PDF, kde OCR z presného vstupu spraví
odhad. PDFBox je v classpath tranzitívne z `application-engine`, takže prvé dve
cesty nepotrebujú žiadnu inštaláciu.

**OCR treba doinštalovať** — inak appka vo formulári napíše, že binárka nie je
v PATH, a beží ďalej:

```bash
apt-get install tesseract-ocr tesseract-ocr-slk     # Debian/Ubuntu
```

Na Windows build z UB-Mannheim + `slk` do PATH. Prepína sa
`etask.ocr.binary` a `etask.ocr.languages` (bez `slk` nastav `eng`).

### Čo tam hryzie

* **Prečítané sa nikdy nezapisuje samo do rozhodnutia.** Akcia vyplní len
  **prázdne** polia; keď sa hodnota líši od tej, ktorú človek napísal, ohlási
  rozdiel a nechá jeho verziu. Inak by jedno kliknutie ticho prepísalo sumu,
  ktorú niekto práve opravoval podľa papiera.
* **`number` pole bez hodnoty vracia `0.0`, nie `null`.** Kto testuje „je
  prázdne?“ na null, nedoplní nikdy nič a bude hlásiť rozdiel oproti nule.
* **IBAN sa overuje kontrolným súčtom (mod 97), nie regexom.** Vzor na
  „SK + 2 číslice + skupiny po štyroch“ sedí aj na IČ DPH (`SK2023445566`)
  a po odstránení medzier aj na IBAN s nalepeným ďalším slovom. Mod 97 je
  zároveň ochrana pred OCR: prehodená číslica kontrolu neprejde, takže sa
  IBAN radšej nevyplní, než by sa vyplnil zle.
* **V UBL je `cbc:CompanyID` dvakrát** — u dodávateľa aj u odberateľa, a ešte
  raz ako IČ DPH. Kto hľadá po celom dokumente, vytiahne cudzie IČO a hodnota
  tam **bude** — len bude nesprávna. Preto sa polia strany hľadajú len
  v podstrome dodávateľa a prejdú sa všetci kandidáti.
* **Nahranie prílohy cez API vyžaduje časť `data` = `{taskId: fieldId}`.**
  S `{}` vráti engine HTTP 200 a neuloží nič (`ENGINE_ISSUES.md`, E19).

Overenie: `python3 tools/sccheck.py` (kroky 14–16). Fixture e-faktúry je
`tools/fixtures/faktura-ubl.xml`, testovacie PDF si test generuje sám.

---

## 11. Priečinky v karte, názvy tlačidiel, schvaľovanie podľa strediska

Tri veci, ktoré sa v Petriflow dajú a nevyzerá to tak.

### Karta s priečinkami

Uzol URI vzniká z **cesty v identifikátore siete**, takže priečinok je vec
pomenovania siete, nie konfigurácie:

```
schvalovanie/faktury/fa_faktura        -> karta „schvalovanie“, priečinok „faktury“
schvalovanie/objednavky/ob_objednavka  -> ten istý rodič, druhý priečinok
```

Do `processes.json` → `uriNodes` patrí **každý** uzol zvlášť (rodič aj deti) —
ikona a role sa dedia z ničoho. Názov, ktorý človek v menu vidí, je
`uriNode.<segment>` v `etask-frontend-starter/src/assets/i18n/*.json`; bez
kľúča sa zobrazí surový segment cesty. Zobrazenia sa vešajú na konkrétny uzol
druhým argumentom `createOrUpdateMenuItem`.

**Pasca:** premenovanie identifikátora je **nová sieť**. Staré prípady zostanú
pod starým identifikátorom a do nových zobrazení nespadnú (dopyt filtruje
`processIdentifier`), takže ich treba zmazať — `tools/sccheck.py --wipe` maže
aj staré identifikátory práve preto.

### „Single task" zobrazenie: dopyt nesmie stáť na `processIdentifier`

Karta, ktorá má otvoriť rovno jeden formulár (konfigurácia, pult), sa robí ako
zobrazenie typu **Task** zúžené na `transitionId`. Pozor na to, čo do dopytu
patrí a čo nie:

```groovy
// ZLE - task dokument v indexe `processIdentifier` NEMÁ
"processIdentifier:\"nastavenia/sc_nastavenia\" AND transitionId:\"t_sc_nastavenia\""

// DOBRE - id prechodu je unikátne, `processId` je stringId tej verzie siete
"transitionId:\"t_sc_nastavenia\" AND processId:\"" + (useCase.petriNetId as String) + "\""
```

Prvý dopyt nenájde **nikdy nič**: prípad aj úloha existujú, engine nič
nenahlási a obrazovka je prázdna — vyzerá to, že sa case nezaložil. Task
dokument nesie `processId` (stringId verzie siete), nie identifikátor.
`processId` sa pri každom re-importe mení, čo je tu v poriadku, lebo položku
menu prestavuje tá istá akcia, ktorá nové `processId` pozná — a zároveň to
zúži zobrazenie na **jeden** case, keď `bootstrapCase` zakladá jeden na verziu.

Druhá polovica tej istej pasce: konfiguračný case sa nezaloží vôbec, keď akcia
v jeho `create` udalosti spadne. Overuj teda existenciu case-u **pre najnovšiu
verziu** siete, nie „nejakého" — `sccheck` to robí v kroku 20.

### Názvy tlačidiel úlohy

`DOKONČIŤ` a `ZRUŠIŤ` nie sú dané: titulok udalosti sa posiela klientovi
a **prázdny titulok tlačidlo skryje** (`PETRIFLOW_LEARNINGS.md` B23,
`ENGINE_ISSUES.md` E3). V tejto appke má každý prechod svoje:

```xml
<event type="finish">
    <id>t_fa_zapis_finish</id>
    <title name="t_fa_zapis_finish_t">Podať na schválenie</title>
    ...
</event>
<event type="delegate">
    <id>t_fa_zapis_delegate</id>
    <title name="empty_button"></title>
</event>
```

Prázdny titulok potrebuje **prázdny preklad v každom jazyku** — inak sa
tlačidlo v druhom jazyku vráti. Preto je v sieti jeden kľúč `empty_button`
s prázdnou hodnotou a používajú ho všetky skryté tlačidlá.

Read-only pohľad (`t_fa_prehlad`) má prázdne všetky štyri: nie je čo dokončiť
ani rušiť, a skryť tlačidlo takto je lepšie než odoberať oprávnenie — `view`
musí zostať.

### Schvaľovanie podľa strediska

`roleRef` sa v prechode uvádza staticky, takže „schváli to vedúci **toho**
strediska“ sa deklaratívne napísať nedá. Ide to cez `userList` pole:

```groovy
// pri podaní: kto smie túto faktúru schváliť
def kandidati = usersWithRoleAll("schv_" + stredisko) - zadávateľ
change fa_schvalovatelia value { kandidati }
```

a na prechode visí `userRef fa_schvalovatelia` s `perform`. `usersWithRoleAll`
je primitívum delegáta — `usersWithRole` filtruje **zadaný** zoznam, toto je ten
druhý prípad („kto všetko má rolu X“).

Tri veci, ktoré k tomu patria:

* **Rola `schvalovatel` na tom prechode byť nesmie.** `roleRef` a `userRef` sa
  zjednocujú, takže by faktúru schválil ktokoľvek s generickou rolou
  a smerovanie podľa stredísk by nebolo k ničomu. Zostáva ako **záloha**:
  keď stredisko vlastného schvaľovateľa nemá, dostane sa do toho zoznamu.
* **Kaskáda musí byť viditeľná.** `stredisko → všetci schvaľovatelia →
  riaditeľ`, a každý stupeň sa zapíše do priebehu prípadu. Bez toho by faktúra
  v stredisku bez schvaľovateľa čakala navždy a nikto by nevedel prečo.
* **Zadávateľ sa zo zoznamu vyhodí.** Štvoro očí tak nezačína odmietnutím, ale
  smerovaním — kto faktúru zapísal, tú úlohu ani neuvidí. Guard vo `finish`
  zostáva ako druhá línia, pole sa dá prepísať akciou aj cez API.

**Pri testovaní pozor na `ROLE_ADMIN`:** obchádza všetky oprávnenia Petriflow,
takže hranicu „cudzie stredisko si úlohu nepriradí“ sa na `admin@test.local`
overiť nedá. `sccheck` na to používa `operator@test.local` (bez ROLE_ADMIN).

---

## 12. Celý stack v Dockeri (OCR, SMTP, notifikácie)

```bash
etask-configuration/tools/up.sh --docker            # postaví, zdvihne, naimportuje siete
etask-configuration/tools/up.sh --docker --build    # vynúti rebuild obrazov
etask-configuration/tools/up.sh --docker --stop     # zastaví, dáta zostanú
etask-configuration/tools/up.sh --docker --fresh --build   # od nuly, ZMAŽE dáta
```

Compose je `deploy/docker-compose.dev.yml` (projekt `etask`), takže Docker
Desktop ukáže jeden stack so všetkým, čo appka používa:

| služba | čo to je | odkiaľ sa na to ide |
|---|---|---|
| `frontend` | Angular portál v nginxe, `/api` proxuje na backend | http://localhost:4200 |
| `backend` | engine + eTask starter, **s tesseractom v obraze** | http://localhost:8080 |
| `mongo` | dáta prípadov | `localhost:27017` (`mongosh`) |
| `elastic` | index pre `/search` — bez neho sú zoznamy prázdne | http://localhost:9200 |
| `redis` | session store; bez neho Spring spadne až na session | — |
| `mailpit` | SMTP, ktorý maily **nikam neposiela** a ukáže ich | http://localhost:8025 |

Prod compose (`docker-compose.prod.yml`) obrazy **ťahá** z GHCR; tento ich
**buildí** z checkoutu. To je celý rozdiel v zámere — inak sú služby tie isté.

### OCR

`tesseract` je v obraze backendu vrátane `slk` a `eng` dát. Slovenské dáta sú
povinné: bez nich tesseract na slovenskej faktúre vráti zmes znakov, ktorá
**vyzerá** ako prečítaný text, takže sa to neprejaví ako chyba, ale ako nezmyselne
predvyplnené polia. Overiť sa to dá priamo v obraze:

```bash
docker run --rm --entrypoint sh etask-backend:dev -c 'tesseract --list-langs'
```

### Notifikačné maily

Appka posiela e-mail vždy, keď sa faktúra alebo objednávka posunie — tomu, kto
je na rade (a pri uzavretí tomu, kto ju podal). Ide to cez
`com.netgrif.etask.mail.NotifyService` a z Petriflow to je jeden primitív:

```groovy
notifikuj(fa_schvalovatelia, "Faktúra na schválenie", telo)   // vráti počet odoslaných
notifikacieZapnute()                                          // je vôbec SMTP?
```

Tri veci, ktoré sú v tom zámerne:

* **Notifikácia nesmie zhodiť schválenie.** Posiela sa z `finish`, teda vnútri
  transakcie, ktorá prepína token. `JavaMailSender` pri nedostupnom SMTP hodí
  výnimku — a schválenie faktúry by zlyhalo na tom, že sa nepodarilo poslať mail
  o schválení. Preto sa chytá `Throwable` a appka beží ďalej.
* **`spring.mail.host` má v `application.properties` default `''`** — dva
  apostrofy, nie prázdny string. Spring úvodzovky neodstraňuje, takže naivná
  kontrola „je host nastavený?" prehlási SMTP za nastavený na každom stroji bez
  SMTP a každá notifikácia skončí výnimkou v logu. `NotifyService.smtpHost()`
  tie apostrofy zratá.
* **Každý príjemca dostane vlastný mail.** V jednom by každý schvaľovateľ videl
  adresy ostatných a jedna zlá adresa by zhodila odoslanie všetkým.

Vypnúť sa to dá `ETASK_NOTIFICATIONS=false` (property
`etask.notifications.enabled`) — vypnuté notifikácie nie sú chyba, sieť si to
vie zistiť cez `notifikacieZapnute()`.

Testovať sa dá bez prehliadača, Mailpit má REST API:

```bash
curl -s localhost:8025/api/v1/messages | head -c 400
curl -s -X DELETE localhost:8025/api/v1/messages     # vyčistí schránku
```

### Prenos dát z lokálneho behu do stacku (a prečo Elastic vyzerá prázdny)

Starý `etask-backend-starter/docker-compose.yml` mal Mongo v **anonymnom**
volume a Elastic **bez** volume. Po prechode na `etask` stack sú volumes iné,
takže appka vyzerá prázdna. Mongo sa prenesie kópiou:

```bash
OLD=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data/db"}}{{.Name}}{{end}}{{end}}' \
      etask-backend-starter-docker-mongo-1)
docker volume create etask_mongo-data
docker run --rm -v "$OLD":/from -v etask_mongo-data:/to alpine sh -c 'cp -a /from/. /to/'
```

**Pozor: v Elasticu nie sú len indexy prípadov, ale aj URI uzly** (priečinky
bočného menu). Nový ES index teda znamená nové id uzlov a položky menu z Monga
visia na starých — priečinok v paneli je prázdny. Prejde to reštartom backendu
(menu siete si uzol dorovnajú, RUNBOOK 4), nie preindexovaním.

Index v Elasticu sa **neprenáša** — a to je horšie, než sa zdá: prípady v Mongu
sú, ale `/search` ich nenájde, takže zoznamy v appke sú prázdne bez jedinej
chyby. Engine na to má cron úlohu (`spring.data.elasticsearch.reindex`), ktorá
ale pozerá len na prípady zmenené **od štartu** — `reindex-from` má default
null. Dev compose ju preto prepína na „každé 2 minúty, spätne 30 dní":

```yaml
SPRING_APPLICATION_JSON: >-
  {"spring.data.elasticsearch.reindex":"0 */2 * * * *",
   "spring.data.elasticsearch.reindex-from":"P30D"}
```

Cez `SPRING_APPLICATION_JSON`, nie cez `JAVA_OPTS`: cron výraz obsahuje medzery
a v `${JAVA_OPTS}` by sa rozpadol na viac argumentov.

### Šesť pascí, na ktorých to padlo

Všetky tri vyzerali ako niečo iné, než čím boli:

| hlásenie | v skutočnosti |
|---|---|
| `failed to resolve source metadata for docker.io/library/openjdk:11-jdk` | oficiálna rodina obrazov `openjdk` bola z Docker Hubu **stiahnutá** (aj `maven:3-jdk-11`). Nástupca: `eclipse-temurin:11-jdk`, `maven:3.9-eclipse-temurin-11` |
| `/usr/bin/env: 'bash\r': No such file or directory` | `core.autocrlf=true` dal skriptu CRLF, shebang sa číta ako `bash\r`. Rieši `.gitattributes` (`*.sh text eol=lf`) pre budúce checkouty a `sed -i 's/\r$//'` v Dockerfile pre ten aktuálny |
| `ZipException opening "xml-apis-ext-1.3.04.jar": zip END header not found` + `cannot access java` | JitPack ako Maven repozitár v `settings.xml` odpovedal na **cudzí** artefakt 403 s HTML telom a Maven to uložil ako `.jar`. Maven nevie repozitár obmedziť na jednu groupId, takže jediná obrana je nemať ho tam — `vendor-deps.sh` si qrgen ťahá `curl`om sám a každý stiahnutý jar overí, že je čitateľný zip |
| `JedisConnectionException: Could not get a resource from the pool` → `Connection refused`, hoci redis kontejner je healthy | engine si Jedis factory stavia sám a číta `spring.session.redis.host` cez `@Value` (`SessionConfiguration`), čo starter plní z `${REDIS_HOST}`. `SPRING_REDIS_HOST` (štandardné Spring Boot property) sa naň **nedostane** — appka beží na `localhost`. Správne env sú `REDIS_HOST` a `REDIS_PORT`; prod compose to mal tiež zle |
| služba je `unhealthy`, hoci z hostiteľa odpovedá 200 — a `depends_on` kvôli tomu nespustí, čo na ňu čaká | healthcheck volal `http://localhost/` **vnútri** kontejnera. Tam sa `localhost` rozloží najprv na `::1`, ale nginx počúva len na IPv4 `0.0.0.0:80` → `Connection refused`. V healthchecku patrí `127.0.0.1` |
| v logu `NetRunner: ziadne siete na import` a `BootstrapCaseRunner finished` za 13 ms — prázdna appka bez menu | Dockerfile kopíroval `etask-configuration/processes`, ale **nie** `processes.json`. Maven chýbajúci resource mlčky preskočí, takže jar mal siete a nemal manifest — a manifest je to, čo NetRunner aj BootstrapCaseRunner čítajú. Build to teraz kontroluje (`test -f target/classes/petriNets/processes.json`) |

### Po `pfsync --sync` v Dockeri: menu a konfigurácia potrebujú nový prípad

`pfsync --sync` naimportuje novú verziu siete, ale `bootstrapCase` prípady
zakladá **runner pri štarte**. Po importe teda platí to isté ako pri lokálnom
behu (RUNBOOK 4): menu aj konfigurácia ostanú na starej verzii, kým nevznikne
nový prípad. V Dockeri je to jeden príkaz:

```bash
docker compose -f deploy/docker-compose.dev.yml restart backend
```

### Čo `--docker` nerobí

Nemontuje zdrojáky. Zmena v Jave alebo Groovy delegáte znamená
`--docker --build` (Maven beží v obraze, ~3 minúty). **Zmena v sieti build
nepotrebuje** — siete sa importujú cez `pfsync` z repozitára, nie z jaru.

---

## 13. Automatická oprava a MCP server

### `pffix` — opravy, ktoré majú jednoznačné riešenie

```bash
python3 tools/pffix.py processes/            # ukáže, čo by spravil
python3 tools/pffix.py processes/ --write    # zapíše
python3 tools/pflint.py processes/           # a potom skontroluj
```

Oddelené od `pflint` zámerne: kontrola, ktorá aj prepisuje, sa raz spustí omylom
a prepis siete sa neprejaví ako chyba, ale ako iná appka.

| pravidlo | oprava |
|---|---|
| `grid-overlap` | posunie nižšie položený prvok o výšku prekrytia — Angular pri prekrytí úlohu **nevykreslí** a zostane spinner |
| `type-textarea` | `type="textarea"` → `type="text"` + `<component><name>textarea</name></component>` |
| `button-reads-text` | doplní `immediate="true"` poľu, ktoré číta tlačidlo v tom istom dataGroup |

Čo **neopravuje** a prečo: `unsafe-nav-property` (oprava závisí od kontextu
akcie), `findcase-stringid` (treba istotu, že premenná je id), `option-key-mongo`
(kľúč sa používa aj inde a v dátach), `data-unused` (nástroj nevie, či pole plní
iná sieť). Tie ostávajú `pflint`u — a `pfloop`u.

### `pfloop` — validuj, oprav, over, zvyšok priprav modelu

```bash
python3 tools/pfloop.py                 # processes/, bez enginu
python3 tools/pfloop.py --fix           # aj aplikuje mechanické opravy
python3 tools/pfloop.py --engine        # aj import do bežiaceho enginu
```

Spojí celý reťazec do jedného príkazu a **rozdelí nálezy na tri triedy**, lebo
každá patrí niekomu inému:

1. **mechanické** — aplikuje `pffix` a overí znova;
2. **podľa hlásenia** — model ich vie opraviť, keď dostane chybu **aj**
   príslušnú kapitolu; `pfloop` mu to napíše do `.run/pfloop-zadanie.md`
   (chyba + výrez siete + kapitola, nie celá dokumentácia);
3. **návrhové** — „stav patrí do `enumeration_map`", „pohľad má visieť na
   mieste, ktoré nikto nekonzumuje". Tu automat nezlyhá hlučne, zlyhá tak, že
   appka **vyzerá** hotovo. Ostáva človeku.

Zadanie sa **nespúšťa** automaticky. To je zámer: patch, ktorý nikto nevidel,
je horší než nález, ktorý zostal.

### MCP server (`pfmcp`)

```bash
# rýchla skúška bez klienta
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python3 tools/pfmcp.py
```

Registrácia je v `.mcp.json` v roote repozitára — Claude Code si ju vezme sám
pri štarte v tomto priečinku (na Linuxe/macOS zmeň `py -3` na `python3`):

```json
{"mcpServers": {"petriflow": {"command": "py",
  "args": ["-3", "etask-configuration/tools/pfmcp.py"]}}}
```

| nástroj | vracia |
|---|---|
| `pf_doc_list` | dokumenty a kapitoly s cenou v tokenoch |
| `pf_doc` | jednu kapitolu |
| `pf_doc_search` | v ktorých kapitolách to je (nadpisy, nie telo) |
| `pf_lint` | nálezy ako `{subor, riadok, uroven, pravidlo, sprava, oprava}` |
| `pf_fix` | čo by `pffix` opravil (`write=true` zapíše) |
| `pf_api` | primitíva volateľné z akcie podľa mena |

Prečo to má zmysel popri CLI: **popis nástroja je súčasťou protokolu**, takže
sa nástroj ohlási sám — presne ten problém, kvôli ktorému vznikol
`docs/reference/action-api.md` („nemal som ako vedieť, že to existuje"). A nález
ako štruktúra sa dá spracovať; text sa dá len prečítať.

Server **nič nemení**, kým sa nezavolá `pf_fix` s `write=true`, a nesiaha na
engine ani na databázu — `pfsync` a akceptačné sady majú bežať vedome.


---

## 14. „Otvoriť v builderi" — model do modelára bez sťahovania

V sekcii **Workflow** (karta pre `ROLE_ADMIN`) je pri každom procese tlačidlo
**Otvoriť v builderi**, ktoré otvorí model v
`https://builder.netgrif.cloud/modeler?modelUrl=…`. Vyzerá to ako odkaz na dva
riadky. Nie je, a dôvod je jediný: **builder si XML stiahne sám.**

Zmerané na bežiacom engine a na samotnom builderi:

| pokus | výsledok |
|---|---|
| `?modelUrl=<náš /api/petrinet/{id}/file>` | **401** — builder nepošle žiadnu našu hlavičku |
| token v query stringu (`?auth=`, `?token=`, `?access_token=`, `?jwt=`, `?X-Auth-Token=`) | **401** vo všetkých variantoch, engine ho berie len ako hlavičku |
| anonymná session enginu | **401**, XML nečíta ani ona |
| `/api/public/petrinet/{id}/file` | **200**, ale je to HAL index, nie XML |
| `?modelUrl=data:application/xml;base64,…` | XHR `data:` URL prečíta, ale nginx buildera vráti **414 Request-URI Too Large** už pri 21 kB (bežná sieť má 10–50 kB) |
| HTTPS builder → `http://127.0.0.1:8080` | vo vstavanej prehliadačke **zablokované** (`ERR_BLOCKED_BY_CLIENT`, `status: 0`) — v bežnom Chrome NEOVERENÉ, viď nižšie |

Builder číta parameter takto (z jeho vlastného bundlu):

```js
this.route.queryParams.subscribe(p => { p.modelUrl && http.get(p.modelUrl, {responseType: "text"}) ... })
```

Obyčajný `HttpClient.get` bez `withCredentials` a bez hlavičiek. Iný vstup
**nemá** — žiadny `postMessage`, žiadny druhý parameter.

Z toho plynie jediné riešenie: model musí byť chvíľu čitateľný **bez
prihlásenia**. Robí to `ModelLinkController`:

```
GET /api/v2/model-link/{netId}        → { path, expiresAt, validForSeconds }   vyžaduje ROLE_ADMIN
GET /api/public/model/{netId}?exp=&sig=  → XML                                  bez autentifikácie
```

Podpis je HMAC-SHA256 nad `netId|expiry` kľúčom, ktorý sa generuje **pri štarte
a nikde sa neukladá**. Odkaz platí 5 minút a reštart ho zneplatní — čo je
zámer: kľúč, ktorý nie je zapísaný, nevytečie z properties, z vrstvy obrazu ani
z histórie gitu. **Ak to raz pobeží vo viac replikách, tento kľúč musí byť
zdieľaný** — inak odkaz vydaný jednou inštanciou druhá neoverí.

Tri veci, ktoré k tomu patria a inak sa spravia zle:

* **Endpoint vracia cestu, nie absolútnu URL.** Za reverse proxy ju backend
  zložiť nevie — `deploy/nginx.conf` posiela `proxy_set_header Host $host`,
  čo zahadzuje port, takže portál na `:4200` by dostal odkaz na `:80`. Origin
  pozná prehliadač; prefix dopĺňa frontend.
* **Okno sa otvára v obsluhe kliknutia, nie v callbacku.** `window.open`
  zavolané až po návrate HTTP odpovede je asynchrónny popup a prehliadače ho
  blokujú. Tab sa otvorí prázdny hneď a presmeruje sa, keď príde odkaz.
* **Posledný skok je jediný neoverený.** Že builder náš odkaz naozaj stiahnuť
  skúsi, overené je — v jeho konzole je chyba jeho vlastného `HttpClient`
  s našou URL. Či ho prehliadač k `http://localhost` pustí, overené **nie je**:
  vo vstavanej prehliadačke to padlo na `ERR_BLOCKED_BY_CLIENT` bez hlásenia
  o mixed contente, čo môže byť aj sandbox toho panelu. Chrome pritom
  `http://localhost` a `http://127.0.0.1` považuje za dôveryhodný pôvod, takže
  pravidlo o mixed contente sa na ne bežne **nevzťahuje** — reálne to môže ísť.
  Ak nie, prejaví sa to tým, že **builder ukáže prázdne plátno a nikde nie je
  chyba**; frontend preto pri HTTP portáli a HTTPS builderi upozorní snackbarom.
  Vtedy sú tri cesty: povoliť „Insecure content" pre `builder.netgrif.cloud`
  v nastaveniach stránky, pustiť portál po HTTPS, alebo si builder hostovať
  vedľa portálu — adresa je konfigurácia (`services.builder.modelerUrl`
  v `nae.json`, prepísateľná cez `services-builder-modelerUrl` v `env.js`).
  Na nasadenej HTTPS inštancii tento problém nevzniká.

Adresa buildera je konfigurácia, nie konštanta v kóde — appka bez nej tlačidlo
vôbec nevykreslí (`*ngIf="builderUrl"`).
