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

**Do Javy ani do `pom.xml` sa nesiaha.** `NetRunner` číta manifest a identifikátor
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
cd etask-configuration && python3 tools/pfapi.py > reference/action-api.md
```

**Najprv sa pozri do `reference/action-api.md`.** Je to generovaný zoznam 169
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
```

Takže priečinok „Vybavené" je obyčajný dopyt nad dátovým poľom, nie nová sieť:

```groovy
def query = "processIdentifier:\"mojaapp/mojaapp_ziadost\"" +
            " AND dataSet.stav_label.textValue:(\"Schválená\" OR \"Zamietnutá\")"
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
  názvov prípadov nepatrí próza, ale **dáta**: číslo, dátum, meno, stav ako
  krátky kód. Stav ako slovo („Podané") tam patrí len vtedy, keď je jednojazyčnosť
  prijateľná.
* **Názov uzla URI** (karta priečinka). Nie je `I18nString` vôbec —
  `UriService` mu nastaví názov ako `String` z cesty. Prekladá sa na frontende:
  kľúč `uriNode.<segment>` v `etask-frontend-starter/src/assets/i18n/*.json`,
  pipe `uriNodeTitle`. Uzol bez záznamu spadne na skrášlený segment.
* **Hodnota, ktorú vypočíta akcia.** `change pole value { "Aktívny" }` zapíše
  reťazec a ten je jednojazyčný. Ak sa má prepínať, musí to byť pole s
  možnosťami a preložené `options`, alebo `i18n(...)`:
  `change pole options { ["a": i18n("Aktívny", ["en": "Active"])] }`.

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
