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
* **`NetRunner`** — siete sa importujú zo súborov pri starte, aplikačná logika je
  oddelená od runtime kódu. Toto je už dnes presne ten model „pri štarte sa načíta
  XML reprezentácia". (Zoznam bol pôvodne Java enum; nahradil ho manifest
  `processes.json` — viď bod 6 v časti 5.)
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

> **Opravené oproti prvej verzii tejto analýzy.** Vrstvu 2 som opísal defenzívne
> („keď sa to v akcii vyjadriť nedá"), a to je zlé rámovanie. Delegát nie je
> záchranná brzda — je to mechanizmus, ktorým **rastie jazyk**. Metóda pridaná
> do `EtaskActionDelegate` je nové Petriflow primitívum, volateľné menom
> z každej siete, bez importu a bez zásahu do frontendu. Preto je vrstva 3 skoro
> vždy zbytočná, a preto platí pravidlo promócie: keď ten istý Groovy píšeš
> v druhej sieti, presuň ho do delegáta.
>
> Cena za to je dynamický dispatch: preklep v názve metódy **engine nezachytí**
> (overené — naimportuje sa a za behu vráti HTTP 200, kým akcia padne na
> `MissingMethodException`). Preto `pflint` odvtedy kontroluje volania proti
> `docs/reference/action-api.md`. Rozširovanie slovníka a aktuálny inventár sú dve
> strany tej istej veci.

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
  `docs/reference/petriflow.schema.v1.1.0.xsd` **a** runtime, a runtime vyhráva.
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
* `tools/pfapi.py` + `docs/reference/action-api.md` — generovaný inventár extension pointov
* `.claude/skills/petriflow/SKILL.md` + `CLAUDE.md` — instruction layer
* `tools/pfseed.py` + `seed.json` — idempotentné prideľovanie rolí, oprava osirelých
* `tools/README-petriflow-tools.md` — kedy ktorý a prečo tri
* `docs/reference/petriflow.schema.v1.1.0.xsd` — oficiálna schéma offline
* `processes.json` + `ProcessManifest` — nová appka bez zásahu do Javy
* Service Desk odpojený od frameworku — je to príkladová aplikácia, nie výbava
* `examples/skeleton.xml` — najmenšia funkčná sieť ako východisko
* oprava `wi_result` v `sd_work_item.xml`

Ďalší krok v poradí podľa páky:

1. ~~Inventár extension pointov ako skill file.~~ **Hotové** — `tools/pfapi.py`
   generuje `docs/reference/action-api.md` (169 metód enginu + vlastné metódy
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
6. ~~Pridanie aplikácie bez zásahu do frameworku.~~ **Hotové** — a bol to
   najtvrdší nález celej tejto časti. Test bol jednoduchý: čerstvý klon,
   `bootstrap.sh`, a pridať appku. Nedalo sa to bez editovania **`NetRunner`
   (Java enum)** a **`pom.xml` (`<includes>`)** — teda šablóna, ktorá káže
   nepísať Javu, vyžadovala napísať Javu, aby sa dala použiť. Riešenie:
   `processes.json` ako manifest (poradie + zoznam), `pom.xml` kopíruje
   `processes/*.xml` hromadne, `NetRunner` číta manifest z classpath
   a identifikátor si berie regexom z `<id>` v XML — takže sa nemôže rozísť
   so sieťou tak, ako sa rozchádzal enum.

   Overené v klone end-to-end: 1 XML + 1 riadok manifestu → runner sieť
   naimportoval (existujúce preskočil), case sa vytvoril, akcia tlačidla
   prebehla, `changeCaseProperty("title")` a dátové pole sa zapísali.

   Pasca, na ktorej to najprv padlo: **stale `target/`**. Maven pri existujúcom
   `target/` preskočí kopírovanie zdroja a jar vyjde bez novej siete, bez
   varovania. To je ten istý tvar chyby ako pri presune adresára po merge
   s `main` — Maven mlčí a zlyhá až runtime.
7. ~~Rozhodnúť, či Service Desk zostáva ako `examples/`.~~ **Zostáva** — ale to
   rozhodnutie malo cenu len vtedy, ak SD prestane byť súčasťou frameworku.
   Tri miesta ho poznali po mene:

   | bolo | je |
   |---|---|
   | `SdMenuRunner` s natvrdo `service_desk/sd_menu` | `BootstrapCaseRunner` nad `bootstrapCase` v manifeste |
   | `UriNodeDataRunner.NODES` — mapa v Jave | `uriNodes` v manifeste |
   | `EtaskRunnerController` komentár o SD | popis mechanizmu |

   Kritérium bolo jednoduché: **odstránenie príkladovej appky nesmie znamenať
   zásah do Javy.** Dnes je to päť XML súborov a tri záznamy v manifeste.

   Vedľajší nález pri prevode: `UriNodeDataRunner` porovnával `Set` z dokumentu
   s hodnotou z konfigurácie. Kým bola konfigurácia v Jave (`as Set`), sedelo to;
   z JSON prídu zoznamy, takže porovnanie by nikdy nesedelo a runner by
   zapisoval pri každom štarte — „idempotentný" len na papieri. Preto sa obe
   strany prevádzajú na `Set<String>` pred porovnaním.

---

## 6. Koľko to stojí na tokenoch — a čo s tým

Merané na tomto repozitári (odhad ~4 znaky na token, ide o rád veľkosti).

### Kde tokeny boli

| čo | ~tokenov | kedy sa to čítalo |
|---|---|---|
| `CLAUDE.md` | 3 014 | **vždy**, v každom sedení |
| `docs/reference/cheatsheet.md` | 1 760 | na začiatku úlohy |
| skill `petriflow` | 3 188 | pri sieťach a akciách |
| `docs/RUNBOOK.md` | 14 466 | celý, aj keď išlo o jednu kapitolu |
| `docs/petriflow_reference.md` | 27 120 | celý, alebo vôbec |
| všetko dokopy | **86 644** | |

Otázka „ako pridám kartu do bočného menu?" stála **19 240 tokenov**
(`CLAUDE.md` + cheatsheet + celý RUNBOOK) — a druhá otázka v tom istom sedení
zaplatila RUNBOOK znova, ak medzitým vypadol z kontextu.

### Čo sa ukázalo, keď sa to zmeralo

**Duplicita nie je problém.** Naprieč všetkými dokumentmi je doslovne zopakovaná
**jedna** veta dlhšia než 90 znakov (z 1 098). Dokumentácia nie je kopírovaná,
je paralelná — každý súbor hovorí o tom istom z inej strany a pre iný moment.
Zlučovať ju by teda nič neušetrilo a niečo by sa stratilo.

**Problém je granularita.** Čítalo sa po súboroch, lebo nástroje čítajú súbory.

### Čo sa spravilo

1. **`tools/pfdoc.py`** — číta kapitolu, nie súbor, a `hladaj` vypíše len
   **nadpisy** kapitol s ich cenou (telo si vypýtaš zvlášť; inak by sa grep
   výstupom ušetrené tokeny hneď minuli späť).

   | kapitola | ~tokenov | namiesto |
   |---|---|---|
   | `runbook 4` (menu) | 2 760 | 14 466 |
   | `runbook 12` (Docker) | 1 905 | 14 466 |
   | `learnings B25` | 341 | 9 063 |
   | `engine E20` | 430 | 5 795 |

2. **`CLAUDE.md` na diéte: 3 014 → 1 790 tokenov (−41 %).** Ostali v ňom len
   rozhodnutia, pravidlá a smerovník; vysvetlenia sa presunuli tam, kde už boli.
   Pravidlo pre ďalšie škrtanie: **škrtá sa vysvetlenie, nikdy pravidlo**, a po
   každom škrte musí ostať ukazovateľ, ktorý menuje presný príkaz `pfdoc`.

3. **Cheatsheet smeruje príkazmi**, nie názvami súborov, a pribudla v ňom
   tabuľka vzorov z reálnych appiek (B25–B27, schvaľovanie podľa strediska,
   preložiteľný stav).

Nová cena tej istej otázky o menu: `CLAUDE.md` (1 790) + cheatsheet (1 957) +
`pfdoc hladaj` (~150) + `runbook 4` (2 760) = **6 657 tokenov, −65 %**. Druhá
otázka v tom istom sedení stojí už len cenu svojej kapitoly.

### Čo by som spravil ďalej (v poradí podľa pomeru úžitok/riziko)

1. **Skill `petriflow` (3 188) rozdeliť** na krátky rozhodovací router (~800)
   a sekcie na dožiadanie. Načítava sa pri každej úlohe so sieťou, takže je to
   druhý najdrahší „vždy" po `CLAUDE.md`.
2. **Zdieľaná knižnica akceptačných testov.** `sccheck`, `dvcheck`, `pucheck`
   a `majetokcheck` nesú každý ~150 riadkov identického `Client`a a pomocníkov.
   `tools/pftestlib.py` by z písania testu novej appky spravil desiatky riadkov
   namiesto stoviek — a šablóna má práve toto robiť lacným.
3. **Skelet nech učí viac.** `pfnew` už nesie preložiteľný stav a `pripoj_do_uzla`;
   pridať read-only stavový pohľad (B25) by nový appke dalo správny vzor zadarmo,
   bez jediného prečítaného riadku dokumentácie.
4. **CI na kvalitu, nie len na build.** `deploy.yml` stavia obrazy; `pflint`,
   `pfgroovy`, `pfi18n`, `pfview` a `pftest` v ňom nebežia. Sú to sekundy a je to
   presne tá vrstva, ktorá chytá tiché chyby.
5. **`pfdoc --json`** pre agentov (zoznam kapitol s cenami strojovo), aby si
   vedeli naplánovať čítanie dopredu.
6. **Dve siete v `processes/` nie sú v manifeste** (`ai_config.xml`,
   `sd_request.xml`) — v engine neexistujú, ale `pflint` ich lintuje a vyzerajú
   ako súčasť dodávky. Buď doplniť do `import`, alebo vyhodiť.

### Čo sa zámerne NEškrtalo

Bezpečnostné a prostredové pravidlá (Java 11, `LANG=C.UTF-8`, JWT kľúč,
„nespúšťať `pfsync --sync` na produkciu"), pravidlo troch vrstiev a zoznam
„čo nerobiť". To sú veci, ktorých vynechanie stojí hodiny ladenia — a ich cena
v tokenoch je rádovo nižšia než jedno také ladenie.

---

## 7. Čo ukázalo postavenie jednej appky a preskupenie celého portálu

Druhý priebeh tým istým harnessom, s odstupom. Vzniklo pri ňom: aplikácia
**Onboarding** (paralelné vetvy, AND-join, smerovanie na konkrétneho
nadriadeného), štyri rozšírenia platformy (podpísaný odkaz na model pre builder,
`ROLE_ADMIN` v UI, katalógové zobrazenia, hľadanie v zozname procesov)
a preskupenie **19 sietí** do kategórií `hr / financie / it / admin` naprieč
štyrmi repozitármi. Na konci **449 kontrol v piatich akceptačných sadách**.

Zaujímavé na tom nie sú tie funkcie. Zaujímavé je, čo ten priebeh ukázal o tom,
ako sa Petriflow appky s AI stavajú — a kde to aj s celým týmto harnessom stále
padá.

### 7.1 Statická kontrola prešla, a backend nenaštartoval

Toto je hlavné zistenie tohto kola. Pred nasadením preskupených sietí hlásili
všetky offline nástroje čisto:

```
pflint:   19 sieti, 0 chyb, 0 upozorneni
pfgroovy: 19 sieti, 216 akcii, 0 syntaktickych chyb
pfview:   0 chyb, 0 upozorneni
pfsync:   vsetky siete sedia s tym, co drzi engine
```

Na čistej databáze backend **nenaštartoval**. A keď po oprave naštartoval,
admin-only katalóg „Všetky prípady" videl **každý prihlásený používateľ**.

Obe chyby boli v poradí operácií pri štarte:

| chyba | prečo ju nič nechytilo |
|---|---|
| `setUriNodeData("general", …)` bežalo v udalosti `upload`, teda pri importe prvej siete — uzol vtedy ešte neexistuje | `NullPointerException` z vnútra Groovy, `NetRunner` zhodil kontext. Na **existujúcej** inštancii uzol z minulého behu bol, takže sa to nikdy neprejavilo |
| `UriNodeDataRunner` bežal pred `BootstrapCaseRunner`om, takže uzol `general` v čase konfigurácie neexistoval a runner ho preskočil | Uzol bez `UriNodeData` je **zámerne** viditeľný pre všetkých (fail-open). Žiadna chyba, žiadny log — len karta, ktorá tam nemá čo robiť |

Obe som **zaviedol ja**, v predchádzajúcom kroku toho istého vlákna, keď som
stavanie katalógových položiek presunul z `upload` do `create`. Overil som to
vtedy proti bežiacej inštancii, bolo to zelené, a nešlo o nedbalosť: na bežiacej
inštancii tá chyba **neexistuje**.

Z toho plynie oprava pravidla, ktoré tento repozitár opakuje od začiatku.
„Ground truth je bežiaci engine" je pravda, ale nestačí — **bežiaca inštancia
nesie stav z predchádzajúcich behov a presne ten maskuje chyby poradia.**

| úroveň | chytí | nechytí | cena |
|---|---|---|---|
| `pflint`, `pfgroovy`, `pfi18n`, `pfview` | štruktúra, syntax, preklady, render | čokoľvek, čo závisí od stavu enginu | sekundy |
| import do **bežiaceho** enginu (`pfsync --sync`, `pfcheck`) | sieť sa naimportuje, akcie bežia | poradie pri štarte, prvý beh runnerov, prázdne indexy | desiatky sekúnd |
| **čistá databáza** (`up.sh --docker --fresh --build`) | poradie runnerov, prvý import, fail-open uzly, chýbajúce seedy | výkon, migrácie existujúcich dát | ~10 minút |
| akceptačné sady | čo appka naozaj robí a kto čo vidí | čo nikto nenapísal ako kontrolu | minúty |

**Čistá databáza je samostatná úroveň overenia, nie luxus.** Patrí pred každé
odovzdanie, ktoré sa dotklo poradia štartu, uzlov URI, manifestu alebo runnerov.
Doplnené do `cheatsheet.md` aj do reťazca v `CLAUDE.md`.

### 7.2 Drahé chyby neboli v písaní kódu, ale v uverení dokumentu

Tri prípady z tohto vlákna, kde bol zdrojom pravdy **vlastný repozitár** a mýlil sa:

* **`dataSet.<pole>.textValue` pri `enumeration_map`.** Takto to stálo v RUNBOOKu,
  v cheatsheete aj v generátore `pfnew` — teda každá takto vygenerovaná appka
  dostala zobrazenie, ktoré nenájde nikdy nič. Kľúč je v `.keyValue`;
  `.textValue` drží preložené popisky (všetky jazyky naraz). Jedno meranie:
  `keyValue:"nastupil"` → 2 prípady, `textValue:"nastupil"` → 0.
* **Hľadanie procesov podľa názvu.** Engine má `title` explicitne v tej istej
  vetve, ktorá robí regex — ale `PetriNet.title` je v Mongu `I18nString`, takže
  regex nad dokumentom nemá o čo oprieť. Nenájde **nikdy nič** (`ENGINE_ISSUES`
  E21). Vedľajší nález z toho istého merania: hodnota ide do regexu
  neescapovaná, takže `{"title": "("}` vráti **HTTP 500**.
* **Ako odovzdať model builderu.** Štyri hypotézy, tri vyvrátené meraním za pár
  minút: token v query stringu (401 vo všetkých variantoch), anonymná session
  (401), `data:` URL s modelom (nginx buildera vráti **414** už pri 21 kB, bežná
  sieť má 10–50 kB). Zostala jedna a tá funguje.

Spoločné je, že **každú z nich vyriešilo jedno meranie proti bežiacemu enginu**,
a každá by inak prešla do dodávky ako „funguje to, len to nič nenájde".

Pre agenta z toho plynie konkrétne pravidlo: keď je tvrdenie lacné odmerať
(jeden `curl`, jeden dopyt), **odmeraj ho, aj keď je napísané v tomto repozitári**
— najmä ak z neho generuješ kód pre ďalšie aplikácie.

### 7.3 Tiché zlyhanie je stále dominantný režim

Nové položky do katalógu, všetky z tohto vlákna a všetky overené za behu:

| tiché zlyhanie | ako sa prejaví |
|---|---|
| dopyt na `enumeration_map` cez `.textValue` | zobrazenie je prázdne, HTTP 200 |
| hľadanie procesu podľa `title` | prázdny výsledok, HTTP 200 |
| `allowedNets: []` na zobrazení | tlačidlo „+" vráti „Žiadne povolené siete" |
| uzol URI bez `UriNodeData` | karta viditeľná pre všetkých |
| `required` na `boolean` | prejde aj s hodnotou `false` |
| `roleRef` + `userRef` na prechode | zjednotia sa, nie prienik — smerovanie prestane platiť |
| predvoľba vnorená v prázdnej zbaliteľnej sekcii | je v DOM a nedá sa k nej dostať |
| `NetRunner` importuje len chýbajúce siete | zmena XML frameworkovej siete sa na existujúcej inštancii nikdy neprejaví |
| premenovanie identifikátora siete | je to nová sieť; staré prípady zostanú mimo nových zobrazení |

Posledné dve stoja za zvláštnu pozornosť, lebo sa týkajú **údržby**, nie vývoja:
appka postavená správne prestane fungovať tým, že sa okolo nej niečo premenuje.

### 7.4 Čo z refaktoru spravili akceptačné sady

Preskupenie 19 sietí do kategórií je mechanická zmena, ktorú offline nástroje
odobrili bez výhrady. Sady našli dve veci, ktoré by inak odišli do dodávky:

1. **Karty sa prestali dať nájsť.** `/api/v2/uri/root` vracia len **priame deti
   koreňa** — a tým je odteraz kategória, nie appka. Každý test, ktorý hľadal
   kartu medzi deťmi koreňa, by zlyhal bez ohľadu na to, či appka funguje.
   Riešené `pftestlib.uri_paths(deep=True)`.
2. **Rola `spravca_majetku` nebola pridelená nikomu** — ani na `main`, teda
   dávno pred týmto vláknom. Prípady Majetku preto cez vyhľadávanie nevidel ani
   `super`, účet, cez ktorý čítajú všetky sady.

Z bodu 6.2 („zdieľaná knižnica akceptačných testov") sa medzitým stalo
`tools/pftestlib.py` a **toto bola prvá situácia, kde sa to vrátilo**: oprava
hĺbkového čítania kariet bola jedna funkcia v knižnici plus tri kópie
v samostatných sadách, ktoré si vlastného klienta ponechávajú zámerne.

### 7.5 Kde harness pomohol a kde nie

**Pomohol**, merateľne:

* `pfnew` vygeneroval Onboarding appku so správnymi vzormi (preložiteľný stav,
  názov prípadu bez stavu, `allowedNets`, `pripoj_do_uzla`) — dopisovala sa
  doménová logika, nie appka.
* `pfdoc` udržal čítanie po kapitolách; celý RUNBOOK sa ani raz nenačítal.
* `action-api.md` zabránil písaniu metód, ktoré už existujú (`usersWithRole`,
  `userIdsOf`, `menaUzivatelov`).
* Akceptačné sady prežili štrukturálny refaktor a chytili obe regresie.

**Nepomohol**, a to je zoznam na ďalšiu prácu:

1. **Chýbal krok „čistá databáza".** Reťazec overovania končil pri `pfsync --sync`.
   Doplnené do `cheatsheet.md` a `CLAUDE.md`; stálo to dva startup-breaking bugy.
2. **`pfnew` skelet stále nenesie read-only stavový pohľad (B25).** V Onboardingu
   som ho písal ručne, hoci je to vzor, ktorý potrebuje takmer každá appka so
   schvaľovaním. Bod 6.3 je teda stále otvorený a toto vlákno ho potvrdilo.
3. **CI nespúšťa kvalitatívny reťazec** (bod 6.4). `pflint`, `pfgroovy`,
   `pfi18n`, `pfview` sú sekundy a chytajú presne tú vrstvu, ktorá mlčí.
4. **Frameworkové siete sa na existujúcej inštancii neaktualizujú.**
   `configuration_tiles.xml` žije v `backend-starter/resources` a `pfsync` ho
   nepokrýva, takže zmenu bolo treba naimportovať ručne cez API. Nástroj na to
   neexistuje.
5. **`up.sh` spúšťa `pfsync` skôr, než dobehnú štartovacie runnery.** Healthcheck
   zozelenie pred nimi, takže na čistej databáze zakaždým vypíše
   `prihlasenie super@netgrif.com zlyhalo`. Nie je to chyba nasadenia, ale je to
   presne ten druh šumu, ktorý učí ignorovať výpisy.

### 7.6 Čo z toho platí všeobecne pre tvorbu appiek s AI

Zovšeobecnenie, ktoré si trúfam spraviť z dvoch priebehov:

* **Hodnota harnessu nie je v tom, že agent píše kód rýchlejšie.** Kód je lacný.
  Hodnota je v tom, že agent **nemusí uhádnuť** to, čo sa nedá odvodiť — aritu
  `createOrUpdateMenuItem`, poradie mazania filtra, `keyValue` vs `textValue`.
  Každá takáto vec, ktorá nie je zapísaná, stojí hodiny a zopakuje sa pri každej
  ďalšej appke.
* **Overovanie musí mať úrovne a agent musí vedieť, ktorá chytá čo.** Zelená
  statická kontrola je dôkaz o štruktúre, nie o tom, že to beží. Bez tabuľky
  v 7.1 si agent (aj človek) vyberie najlacnejšiu úroveň a skončí pri nej.
* **Dokumentácia projektu je vstup, nie autorita.** Tri z najdrahších chýb tohto
  vlákna boli veci, ktoré repozitár tvrdil a neboli pravda. Pravidlo „keď si
  nástroj a engine odporujú, chyba je v nástroji" treba rozšíriť: *keď si
  dokument a engine odporujú, chyba je v dokumente — a treba ho opraviť.*
* **Za každú opravu patrí záznam tam, kde ju niekto nabudúce hľadá.** Toto vlákno
  pridalo `ENGINE_ISSUES` E21, `RUNBOOK` 14, položky do cheatsheetu a opravu
  generátora. Bez toho by sa tá istá práca spravila znova.

## 8. Tretí priebeh: čo ukázalo nasadenie na skutočných ľudí

Tretie kolo tým istým harnessom. Vzniklo pri ňom: prepísaný **Onboarding**
(z troch schvaľovacích kôl na jedno), appka **Pracovné cesty** (tri siete plus
menu), **redesign portálu** podľa dizajn systému z Figmy, **obnova hesla**
end-to-end, **verejný formulár** s označením procesov, ktoré ho majú, a
**priečinkové zobrazenie**. V inštancii je 33 identifikátorov sietí, 51 verzií,
81 účtov a 485 prípadov.

Zaujímavé opäť nie sú tie funkcie. Zaujímavé je, že **každá jedna chyba tohto
kola sa prejavila ako niečo iné, než čím bola** — a tri z nich by žiadna
statická kontrola nenašla, lebo nešlo o kód, ale o stav.

### 8.1 Findings

| # | príznak, ktorý videl človek | skutočná príčina | zapísané v |
|---|---|---|---|
| 1 | „obnova hesla sa točí, mail nechodí" | chýbajúci endpoint v `nae.json`; knižnica vyhodí výnimku **pred** odoslaním | FRONTEND B6 |
| 2 | „nemám task môjho vozidla" | proces žiadal doménovú rolu, ktorú nemalo 25 z 27 účtov | PETRIFLOW B28 |
| 3 | „po prihlásení iného vidím cudzie menu" | `UriService` načíta koreň raz za beh aplikácie | FRONTEND B8 |
| 4 | „pridelil som rolu a nefunguje to ani po refreshi" | oprávnenia sa počítajú zo session, `/user/me` už novú rolu hlási | ENGINE E25 |
| 5 | „karta je cez celú šírku okna" | `fxLayoutGap` pridá inline `max-width` a prebije šírku zo štýlu | FRONTEND B7 |
| 6 | nikto to nevidel | appka Pracovné cesty nebola v manifeste vôbec | 8.3 nižšie |

### 8.2 Keď sa nestane nič, chyba je pred requestom

Obnova hesla mala štyri príznaky naraz: v prehliadači **žiadny request**,
v logu backendu **žiadny záznam**, v Mailpite **žiadny mail**, na obrazovke
**večne točiaci spinner**. Tri zo štyroch ukazujú na backend a hľadal som ho
tam: SMTP konfiguráciu, mailové šablóny, stav účtu v Mongu.

Príčina bola jeden chýbajúci riadok v konfigurácii frontendu. `SignUpService`
si adresu skladá v konštruktore a pri chýbajúcom kľúči **vyhodí výnimku
synchrónne**, ešte pred vytvorením Observable. Komponent zapne spinner, zavolá
metódu a vypína ho až v `subscribe`, ktoré nikdy nevznikne.

Diagnostika, ktorá to rozhodne za desať sekúnd a ktorú som mal spraviť ako
prvú:

```bash
curl -s -X POST "http://localhost:8080/api/auth/reset" -H "Content-Type: text/plain" -d 'niekto@example.com'
```

**Keď `curl` mail pošle a appka nie, problém je pred requestom, nie za ním.**
Zovšeobecnene: prázdna množina príznakov na strane servera nie je dôkaz
o serveri, je to dôkaz, že sa k nemu nič nedostalo.

### 8.3 Manifest je jediné miesto, kde je napísané, čo je nasadené, a nič ho neoveruje

Pri hľadaní chýbajúceho vozidla sa ukázalo, že appka **Pracovné cesty**, ktorú
inštancia bežne používa (štyri siete, 13 prípadov, položky v menu), **nebola
v `processes.json` vôbec**. Ani v `import`, ani v `bootstrapCase`, ani
v `uriNodes`. Do enginu sa kedysi dostala ručným importom a odvtedy tam žila.

Na čistej databáze by neexistovala. Nič to nehlásilo, lebo bežiaca inštancia ju
má a všetky kontroly bežia proti nej alebo proti súborom v `processes/`.

Je to ten istý tvar chyby ako v kapitole 7.1, len z opačnej strany: tam bežiaca
inštancia **maskovala** chybu poradia, tu **maskovala** chýbajúci záznam
o nasadení. Spoločné majú to, že stav inštancie je bohatší než to, čo je
zapísané.

Jediné upozornenie, ktoré na to ukazovalo, prišlo z `pflint`:

```
pc_menu.xml:138: WARNING [menu-uri-unknown] createOrUpdateMenuItem:
  URI cesta 'hr/cesty' nie je medzi `uriNodes` v processes.json
```

Nedalo sa z neho prečítať, že chýba celá appka. Hovorilo o jednom uzle.

**Návrh, ktorý z toho plynie:** `pfsync` porovnáva XML súbory s tým, čo drží
engine. Nech porovnáva aj **zoznam identifikátorov v engine so zoznamom
v manifeste** a hlási obe strany rozdielu:

* v engine a nie v manifeste → na čistej databáze appka zanikne,
* v manifeste a nie v engine → `up.sh` ju naimportuje, možno neúmyselne.

Je to niekoľko riadkov v nástroji, ktorý oba zoznamy už má.

### 8.4 Oprávnenia „pre všetkých" sa doménovou rolou nedajú spraviť

Vyúčtovanie pracovnej cesty podáva ktokoľvek. Sieť to mala podmienené rolou
`zamestnanec`, čo znie správne, a znamená to prideliť tú rolu **každému
jednému účtu v inštancii**. Pri prvom kole ľudí to nikto nespraví: 25 z 27
účtov ju nemalo.

Prejav bol taký, že appka „nič nerobí". Položka menu je, obrazovka prázdna,
tlačidlo nezaloží nič a nikde sa nepovie prečo.

Na proces, ktorý je z definície pre všetkých, patrí systémová rola `default`.
Má ju každý prihlásený, nedeklaruje sa a `pflint` ju pozná. S jednou výhradou,
ktorá sa ľahko prehliadne: `default` dostáva **iba `create`**. Keby dostal aj
`view`, videl by každý obsah osobných kariet všetkých kolegov. Vidieť ju má
vlastník, a to je `userRef`, nie rola.

### 8.5 Stav, ktorý prežije refresh

Dve chyby tohto kola mali spoločné, že „skús to znova načítať" na ne nezaberá,
a pritom je to prvá vec, ktorú človek spraví.

`UriService` drží koreň stromu v službe, ktorá prežije odhlásenie, takže po
prihlásení iného účtu svieti v menu strom predošlého človeka. To refresh
vyrieši, lebo zhodí celý stav služieb, a práve preto sa to ťažko hlási:
„mne to po refreshi funguje".

Zmena rolí je horšia. Oprávnenia sa vyhodnocujú proti `stringId` rolí uloženým
v session, kým `/user/me` číta z databázy. Stará session teda **novú rolu
hlási a zároveň na ňu vracia 403**:

```
POST /api/user/{id}/role/assign   (rola agent)
GET  /api/user/me        stará session -> ['agent']    nová session -> ['agent']
POST /api/workflow/case  stará session -> 403          nová session -> 200
```

Používateľ vidí stav, ktorý pre neho neplatí, a odpoveď 403 nemá s čím spojiť.
Refresh nepomôže, lebo stará nie je stránka, ale session.

Pre appku z toho plynie prevádzkové pravidlo, nie oprava: **kto prideľuje role,
musí človeku povedať, že sa má znova prihlásiť.** Pre platformu je to zadanie:
po zmene rolí zneplatniť sessiony toho účtu.

### 8.6 Čo zabránilo zbytočnej práci

Dvakrát v tomto kole bolo najlacnejšie neurobiť nič a najprv zmerať.

**Prvý raz** pri viackrokovom verejnom formulári. Návrh bol rozdeliť sieť na
dve, lebo „vnútri formulára nenastane reload". Namiesto prepisovania siete som
ten istý formulár otvoril na druhej route a fungoval. Chyba nebola v sieti, ale
v tom, na akej obrazovke visela. Rozdelenie siete by bolo prepísalo model
a chybu nechalo tam, kde bola.

**Druhý raz** pri dvoch pokusoch rozbehať ten formulár na pôvodnej route. Ani
jeden nefungoval a obidva som **vrátil**, namiesto aby som ich nechal v kóde
ako „možno to niečomu pomôže". Kód, o ktorom sa nedá povedať, čo rieši, je
drahší než jeho absencia: pri ďalšej chybe sa najprv podozrieva on.

### 8.7 Dizajn systém nie je paleta

Redesign portálu podľa Figma súboru ukázal vec, ktorú som nečakal: **dizajn
systém si v deviatich miestach odporoval sám**. Krok 700 označený ako 600
v piatich farebných rampách, štyri posunuté hodnoty rozostupov.

Nástroj, ktorý tokeny ťahá z exportu, preto nesmie ticho vybrať jednu z dvoch
hodnôt. `figmatokens.py --kontrola` rozpory **vypíše** a rozhodnutie nechá na
človeka. Ticho vybrať znamená preniesť chybu dizajnu do kódu a stratiť
informáciu, že tam bola.

Druhá vec je knižnica: `navigation-theme` používa tóny **50 a 100** na ľavý
rail, takže farebný odtieň v nich zafarbí celé menu. V dizajn systéme sú to
„najsvetlejšie odtiene značky", v appke je to pozadie navigácie, a tieto dve
veci sa nedajú splniť naraz.

### 8.8 Zhrnutie: kde je harness silný a kde stále nie

| | stav |
|---|---|
| písanie sietí | spoľahlivé. 26 sietí, `pflint`/`pfgroovy`/`pfi18n`/`pfview` zelené, chyby sú vzácne a rýchlo viditeľné |
| akceptačné testy | 8 sád. Napísať test appky trvá menej než postaviť appku |
| **súlad repozitára s nasadením** | **najslabšie miesto.** Manifest nikto neoveruje proti enginu a rozdiel sa prejaví až na čistej databáze |
| chyby v knižnici frontendu | nájditeľné, ale draho. Minifikovaný kód, `private` v deklaráciách, stav v službách `providedIn: 'root'` |
| chyby na hranici session a databázy | najdrahšie. Prejavia sa ako „appka klame" a statická kontrola o nich nemá ako vedieť |

Z toho plynie jediná konkrétna úloha do nástrojov: **porovnávať manifest
s enginom** (8.3). Zvyšok sú pravidlá pre prácu, nie kód.
