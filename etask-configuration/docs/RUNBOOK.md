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
tools/up.sh --fresh       # zahodí databázu a začne odznova
tools/up.sh --frontend    # popri backende aj ng serve na :4200
tools/up.sh --db mojadb   # iná databáza
```

Prihlásenie: `super@netgrif.com` / `password`.

**Prečo to je skript a nie odsek v READMe.** Každý krok má tichú pascu:

| pasca | ako sa prejaví |
|---|---|
| chýbajúci `certificates/private.der` | verejné formuláre vracajú **401**, bez správy, ktorá by to spojila s kľúčom |
| JDK 17/21 | `Unsupported class file major version` — Groovy 3 na novšej Jave padá |
| bez `LANG=C.UTF-8` | import siete s diakritikou v názve zhodí `InvalidPathException` |
| stale `target/` | Maven preskočí kopírovanie zdrojov: jar bez sietí, alebo s triedou, ktorú zdroj už nemá |
| chýbajúci Redis | Spring spadne až na session store, dlho po štarte |

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
siete ju treba nahrať znova (`pfcheck`, alebo Nahrať proces v appke).

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

A ešte: po `createFilterInMenu` sa zápis do vlastného casu (ani `change`, ani
`setData`) neuchová — engine medzitým zakladal iné casy a výsledok zahodí.
`changeCaseProperty("title")` prežije.

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

**Procesné roly** (`agent`, `specialist`, …) rozhodujú o prístupe k taskom
a casom. V properties nie sú — deklaratívny cieľový stav je v `seed.json`:

```bash
cd etask-configuration && python3 tools/pfseed.py
```

**Rolu treba prideliť znova po každom re-importe siete.** Rola má `stringId`
razené per verziu, takže po re-importe používateľ na casoch novej verzie
prístup stratí — bez chybovej správy. Oprávnenie cez `userRef` re-import
prežije, cez `roleRef` nie.

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
