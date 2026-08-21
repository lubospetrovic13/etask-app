---
name: petriflow
description: Práca s Petriflow sieťami v tomto repozitári — tvorba a úprava procesov (.xml v etask-configuration/processes), akcie v Groovy, oprávnenia, dátové polia, formuláre, menu. Použi VŽDY pred písaním alebo úpravou Petriflow siete, a tiež keď sa rozhoduješ, či má funkcionalita ísť do Petriflow, do action delegate alebo do Java/Angular kódu. Trigger aj na: proces, sieť, transition, dataGroup, taskRef, dataRef, roleRef, userRef, action delegate, setData, createCase.
---

# Petriflow v tomto repozitári

Aplikačná logika je v Petriflow sieťach, nie v Jave a nie v Angulari. Framework
je ~5 500 riadkov, siete ~7 500 — ten pomer je zámer a má sa udržať.

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

## Pravidlo 2: tri vrstvy, a nikdy nezačínaj na tretej

```
1. Petriflow XML          ← default. Stav, prechody, dáta, oprávnenia case-u.
2. Custom action delegate ← I/O, cudzie API, výpočet, ktorý sa v Groovy akcii
                            nedá vyjadriť čitateľne.
3. Framework/runtime kód  ← len render, HTTP layer, a to, čo engine neposkytuje.
```

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

Po každej zmene siete, v tomto poradí:

```bash
cd etask-configuration
python3 tools/pflint.py processes/          # 0,3 s — štruktúra, tiché pasce
python3 tools/pfgroovy.py processes/       # 3 s   — syntax Groovy
tools/pfcheck.sh --log <backend.log> processes/   # ground truth import
```

**Ground truth je engine.** Keď si offline nástroj a engine odporujú, chyba je
v nástroji — nie v sieti. Stalo sa to dvakrát pri stavbe `pfgroovy`. Detaily
v `tools/README-petriflow-tools.md`.

**Po re-importe siete prideľ role znova:**

```bash
python3 tools/pfseed.py          # cieľový stav je v seed.json
```

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
  pridelený Y" sa deklaratívne napísať nedá. Rieši sa presunom roly do dát —
  vzor je v `sd_customer` + `sd_ticket`.
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
  processes/            aplikačná logika — siete (toto upravuješ)
  reference/
    action-api.md       generovaný inventár extension pointov ← ČÍTAJ PRVÉ
    petriflow.schema.v1.1.0.xsd
  docs/
    petriflow_reference.md    jazyková referencia
    PETRIFLOW_LEARNINGS.md    čo referencia nepokrýva alebo tvrdí zle
    SERVICE_DESK.md           worked example: eForm, SLA, per-org oprávnenia
    AI_STARTER_ANALYSIS.md    prečo je repozitár takto postavený
  tools/                pflint, pfgroovy, pfcheck, pftest, pfapi
etask-backend-starter/
  src/main/groovy/com/netgrif/etask/EtaskActionDelegate.groovy   ← vrstva 2
  src/main/groovy/com/netgrif/etask/startup/NetRunner.groovy     siete → import
```

Siete sa importujú pri starte z `processes/` (`NetRunner.PetriNetEnum`), ale
**len keď v databáze chýbajú**. Po zmene siete ju treba nahrať znova.

## Worked example

Než začneš písať, prečítaj `docs/SERVICE_DESK.md` a pozri `processes/sd_*.xml`.
Je tam verejný viackrokový eForm cez taskRef bez klikania DOKONČIŤ, child casy,
per-organizačné oprávnenia a SLA per zákazník. Funkčný príklad je pri Petriflow
užitočnejší než špecifikácia — dialekt sa z neho číta spoľahlivejšie než zo schémy.
