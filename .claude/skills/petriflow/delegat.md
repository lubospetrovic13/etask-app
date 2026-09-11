# Vrstva 2: delegát je miesto, kde rastie jazyk

`EtaskActionDelegate` dedí engine `ActionDelegate`, je `@Component`, a čokoľvek
v ňom sa dá zavolať priamo z akcie **menom** — bez importu, bez wiringu, bez
zásahu do frontendu. Preto je vrstva 3 skoro vždy zbytočná.

**Pravidlo promócie:** keď ten istý Groovy píšeš v druhej sieti, nepíš ho po
tretie — presuň ho do delegáta. Presne takto vznikli `userIdsOf()`
a `usersWithRole()`: extrakcia id z userList sa kopírovala do každej siete
vrátane pasce `u?._id`, ktorá zhodí celú akciu.

## Ako pridať metódu

```groovy
// etask-backend-starter/src/main/groovy/com/netgrif/etask/EtaskActionDelegate.groovy
@Component
class EtaskActionDelegate extends ActionDelegate {

    /** Jedna veta, na čo to je - `pfapi` ju vytiahne do inventára. */
    List<String> mojePrimitivum(Object vstup, String param = null) { ... }
}
```

Potom `python3 tools/pfapi.py > docs/reference/action-api.md` — inventár si metódu
aj s jej javadocom vytiahne zo zdrojáku sám.

**Cena za dynamický dispatch:** preklep v názve metódy **nezachytí engine**.
Sieť sa naimportuje bez námietky a za behu vráti HTTP 200, kým akcia potichu
spadne na `MissingMethodException`. Jediné, čo to chytí, je `pflint` proti
inventáru — o dôvod viac ho po zmene siete spustiť.

**Pozor na preťaženie aritou:** engine aj projekt majú `createOrUpdateMenuItem`,
rozlišujú sa len počtom argumentov, a tá v engine na update ceste padá. Inventár
také kolízie označuje.

## Keď je vrstva 3 naozaj správna

Petriflow je jazyk pre *stav, prechody, dáta a oprávnenia case-u*. **Nie je**
jazyk pre render a nie je jazyk pre infraštruktúru okolo requestu. Overené
prípady:

| požiadavka | prečo nie Petriflow |
|---|---|
| taskRef sa má preklopiť bez reloadu | čisto klientský render |
| viditeľnosť uzla menu podľa roly | `UriNode` nemá pole pre role, endpointy neberú usera |
| pole sa má uložiť počas písania | `FormControl` vzniká v privátnom poli knižnice s `updateOn: 'blur'`, injection token preň neexistuje (`pfdoc runbook 6`) |

Vlastné primitíva, ktoré takto vznikli z reálnych appiek: `usersWithRoleAll`,
`najnovsiCase`, `precitajFakturu`, `ocrDostupne`, `notifikuj`, `menaUzivatelov`,
`pripoj_do_uzla`, `createOrUpdateMenuItem`.
