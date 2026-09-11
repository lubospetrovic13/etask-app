# Cheatsheet: appka v Petriflow za jedno čítanie

Dokumentácia tohto repozitára má ~86 000 tokenov. Načítať ju celú pred prvým
riadkom kódu je najväčšia jednotlivá položka nákladu na jednu appku — a väčšina
z nej je odpoveď na otázku, ktorú v danej úlohe nikto nepoloží.

**Toto je to, čo treba vedieť vopred** (~1 700 tokenov). Zvyšok je referencia na
dožiadanie — a berie sa **po kapitolách**, nie po súboroch:

```bash
python3 tools/pfdoc.py                  # čo kde je, s cenou v tokenoch
python3 tools/pfdoc.py hladaj "menu"    # v ktorej kapitole to je
python3 tools/pfdoc.py runbook 4        # len tá kapitola (~2 700 namiesto ~14 500)
```

Keď niečo nesedí s tým, čo robí engine, **pravdu má engine** — a potom je chyba
v tomto súbore alebo v nástroji, nie v sieti.

---

## Postup

```bash
cd etask-configuration
cp examples/skeleton.xml processes/mojaapp.xml      # prepíš <id>, <initials>, <title>
# dopíš "mojaapp.xml" do processes.json → "import"
python3 tools/pflint.py processes/        # 0,3 s  štruktúra a tiché pasce
python3 tools/pfgroovy.py processes/      # 3 s    syntax Groovy
python3 tools/pfview.py                   # 2 s    vykreslí to frontend?
python3 tools/pfsync.py --sync            #        import do enginu + role
```

Do Javy ani do `pom.xml` sa nesiaha. Pri zmene **manifestu** treba prestaviť jar
(pakuje sa doň); pri zmene len XML stačí `pfsync --sync`.

Pred písaním vlastnej metódy otvor `docs/reference/action-api.md` — 200+ metód,
ktoré sa dajú volať z akcie menom. Delegát je dynamický, takže preklep spadne
až za behu; ten zoznam je jediná obrana a `pflint` proti nemu kontroluje.

---

## Osem rozhodnutí, ktoré určujú, či to bude fungovať

| rozhodnutie | správne | prečo | podrobne |
|---|---|---|---|
| **Prípad = entita, či úkon?** | entita | prípad na úkon znamená päť rozpísaných prípadov o tej istej veci a žiadny nie je ten pravý | RUNBOOK 7 |
| **Typ poľa čítaného v Groovy** | `enumeration_map`, `multichoice_map` | bezmapové varianty ukladajú zobrazený text ako kľúč, takže `"kluc" in pole.value` ticho nesedí | reference, pravidlo `_map` |
| **Kľúč možnosti** | bez `.` a `$`, slug (`1_0_0`) | Mongo to v názvoch polí zakazuje, uloženie spadne | reference C17 |
| **Kedy `immediate="true"`** | len keď to má byť stĺpec alebo sa podľa toho hľadá | na `multichoice_map` s runtime možnosťami zhodí indexáciu | LEARNINGS B13 |
| **`assignPolicy`** | `auto` na osobnú úlohu, `manual` na zdieľanú | auto priradí úlohu tomu, kto ju vyrobil — pri bootstrape systémovému účtu | LEARNINGS B12 |
| **Zakázať `cancel`?** | nie | `cancel` úlohu **uvoľní**, nezruší; zákaz znamená, že ju nemá kto pustiť | LEARNINGS B12 |
| **Read-only pohľad** | read arc zo **sinku**, alebo vôbec nie | odmietnuté `finish` zmaže ostatné úlohy toho miesta a neobnoví ich | LEARNINGS B8b |
| **Routovacie príznaky** | v `phase="pre"` | v `post` sa token pohne s nulami a zmizne | reference C4 |

---

## Čo mlčí

Toto sú chyby, ktoré **engine prijme**, build nenahlási a v appke sa prejavia
ako „nefunguje to". Všetky sú overené na bežiacom engine.

**Sieť a dáta**

- `change <pole> options { }` v `create` udalosti prípadu sa **neuchová**.
  Nastavuj možnosti tam, kde zapisuješ hodnotu. (B11)
- Pole, ktoré nie je v žiadnom `dataGroup`, **nevráti** `GET /api/task/{id}/data`
  — ani skryté. Na vnútorný stav je to v poriadku, na čokoľvek testovateľné nie.
- Pridanie poľa do siete **nepridá ho do existujúcich prípadov**. (reference C18)
- Prípad si drží **verziu siete, v ktorej vznikol**. Kto testuje na starom
  prípade, testuje starý model.
- `findCases { it.dataSet... }` **nefunguje**. Filtruj v Groovy, alebo Elastic
  dopytom nad `dataSet.<pole>.textValue` (to je iná cesta, nie to isté).
- `button` vedľa `text` poľa v tom istom `dataGroup`: bez `immediate="true"` na
  tom texte akcia prečíta prázdno — blur a klik sú jedna požiadavka.

**Oprávnenia**

- `perform` je **skratka** pre `assign+cancel+finish+view+set`, nie oprávnenie,
  a `delegate` v nej **nie je**. Rozbaľuje sa prvá, takže
  `<perform>true</perform><cancel>false</cancel>` funguje.
- Tri stavy: chýba = bez názoru, `true` = udeľuje, **`false` = zakazuje**.
  Role sa spájajú cez AND a jediné `false` prebije `true` z inej roly.
- `userRef` rolové oprávnenia **nahradzuje**, nespája. `ROLE_ADMIN` obchádza
  všetko. `finish` navyše vyžaduje byť riešiteľom.
- Rola má `stringId` **razené per verziu siete**. Po re-importe prideľ znova
  (`pfseed`) a v prehliadači sa odhlás a prihlás, inak 403.
- `removeRole(...)` z akcie v 6.3.1 rolu **neodoberie a mlčí**. Použi
  `setProcessRole(userId, importId, siet, verzia, false)`. (B9)

**Menu a zobrazenia**

- Karta vzniká z `uriNodes` v manifeste. URI cesta v
  `createOrUpdateMenuItem(id, **uri**, ...)` je druhý argument, v
  `createFilterInMenu(**uri**, id, ...)` prvý.
- `createOrUpdateMenuItem` sa volá s **deviatimi** argumentmi (projektová
  varianta); jej update cesta nefunguje, takže položku vždy zahoď a postav
  znova — a `deleteMenuItem` pred tým, `deleteFilter` po tom.
- Stĺpec z dátového poľa sa vykreslí len ak je jeho sieť v **`allowedNets`**
  toho zobrazenia. Inak zostane prázdny a nič sa nezaloguje.
- Menu pozná len typy **`Case`** a **`Task`**. „Single task" zobrazenie sa robí
  ako Task zobrazenie zúžené na `transitionId:"..."`.
- Vyhodenie appky z manifestu **nič nezmaže**; uzol URI žije v Elasticsearchi.
  (RUNBOOK 2, Premenovanie)

**Prostredie**

- Java **11**. `LANG=C.UTF-8` a `-Dsun.jnu.encoding=UTF-8`, inak sa sieť
  s diakritikou naimportuje, ale jej XML sa neuloží a `pfsync` ju už neprečíta.
- Jar sa spúšťa z `etask-backend-starter/` (`PdfRunner` asserts na relatívne
  cesty). Najlepšie `tools/up.sh`, ktorý to robí správne.
- Odmietnutie z akcie vracia **HTTP 200** a dôvod v tele ako `error`. Test na
  stavový kód taký blok prehliadne.
- Telo `POST /api/task/{id}/data` je `{taskId: {fieldId: {...}}}`. Ploché telo
  vráti 200 a ticho nezapíše nič.

---

## Tri vrstvy

```
1. Petriflow XML          ← default. Stav, prechody, dáta, oprávnenia.
2. EtaskActionDelegate    ← I/O, cudzie API, čo sa v akcii vyjadriť nedá.
3. Framework / Angular    ← len render a čo engine neposkytuje.
```

Prechod nižšie musí byť odôvodnený vetou, ktorá povie, **ktoré primitívum na
vyššej vrstve chýba**. Ak sa tá veta nedá napísať, problém patrí vyššie.

Vrstva 2 nie je záchranná brzda — je to miesto, kde rastie jazyk. Metóda
v delegáte je nové Petriflow primitívum, volateľné menom z každej siete. Keď ten
istý Groovy píšeš v druhej sieti, presuň ho tam a regeneruj inventár
(`tools/pfapi.py > docs/reference/action-api.md`).

---

## Kde je zvyšok

| chcem | kapitola |
|---|---|
| recept na bežnú úlohu (appka, menu, používatelia, vizuál, verejný prístup, dvojjazyčnosť, Docker) | `pfdoc runbook N` |
| Petriflow ako jazyk, vzory, gotchas C1–C18 | `pfdoc hladaj …` v `petriflow` — **nikdy celé** |
| čo príručka tvrdí zle alebo nepokrýva (A, B, C) | `pfdoc learnings B8b` |
| chyby enginu a knižnice — čo nahlásiť upstream (E1–E20) | `pfdoc engine E20` |
| metódy volateľné z akcie | `docs/reference/action-api.md` |
| rozhodovací postup pre agenta | `.claude/skills/petriflow/SKILL.md` |
| worked example (eForm, SLA, oprávnenia per organizácia) | `pfdoc sd` |
| prečo je repozitár takto postavený | `pfdoc analyza` |

Vzory, ktoré vyšli z reálnych appiek a inak sa vymyslia zle:

| vzor | kde |
|---|---|
| read-only pohľad na celý život prípadu (miesto, ktoré nikto nekonzumuje) | `pfdoc learnings B25` |
| opakované položky (riadky objednávky) — JSON ako zdroj pravdy | `pfdoc learnings B26` |
| konfiguračná appka (limity, schvaľovatelia) — jeden prípad na verziu | `pfdoc learnings B27` |
| schvaľovanie podľa strediska: rola → `userList` → `userRef` | `pfdoc runbook 11` |
| stav, ktorý sa dá preložiť, a názov prípadu bez stavu | `pfdoc runbook 9` |
