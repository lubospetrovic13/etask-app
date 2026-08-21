# eTask ako AI-native Petriflow harness — analýza a prvý prototyp

Analýza toho, čo z tohto repozitára môže byť starter pre AI-driven tvorbu
aplikácií nad Petriflow, a čo tomu dnes chýba. Nie je to potvrdenie konceptu —
koncept je podľa mňa správny, ale z iných dôvodov, než sa na prvý pohľad zdá,
a láme sa na inom mieste, než by človek čakal.

Všetko podstatné nižšie je overené v tomto repozitári alebo za behu na
NAE 6.3.1, nie odvodené.

---

## 0. Najdôležitejšie zistenie: dôkaz z môjho vlastného zlyhania

Pri stavbe Service Desku som potreboval vytvoriť položky bočného menu. Strávil
som na tom hodiny: dekompiloval som `ActionDelegate` z bajtkódu enginu, hádal
poradie argumentov `createFilterInMenu`, omylom vytvoril dva neplatné URI uzly
v Elasticsearchi, ktoré som potom musel ručne mazať, a nakoniec som si napísal
vlastný `menu_item()` helper na idempotenciu, pretože `createOrUpdate*MenuItem`
v 6.3.1 na update ceste padá.

Pritom v tom istom repozitári, v súbore
`etask-backend-starter/src/main/resources/petriNets/configuration_tiles.xml`,
už tri roky existuje toto:

```groovy
createOrUpdateMenuItem("general", "general", "Case", "<dopyt>", "folder", "All cases", [])
setUriNodeData("general", "General", null, "folder")
setUriNodeDataFilters("general", ["general"])
```

Tri riadky. Správne poradie argumentov. Funkčná update cesta — `EtaskActionDelegate`
ju rieši cez `changeFilter`/`changeMenuItem`, čiže obchádza presne ten rozbitý
engine call, na ktorý som narazil. A `setUriNodeData` má parameter `roleIds`,
takže aj časť toho, na čo som napísal nový Java servis, tam bola.

**Toto je dôkaz tvojej tézy, nie ilustrácia.** Kompetentný agent s celým
repozitárom po ruke, s prístupom k bajtkódu, k dokumentácii aj k bežiacej
instancii, si postavil horšiu verziu už existujúceho extension pointu — pretože
nemal ako vedieť, že existuje. Nešlo o schopnosť. Šlo o **absenciu
instruction layeru**.

A má to druhý, drahší dôsledok: v `UriNodeData` sú teraz **dve** polia pre to
isté — pôvodné `processRolesIds` (stringId rolí, klientske filtrovanie) a moje
`requiredProcessRoles` (importId, serverové). Nie sú to duplikáty len opticky,
sú v inom id-priestore. To je technický dlh, ktorý vznikol výhradne z neznalosti
vlastnej codebase.

Ak má starter riešiť jednu vec, tak túto.

---

## 1. Čo sa dá použiť ako základ (a je to lepšie, než sa zdá)

Vlastný kód je prekvapivo malý — a to je pre starter tá najlepšia správa:

| časť | riadkov | rola v starteri |
|---|---:|---|
| backend Java + Groovy | 2 240 | framework/runtime layer |
| frontend TypeScript | 2 758 | framework/runtime layer |
| Petriflow siete | ~7 500 | **aplikačná logika — to, čo píše AI** |
| dokumentácia | 3 852 | reference knowledge |

Pomer je už dnes ten správny: aplikačná logika je väčšia než framework, ktorý ju
nesie. To je presne to, čo od harnessu chceš.

Ďalej je hotové a použiteľné:

* **`EtaskActionDelegate`** (238 r.) — kanonický extension point. Dedí
  `ActionDelegate`, je `@Component`, a všetko, čo v ňom je, je z Petriflow akcie
  volateľné menom. Toto je tá „zapuzdrená implementácia", o ktorej píšeš, a už
  funguje.
* **`NetRunner` + `PetriNetEnum`** — siete sa importujú zo súborov pri starte,
  aplikačná logika je oddelená od runtime kódu. Toto je už dnes presne ten model
  „pri štarte sa načíta XML reprezentácia".
* **`<resources>` v `pom.xml`** — siete idú do jaru priamo z modelovacieho
  priečinka, takže neexistuje druhá kópia, ktorá by sa rozišla.
* **`docs/petriflow_reference.md`** (1 874 r.) + **`PETRIFLOW_LEARNINGS.md`**
  (460 r.) — surová reference knowledge. Nie je to ešte skill file, ale obsah tam je.
* **Service Desk** (5 sietí) — netriviálny worked example: verejný eForm,
  viackrokový wizard cez taskRef, per-organizačné oprávnenia, child casy,
  SLA. Pre agenta je funkčný príklad cennejší než špecifikácia.

---

## 2. Kde sa koncept láme

Toto je jadro analýzy. Nie „čo dorobiť", ale **kde to nefunguje a prečo**.

### 2.1 Petriflow nemá spätnú väzbu — to je hlavný problém, nie expresivita

AI harness stojí a padá na feedback loope. Petriflow dnes má taký, že sa nedá
programovať s istotou:

* Akcie sú **Groovy v CDATA vnútri XML**. Nič ich pred behom neskontroluje.
  Preklep v názve poľa, zlá property, chybné poradie argumentov — všetko až za behu.
* Zlyhania sú **tiché alebo zavádzajúce**. Zdokumentované prípady z jedného týždňa:
  * `u?._id` vyhodí `MissingPropertyException` — `?.` chráni pred null, nie pred
    chýbajúcou property. Zhodí **celú akciu v strede**: časť zmien zapísaná,
    zvyšok nie, v odpovedi nič. Prejavilo sa to ako „`setData` aplikuje len prvé
    dva záznamy mapy" a moja diagnóza bola tri hypotézy vedľa.
  * `findCase { it.stringId.eq(id) }` vráti vždy `null` — `Case` v mongo pole
    `stringId` nemá. V logu je len INFO, nie chyba.
  * `async.run { }` výnimku spolkne. Zle prenesené pole = prázdny cieľový case
    bez akejkoľvek stopy.
  * Zápis do vlastného casu po `createFilterInMenu` sa neuchová — ani `change`,
    ani `setData`.
* **Neexistuje spôsob, ako sieť otestovať.** Žiadny unit test, žiadny dry-run.
  Overenie = nahraj do bežiacej instancie a klikaj. (Toto je čiastočne vyriešené
  v tomto branchi — `tools/pfcheck.sh` — ale stále to overuje len import,
  nie chovanie za behu.)

Pre človeka je to otrava. Pre AI agenta je to fatálne: agent generuje, nedostane
signál, považuje to za hotové. **Toto je skutočný dôvod, prečo implementácia
uteká do Angularu** — nie že by Petriflow nevedel daný problém vyjadriť, ale že
v TypeScripte agent dostane chybu za dve sekundy a v Petriflow za dvadsať minút
manuálneho klikania. Feedback loop rozhoduje, kam kód utečie.

### 2.2 Tri navzájom si odporujúce zdroje pravdy o dialekte

Každá sieť v repozitári deklaruje
`xsi:noNamespaceSchemaLocation="https://petriflow.com/petriflow.schema.xsd"`.
Overil som, čo tá schéma hovorí, a porovnal s realitou:

| zdroj | poradie v `<data>` |
|---|---|
| oficiálna XSD v1.1.0 | `placeholder` → `desc` → … → `init` → … → `component` |
| NAE 6.3.1 za behu | prijme aj `component` pred `init` |
| `PETRIFLOW_LEARNINGS` B5 | `desc` hneď za `title`, teda pred `placeholder` |

Všetky siete v tomto repozitári majú `component` pred `init` a **importujú sa**.
Engine je teda voľnejší než schéma, a náš vlastný zápisník tvrdí tretiu vec.

Navyše: `petriflow_schema.xsd` priložená v jare enginu je len stub, ktorý
`<xs:include>`-uje tú **živú URL**. Čiže „schéma enginu" je to, čo petriflow.com
serveruje dnes — nie to, čo engine v 2023 prijímal.

Dopad na harness: agent, ktorý urobí to najprirozumnejšie (otvorí schému
z hlavičky siete), sa naučí **iný dialekt, než jeho runtime prijme**. A XSD
validácia sa ako gate použiť nedá.

### 2.3 Algebra oprávnení nevie vyjadriť prienik

> **Doplnené:** primitív `usersWithRole()` z toho medzitým urobil jednoriadkovú
> záležitosť. Nerieši to podstatu — engine stále nepozná prienik — ale prestalo
> to byť bespoke kód v každej sieti.

`roleRef` a `userRef` sa **zjednocujú, nie prienikajú**. „Agent a zároveň
pridelený tomuto zákazníkovi" sa deklaratívne napísať nedá. V Service Desku som
to musel obísť tak, že som rolu presunul do dát (zákazník má dva zoznamy ľudí a
tiket si ich kopíruje). Funguje to a je to obhájiteľný model, ale je to
**workaround pre chýbajúce primitívum**, nie návrh.

To je konkrétna odpoveď na tvoju otázku 3: prvé primitívum, ktoré treba doplniť,
nie je nová akcia, ale **skladateľná podmienka oprávnenia**.

### 2.4 Verziovanie zabíja iteračný cyklus

Rola má `stringId` razené **per verzia siete**. Po re-importe užívateľ na casoch
novej verzie prístup stráca. Casy si držia verziu siete, v ktorej vznikli. Za
jednu session som sieť importoval 12-krát a po každom importe musel znovu
prideliť role.

Pre produkciu je to správne (nemenné, auditovateľné). Pre AI development loop je
to brutálne: každá iterácia znamená manuálny setup. Starter musí mať
**idempotentný re-seed** — inak agent po tretej iterácii testuje na rozbitom stave.

### 2.5 Čo Petriflow naozaj nevie a patrí mimo neho

Čestný zoznam z tohto týždňa — miesta, kde som **musel** ísť mimo Petriflow,
a bolo to správne:

| požiadavka | prečo nie Petriflow |
|---|---|
| taskRef sa má preklopiť bez reloadu | čisto klientský render; Petriflow nemá pojem „prekresli" |
| viditeľnosť uzla menu podľa roly | `UriNode` nemá pole pre role a endpointy enginu neberú usera |
| verejný single-task cold link | bootstrap anonymnej session v knižnici; tri pokusy, slepá ulička |

Prvé dva sú legitímne framework-layer. Tretí je defekt knižnice. **Toto je
hranica**, ktorú treba napísať do skill file: Petriflow je jazyk pre *stav,
prechody, dáta a oprávnenia case-u*. Nie je jazyk pre render a nie je jazyk pre
infrastruktúru okolo requestu.

---

## 3. Prvý prototyp: zatvorenie feedback loopu

Z analýzy vyplýva, že najvyššiu páku má spätná väzba, nie ďalšia dokumentácia.
V branchi sú preto tri nástroje, každý vidí niečo, čo ostatné nie:

| nástroj | vidí | nevidí | cena |
|---|---|---|---|
| `pflint.py` | štruktúru XML, odkazy, tiché pasce | Groovy (je to text v CDATA) | 0,3 s, bez závislostí |
| `pfgroovy.py` | syntax Groovy v akciách | čo engine prijme | 3 s, JDK + groovy jar |
| `pfcheck.sh` | **všetko — ground truth** | chovanie za behu | 5 s, bežiaci engine |
| `pftest.sh` | regresiu nástrojov samotných | | |

`pflint` **vedome nekontroluje poradie elementov**, práve preto, že tri zdroje
pravdy si odporujú (časť 2.2). Linter, ktorý označkuje funkčný kód, naučí agenta
linter ignorovať.

`pfcheck` nie je `curl`, a to z dvoch dôvodov, ktoré sú samé zistením:

1. Import endpoint pri chybe vracia **holé `{"status":500}` bez dôvodu**.
   Príčina je výlučne v logu servera, takže `pfcheck` log číta a vytiahne root
   cause. Toto ma tento týždeň stálo hodiny — „500" nepovie, či je to preklep
   v id, diakritika v názve procesu alebo chýbajúca rola.
2. Zlyhaný import **nie je atomický** — stihne vytvoriť procesné role a
   prihlásenie potom vracia 500. `pfcheck` preto po každom importe overí login.

### Čo to našlo

**pflint na ôsmich sieťach: 0 chýb, 3 upozornenia, všetky tri skutočné.**

1. `sd_work_item.xml` — `btn_done` čítal `wi_result` bez `immediate="true"`.
   **Moja vlastná sieť, ktorú som týždeň testoval.** Cez REST sa to neprejavilo,
   hodnota šla samostatným volaním; cez UI (blur + klik v jednej požiadavke) by
   riešiteľ nedokázal úlohu dokončiť. Opravené.
2. `ai_config.xml` — `btn_run_test` číta `mail_from` s tou istou pascou. Nie je
   to moja sieť, len hlásim.
3. `sd_request.xml` — `async.run` okolo prenosu do ticketu.

### Čo to naučilo o stavbe takýchto nástrojov

`pfgroovy` pri prvom spustení hlásil **47 syntaktických chýb na sieťach, ktoré
engine skompiluje bez námietky**. Dvakrát za sebou, z dvoch rôznych príčin:

* NAE hlavička akcie (`pole: f.pole, iné: f.iné;`) **nie je Groovy** —
  jednopoložková verzia sa náhodou parsuje ako labeled statement, viacpoložková
  už nie. Treba ju odstrihnúť, NAE si ju prekladá sám.
* Samostatný parser nemá classpath enginu, takže `org.bson.types.ObjectId`
  neresolvoval. Riešenie je obmedziť kompiláciu na fázu parsovania.

Z toho vyplýva pravidlo, ktoré patrí do skill file: **ground truth je engine.
Keď si offline nástroj a engine odporujú, chyba je v nástroji.** Preto existuje
`pftest.sh` — sedem testov, a tá dôležitejšia polovica je, že nástroj nesmie
označiť funkčný kód.

Mimochodom, ten istý mechanizmus opravil aj moje vlastné tvrdenie: myslel som si,
že engine akcie pri importe nekompiluje. Nekompiloval ich preto, že moja prvá
fixture bola zle štruktúrovaná a **žiadnu akciu neobsahovala**. Engine ich
kompiluje.

## 4. Odpovede na zvyšné otázky

### 4. Hranica medzi Petriflow a frameworkovým kódom

Navrhujem tri vrstvy s jasným pravidlom, kedy sa smie prejsť nižšie:

```
1. Petriflow XML          ← default. Stav, prechody, dáta, oprávnenia case-u.
2. Custom action delegate ← keď treba I/O, cudzie API, alebo výpočet, ktorý sa
                            v Groovy akcii nedá vyjadriť čitateľne.
3. Framework/runtime kód  ← len render, HTTP layer, a to, čo engine neposkytuje
                            (napr. filtrovanie menu podľa roly).
```

Pravidlo pre agenta: **nikdy nezačínaj na vrstve 3.** Prechod na nižšiu vrstvu
musí byť odôvodnený vetou, ktorá povie, ktoré primitívum na vyššej vrstve chýba.
Tá veta je zároveň bug report pre framework.

### 5.–6. Štruktúra repozitára a čo má byť v skill files

Skill files nemajú byť prepis referencie. Majú obsahovať to, čo sa z kódu
**nedá vyčítať**:

* **Inventár extension pointov** — to, čo mne chýbalo. Zoznam metód
  `EtaskActionDelegate` s presnými signatúrami a jednou vetou „na čo to je".
  Toto je najvyššia priorita.
* **Rozhodovací postup** — kedy Petriflow, kedy delegate, kedy framework.
* **Tiché pasce** — `PETRIFLOW_LEARNINGS` prerobené na pravidlá, nie príbehy.
* **Varovanie o dialekte** — schéma z hlavičky siete nie je pravda; pravda je
  `reference/petriflow.schema.v1.1.0.xsd` **a** runtime, a runtime vyhráva.
* **Worked examples** — Service Desk ako referenčný vzor.

### 7. MCP server vs. template repository

**Template repository, jednoznačne, a MCP až keď preukáže potrebu.**

MCP server nad codebase rieši problém, ktorý tu nie je. Vlastný kód je 5 000
riadkov — to sa do kontextu zmestí celé. Problém nebol nikdy „nezmestí sa mi
knowledge do promptu"; problém bol **„neviem, že tá knowledge existuje"**.
To MCP server nerieši, to rieši skill file a dobrá štruktúra.

MCP začne dávať zmysel na inej veci: nástroj `import_and_validate(net.xml)`,
ktorý sieť nahrá do bežiacej instancie a vráti chybu — teda **ako feedback loop,
nie ako knowledge base**. To je ale zbytočné robiť ako MCP, keď to môže byť
skript, ktorý agent zavolá.

### 8. Ako pripraviť branch na odčlenenie

Blokery, ktoré som identifikoval, sú **vyriešené** — každý z nich bol overený, nie
predpokladaný:

| bloker | stav |
|---|---|
| `.idea/` v repozitári (5 súborov) | z gitu von, v `.gitignore` |
| GHCR cesta `lubospetrovic13/*` | pipeline si owner derivuje sama (`github.repository_owner`); v `.env.example` je placeholder |
| JWT kľúč gitignored → verejné formuláre 401 | `tools/bootstrap.sh` lokálne, `docker-entrypoint.sh` v kontejneri (do volume, aby prežil restart) |
| `super`/`password` na verejnej adrese | `ADMIN_PASSWORD` je v compose **povinné** (`:?`), inak compose odmietne nabehnúť |
| 4 testovacie účty s `test1234`, jeden ROLE_ADMIN | bez `ETASK_TEST_PASSWORD` sa **nevytvoria** (`EtaskUserCreator` preskočí prázdne heslo) |
| `technical@netgrif.com` s heslom `password` | to isté, `TECHNICAL_PASSWORD` |

Plus poistka, ktorá je pri šablóne dôležitejšia než jednotlivé opravy:
`EtaskRunner` pri každom starte skontroluje bezpečnostnú pozíciu a nájdené veci
**vypíše ako WARN**. Nič nemení a nič nezhodí — len sa to nedá prehliadnuť.
Overené v oboch smeroch: nesprávne nastavená instancia dá 3 zistenia, správne
nastavená „v poriadku".

Prečo poistka a nie len opravy: šablónu si niekto naklonuje, zmení tri veci a
nasadí. Zoznam v dokumentácii sa dá preskočiť, WARN v logu pri každom starte
menej.

**Jedno rozhodnutie zostáva a nie je technické:** Service Desk je zároveň worked
example (5 sietí, netriviálny, agent sa z neho učí dialekt spoľahlivejšie než zo
schémy) aj konkrétna aplikácia pre konkrétneho zákazníka. Buď ide do startera
ako `examples/`, alebo von. Nesťahoval som ho nikam — to je tvoje rozhodnutie,
nie moje.

## 5. Čo je hotové v tomto branchi a čo je ďalší krok

Hotové:

* `tools/pflint.py` — statická kontrola XML, 0 falošných pozitív na 8 sieťach
* `tools/pfgroovy.py` — syntax Groovy, 0 falošných pozitív na 90 akciách
* `tools/pfcheck.sh` — ground truth import, root cause z logu, kontrola loginu
* `tools/pftest.sh` + `tools/fixtures/` — regresia nástrojov, 7 testov
* `tools/pfapi.py` + `reference/action-api.md` — generovaný inventár extension pointov
* `.claude/skills/petriflow/SKILL.md` + `CLAUDE.md` — instruction layer
* `tools/pfseed.py` + `seed.json` — idempotentné prideľovanie rolí, oprava osirelých
* `tools/README-petriflow-tools.md` — kedy ktorý a prečo tri
* `reference/petriflow.schema.v1.1.0.xsd` — oficiálna schéma offline
* oprava `wi_result` v `sd_work_item.xml`

Ďalší krok v poradí podľa páky:

1. ~~Inventár extension pointov ako skill file.~~ **Hotové** — `tools/pfapi.py`
   generuje `reference/action-api.md` (169 metód enginu + vlastné metódy
   projektu), skill file je v `.claude/skills/petriflow/SKILL.md`, boundary
   pravidlo v `CLAUDE.md`. Generované zámerne: ručný zoznam by driftoval
   s verziou enginu a nesprávny zoznam je horší než žiadny, preto je kontrola
   aktuálnosti (`pfapi --check`) súčasťou `pftest.sh`.
2. ~~Idempotentný re-seed rolí.~~ **Hotové** — `tools/pfseed.py` + `seed.json`,
   deklaratívny cieľový stav podľa `importId`, idempotencia testovaná v `pftest.sh`.
   Vedľajší nález: zlyhaný import nechá osirelé role a taký užívateľ sa **nedá
   prečítať cez REST vôbec** (`/api/user/search` aj `/api/user/me` vracajú 500).
   Cez API sa to opraviť nedá, preto `--repair` ide priamo do databázy. Overené
   na `super`, ktorý mal 6 osirelých rolí po importe spadnutom na diakritike.
   Seedovanie demo casov (zákazníci) zostáva — je to ale SD-špecifické, nie
   infrastruktúra.
3. ~~Skladateľná podmienka oprávnenia.~~ **Hotové** — `usersWithRole()`,
   `hasProcessRole()`, `userIdsOf()` v `EtaskActionDelegate`. Engine sa zmeniť
   nedá, takže prienik sa počíta do userList poľa a `userRef` naň odkazuje;
   nové je to, že je to jeden volateľný primitív a nie bespoke kód v každej
   sieti. `sd_ticket` ho už používa. Overené: človek v tíme zákazníka bez
   príslušnej roly prístup nedostane.
4. ~~Zjednotiť `processRolesIds` a `requiredProcessRoles`.~~ **Hotové** — ale inak,
   než som plánoval. `processRolesIds` mal jediného čitateľa: serializáciu pre
   klientský filter nad zoznamom, ktorý server už prefiltroval. Správne
   zjednotenie preto nebolo zladiť dve polia, ale **zrušiť to klientské
   filtrovanie** — porovnávalo stringId rolí, ktoré sa razia per verziu siete,
   takže po každom re-importe vedelo len ubrať uzly, na ktoré užívateľ právo má.
   Zostalo jedno pole (`requiredProcessRoles`, importId) a jedno miesto, kde sa
   rozhoduje (`UriNodeVisibilityService`).
5. ~~Odčlenenie do samostatného repozitára.~~ **Blokery vyriešené** (časť 8).
   Zostáva rozhodnúť, či Service Desk ide do startera ako `examples/` alebo von,
   a potom `git subtree`/nový repozitár.
