---
name: petriflow
description: Práca s Petriflow sieťami v tomto repozitári — tvorba a úprava procesov (.xml v etask-configuration/processes), akcie v Groovy, oprávnenia, dátové polia, formuláre, menu. Použi VŽDY pred písaním alebo úpravou Petriflow siete, a tiež keď sa rozhoduješ, či má funkcionalita ísť do Petriflow, do action delegate alebo do Java/Angular kódu. Trigger aj na: proces, sieť, transition, dataGroup, taskRef, dataRef, roleRef, userRef, action delegate, setData, createCase.
---

# Petriflow v tomto repozitári

Aplikačná logika je v Petriflow sieťach, nie v Jave a nie v Angulari. Framework
je ~5 500 riadkov, siete ~7 500 — ten pomer je zámer a má sa udržať.

**Najprv `etask-configuration/reference/cheatsheet.md`** — jedna strana:
postup, osem rozhodnutí a zoznam toho, čo mlčí. Tento skill je to, čo príde po
nej; dlhé dokumenty sú referencia na dožiadanie, nie povinné čítanie.

## Pravidlo 1: najprv sa pozri, čo už existuje

**Pred napísaním akejkoľvek metódy si otvor `etask-configuration/reference/action-api.md`.**

Je to generovaný inventár 169 metód enginu plus vlastné metódy tohto projektu,
volateľné priamo z `<action>` menom, bez importov.

Toto nie je odporúčanie zo slušnosti. Pri stavbe Service Desku bol tento súbor
napísaný **preto**, že som ho nemal: hodiny som dekompiloval bajtkód, hádal
poradie argumentov `createFilterInMenu`, omylom vytvoril dva neplatné URI uzly
v Elasticsearchi — a `createOrUpdateMenuItem()` so správnym poradím a funkčnou
update cestou v tom repozitári už tri roky bol. Vedľajší produkt tej neznalosti
je dodnes v `UriNodeData`: dve polia pre to isté, v inom id-priestore.

Delegát je **dynamický**. Preklep v názve metódy prejde parserom aj importom
a spadne až za behu, keď akciu niekto spustí. Zoznam je preto jediná obrana.

## Pravidlo 2: tri vrstvy, a vrstva 2 je miesto, kde rastie jazyk

```
1. Petriflow XML          ← default. Stav, prechody, dáta, oprávnenia case-u.
2. Custom action delegate ← ROZŠIRUJE JAZYK. Nová metóda tu = nové Petriflow
                            primitívum, volateľné menom z každej siete.
3. Framework/runtime kód  ← len render, HTTP layer, a to, čo engine neposkytuje.
```

Vrstva 2 **nie je záchranná brzda**. `EtaskActionDelegate` dedí engine
`ActionDelegate`, je `@Component`, a čokoľvek v ňom je sa dá zavolať priamo
z akcie menom — bez importu, bez wiringu, bez zásahu do frontendu. Je to
mechanizmus, ktorým sa slovník Petriflow rozširuje, a preto je vrstva 3 skoro
vždy zbytočná.

**Pravidlo promócie:** keď ten istý Groovy píšeš v druhej sieti, nepíš ho po
tretie — presuň ho do delegáta. Presne takto vznikli `userIdsOf()`
a `usersWithRole()`: extrakcia id z userList sa kopírovala do každej siete
vrátane pasce `u?._id`, ktorá zhodí celú akciu.

### Ako pridať metódu

```groovy
// etask-backend-starter/src/main/groovy/com/netgrif/etask/EtaskActionDelegate.groovy
@Component
class EtaskActionDelegate extends ActionDelegate {

    /** Jedna veta, na čo to je - `pfapi` ju vytiahne do inventára. */
    List<String> mojePrimitivum(Object vstup, String param = null) { ... }
}
```

Potom `python3 tools/pfapi.py > reference/action-api.md` — inventár si metódu
aj s jej javadocom vytiahne zo zdrojáku sám.

**Cena za dynamický dispatch:** preklep v názve metódy **nezachytí engine**.
Sieť sa naimportuje bez námietky a za behu vráti HTTP 200, kým akcia potichu
spadne na `MissingMethodException`. Jediné, čo to chytí, je `pflint` proti
inventáru — o dôvod viac ho po zmene siete spustiť.

**Pozor na pretaženie aritou:** engine aj projekt majú `createOrUpdateMenuItem`,
rozlišujú sa len počtom argumentov, a tá v enginu na update ceste padá. Inventár
také kolízie označuje.

Prechod na nižšiu vrstvu musí byť odôvodnený vetou, ktorá povie, **ktoré
primitívum na vyššej vrstve chýba**. Tá veta je zároveň bug report pre framework.
Ak ju nedokážeš napísať, problém patrí vyššie.

Petriflow je jazyk pre *stav, prechody, dáta a oprávnenia case-u*. **Nie je**
jazyk pre render a nie je jazyk pre infrastruktúru okolo requestu. Overené
prípady, kde bola vrstva 3 správna:

| požiadavka | prečo nie Petriflow |
|---|---|
| taskRef sa má preklopiť bez reloadu | čisto klientský render |
| viditeľnosť uzla menu podľa roly | `UriNode` nemá pole pre role, endpointy neberú usera |

## Pravidlo 3: overuj, nehádaj

Bežiaci stack (bez neho sa `pfcheck` nemá čoho pýtať):

```bash
etask-configuration/tools/up.sh
```

Po každej zmene siete, v tomto poradí:

```bash
cd etask-configuration
python3 tools/pflint.py processes/          # 0,3 s — štruktúra, tiché pasce
python3 tools/pfgroovy.py processes/       # 3 s   — syntax Groovy
python3 tools/pfview.py                    # 2 s   — vykreslí to frontend?
python3 tools/pfsync.py --sync             # import do enginu + role
```

`pfsync` porovná každé XML s tým, čo engine naozaj drží, rozdielne prežene cez
`pfcheck` a potom prideli role. Prečo nestačí reštart: **`NetRunner` importuje
sieť len keď v databáze chýba**, takže po zmene existujúceho XML engine ďalej
drží starý model, `LATEST` mieri na neho a nové casy z neho vznikajú. Nikde sa
to neohlási.

`pfview` je jediná kontrola vrstvy 3. Sieť sa naimportuje, aj keď si vypýta
`<component><name>` alebo `<property key>`, ktoré frontend nečíta — Angular to
ticho zahodí a vykreslí default. Rovnako ticho zmizne pole, ktorého typ chýba
v našej kópii knižničného resolvera. Inventár sa číta z `node_modules/@netgrif`
pri každom spustení, nie zo zoznamu v kóde.

**Ground truth je engine.** Keď si offline nástroj a engine odporujú, chyba je
v nástroji — nie v sieti. Stalo sa to dvakrát pri stavbe `pfgroovy`. Detaily
v `tools/README-petriflow-tools.md`.

**Po re-importe siete prideľ role znova** — `pfsync --sync` to už robí, ručne:

```bash
python3 tools/pfseed.py          # cieľový stav je v seed.json
```

A potom sa **odhlás a prihlás**: prihlásená session drží staré `stringId` rolí,
takže zakladanie casu vráti 403, hoci cez API tomu istému účtu prejde.

**Case si drží verziu siete, v ktorej vznikol.** Po zmene siete testuj na novom
case — do starého nové prechody ani polia nepribudnú a vyzerá to, že zmena
nefunguje. Nové casy sú v poriadku: frontend si sieť vyžiada ako `LATEST`.

Rola má `stringId` per verziu siete, takže po re-importe užívateľ na casoch novej
verzie prístup stratí. Bez tohto kroku testuješ na rozbitom stave a nevieš o tom.
Keď `pfseed` ohlási užívateľa ako nečitateľného (500 z `/api/user/search`), sú to
osirelé role po zlyhanom importe — `python3 tools/pfseed.py --repair`.

Nikdy neoznačuj sieť za hotovú bez `pfcheck`. Import endpoint pri chybe vracia
holé `{"status":500}` **bez dôvodu** — príčina je len v logu servera, a `pfcheck`
ju z neho vytiahne.

## Tiché pasce, ktoré ťa nič nepovie

Toto sú spôsoby, ako Petriflow zlyhá bez chybovej správy. `pflint` ich hľadá, ale
poznaj ich aj tak — plný zoznam je v `docs/PETRIFLOW_LEARNINGS.md`.

* **`u?._id` zhodí celú akciu.** Groovy `?.` chráni pred null, **nie** pred
  chýbajúcou property. Na `UserFieldValue` vyhodí `MissingPropertyException`
  a akcia spadne v strede: časť zmien zapísaná, zvyšok nie, v odpovedi nič.
  Použi `u.hasProperty("id") ? u.id : null`.
* **`findCase { it.stringId.eq(id) }` vráti vždy null.** `Case` v mongo pole
  `stringId` nemá. V logu je len INFO. Použi
  `it._id.eq(new org.bson.types.ObjectId(id))`, alebo choď cez `it.caseId` tasku.
* **`async.run { }` výnimku spolkne.** Prenos dát medzi casmi sa prejaví len tým,
  že cieľový case je prázdny. Rob to synchrónne v `try/catch`.
* **Button nevidí hodnotu textového poľa v tej istej požiadavke.** Blur a klik
  sú jedna požiadavka. Editovateľné textové pole, ktoré akcia buttonu číta, musí
  mať `immediate="true"`.
* **`roleRef` a `userRef` sa zjednocujú, nie prienikajú.** „Rola X a zároveň
  pridelený Y" sa deklaratívne napísať nedá. Na to je primitív v delegáte:

  ```groovy
  def agents = usersWithRole(customer.dataSet["c_agents"]?.value, "agent")
  change tk_agents value { agents }
  ```

  Rola zostáva autoritatívna — koho niekto pridá do zoznamu omylom a rolu nemá,
  prístup nedostane. Vzor je v `sd_ticket` (`apply_customer`). Id z userList
  poľa nikdy neťahaj ručne, na to je `userIdsOf()` — `u?._id` zhodí celú akciu.
* **Read-only pohľad na read arcu z konzumovaného miesta zmizne natrvalo.**
  Keď na tom mieste niekto klikne DOKONČIŤ a dokončenie sa odmietne (prázdne
  `required` pole alebo výnimka z `phase="pre"`), engine tú read-only úlohu
  zmaže a už ju neobnoví — token sa nepohol, takže nie je čo ju znova povoliť.
  Read arc pre pohľad veď len z miesta, ktoré žiadny prechod nekonzumuje
  (`p_alive`), alebo z koncového. Detaily v `PETRIFLOW_LEARNINGS.md`, B8b.
* **Rola má stringId per verziu siete.** Po re-importe treba role prideliť znova.
  Oprávnenie cez `userRef` re-import prežije, cez `roleRef` nie.
* **Nové dátové pole sa nepropaguje do existujúcich casov.** Case si drží verziu.

## Dialekt: tri zdroje pravdy, ktoré si odporujú

Nedôveruj schéme z hlavičky siete. Poradie podelementov `<data>`:

| zdroj | tvrdí |
|---|---|
| `reference/petriflow.schema.v1.1.0.xsd` (oficiálna) | `init` pred `component` |
| NAE 6.3.1 za behu | prijme aj `component` pred `init` |
| `docs/PETRIFLOW_LEARNINGS` B5 | `desc` hneď za `title` |

Siete v tomto repozitári porušujú schému a importujú sa. `pflint` preto poradie
**vedome nekontroluje**. Keď potrebuješ istotu, `pfcheck` je jediná odpoveď.

## Kde sa čo nachádza

```
etask-configuration/
  docs/RUNBOOK.md       recepty na bežné úlohy (rozbeh, menu, useri, anonym)
  processes/            aplikačná logika — siete (toto upravuješ)
  processes.json        čo sa importuje pri štarte a v akom poradí
  examples/
    skeleton.xml        najmenšia funkčná sieť — odtiaľto začni novú appku
  reference/
    action-api.md       generovaný inventár extension pointov ← ČÍTAJ PRVÉ
    petriflow.schema.v1.1.0.xsd
  docs/
    petriflow_reference.md    jazyková referencia
    PETRIFLOW_LEARNINGS.md    čo referencia nepokrýva alebo tvrdí zle
    SERVICE_DESK.md           worked example: eForm, SLA, per-org oprávnenia
    AI_STARTER_ANALYSIS.md    prečo je repozitár takto postavený
  tools/                up.sh, pflint, pfgroovy, pfview, pfcheck, pftest, pfapi, pfseed
etask-backend-starter/
  src/main/groovy/com/netgrif/etask/EtaskActionDelegate.groovy   ← vrstva 2
  src/main/groovy/com/netgrif/etask/startup/ProcessManifest.groovy   číta manifest
  src/main/groovy/com/netgrif/etask/startup/NetRunner.groovy         import sietí
```

Siete sa importujú pri starte podľa `processes.json`, ale **len keď v databáze
chýbajú**. Po zmene siete ju treba nahrať znova (`pfcheck`).

## Nová aplikácia: XML + riadok v manifeste

```bash
cd etask-configuration
cp examples/skeleton.xml processes/dovolenka.xml     # prepíš <id>, <initials>, <title>
# dopíš "dovolenka.xml" do processes.json → "import"
python3 tools/pflint.py processes/dovolenka.xml
```

**Do Javy ani do `pom.xml` sa nesiaha.** Manifest je jediný zoznam, `pom.xml`
kopíruje `processes/*.xml` hromadne a `NetRunner` si identifikátor prečíta
z `<id>` v XML — nedá sa teda rozísť so sieťou. Ak sa pri pridávaní appky
chystáš editovať Javu, je to signál, že robíš niečo iné, než si myslíš.

Na poradí v manifeste záleží: uzol URI vzniká až importom prvej siete, ktorej
identifikátor tú cestu nesie, takže sieť odkazujúca na uzol (typicky menu)
patrí za ňu.

Manifest má tri sekcie a všetky tri sú tam preto, aby appka nemusela siahať do
Javy:

| kľúč | na čo |
|---|---|
| `import` | súbory sietí a poradie importu |
| `bootstrapCase` | siete, ktorých má pri štarte existovať práve jeden case (typicky tá, čo stavia zobrazenia menu) |
| `uriNodes` | ikona a viditeľnosť karty v bočnom menu — `requiredAuthorities` a `requiredProcessRoles` (importId, nie stringId) |

**Vlastná karta v menu** teda znamená: sieť s identifikátorom `mojaapp/mojaapp`,
položka `"mojaapp"` v `uriNodes`, a ak má karta niečo otvárať, sieť stavajúca
zobrazenia v `bootstrapCase`. Vzor je Service Desk (`sd_menu.xml`).

## Worked example

Service Desk je **príkladová aplikácia, nie časť frameworku** — runtime ho nepozná
po mene, je to len päť sietí a tri záznamy v manifeste. Odstrániť sa dá zmazaním
`processes/sd_*.xml`, ich riadkov v `import`, `bootstrapCase`, položky
`service_desk` v `uriNodes` a `netScope` v `seed.json`. Žiadny Java súbor.

Než začneš písať, prečítaj `docs/SERVICE_DESK.md` a pozri `processes/sd_*.xml`.
Je tam verejný viackrokový eForm cez taskRef bez klikania DOKONČIŤ, child casy,
per-organizačné oprávnenia a SLA per zákazník. Funkčný príklad je pri Petriflow
užitočnejší než špecifikácia — dialekt sa z neho číta spoľahlivejšie než zo schémy.
