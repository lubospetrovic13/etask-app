# eTask — pravidlá pre AI agenta

Petriflow-first aplikačný stack. **Aplikačná logika patrí do Petriflow sietí, nie
do Javy a nie do Angularu.** Framework je ~5 500 riadkov, siete ~7 500 — ten
pomer je zámer.

Tento súbor je v kontexte **vždy**, preto je krátky: sú v ňom len rozhodnutia
a pravidlá. Vysvetlenia sú v dokumentácii a berú sa **po kapitolách**, nie po
súboroch — celá dokumentácia má ~86 000 tokenov, jedna kapitola ~500:

```bash
cd etask-configuration
python3 tools/pfdoc.py                  # čo kde je, s cenou v tokenoch
python3 tools/pfdoc.py hladaj "menu"    # kde o tom je (nadpisy, nie telo)
python3 tools/pfdoc.py runbook 4        # len tá kapitola
```

## Než začneš čokoľvek meniť

**Prečítaj `docs/reference/cheatsheet.md`** (~2 000 tokenov):
postup, osem rozhodnutí, ktoré určujú, či to bude fungovať, a zoznam toho, čo
mlčí. Pri sieťach, akciách, oprávneniach a formulároch **načítaj skill
`petriflow`** (`.claude/skills/petriflow/SKILL.md`).

Recepty na bežné úlohy sú v RUNBOOKu — neimprovizuj, keď tam je overený postup.
Skoro každá z nich má pascu, ktorá sa **neprejaví ako chyba**: chýbajúci JWT
kľúč vracia 401 bez správy, re-import siete ticho odoberie roly, `nc-task-list`
nezobrazí vlastné polia a build o tom mlčí.

| úloha | `pfdoc.py runbook N` |
|---|---|
| rozbehať appku | 1 |
| nová sieť / aplikácia, appka do vlastného repa | 2 |
| logika v Jave volaná z Petriflow | 3 |
| karta a priečinok v bočnom menu | 4 |
| úprava vizuálu, téma | 5 |
| nový field komponent, ukladanie poľa počas písania | 6 |
| noví používatelia a roly | 7 |
| anonymný / verejný prístup | 8 |
| dvojjazyčná appka (SK + EN) | 9 |
| čítanie faktúry z prílohy (e-faktúra, PDF, OCR) | 10 |
| priečinky v karte, názvy tlačidiel, schvaľovanie podľa strediska | 11 |
| celý stack v Dockeri (OCR, SMTP, notifikácie) | 12 |
| automatická oprava (`pffix`, `pfloop`) a MCP server | 13 |
| otvorenie procesu v builderi (podpísaný odkaz na model) | 14 |

## Šablóna, nie nasadenie

Repozitár drží framework, infraštruktúru, správu používateľov a **jednu**
príkladovú appku (Service Desk) — jej kartu vidí len admin, aby sa príklad
nedal zameniť za skutočnú appku. Klientske appky žijú vo vlastných repách
a do checkoutu sa dostanú `pfapp install`:

| appka | repozitár |
|---|---|
| Dovolenky | `../etask-app-dovolenky` |
| Objednávky a faktúry | `../etask-app-objednavky-faktury` |
| Majetok | `../etask-app-majetok` |

`pfapp list` povie, čo je nainštalované, `pfapp status` či sa nasadená kópia
nerozišla so zdrojom. Inštalácia mení `processes.json` a `seed.json` — to je
**stav nasadenia**, nie šablóny, a do commitu šablóny nepatrí. Príručka appky
(`docs/PRIRUCKA.md`) prichádza s appkou.

## Tri vrstvy

```
1. Petriflow XML          ← default. Stav, prechody, dáta, oprávnenia case-u.
2. Custom action delegate ← I/O, cudzie API, výpočet nevyjadriteľný v akcii.
3. Framework/runtime kód  ← len render, HTTP layer, a čo engine neposkytuje.
```

**Nikdy nezačínaj na vrstve 3.** Prechod nižšie musí byť odôvodnený vetou, ktorá
povie, **ktoré primitívum na vyššej vrstve chýba**. Ak ju nedokážeš napísať,
problém patrí vyššie.

Vrstva 2 nie je záchranná brzda — je to miesto, kde rastie jazyk. Metóda
v `EtaskActionDelegate` je nové Petriflow primitívum, volateľné menom z každej
siete. Keď ten istý Groovy píšeš v druhej sieti, presuň ho tam.

**Pred písaním novej metódy** otvor `docs/reference/action-api.md` — generovaný
inventár metód enginu aj projektu. Delegát je dynamický, takže preklep prejde
parserom aj importom a spadne až za behu; ten zoznam je jediná obrana.

## Nová aplikácia

```bash
cd etask-configuration
python3 tools/pfnew.py mojaapp ziadost "Žiadosť o niečo" --role pracovnik
```

Vygeneruje sieť, menu sieť so zobrazeniami a stĺpcami, doplní manifest a napíše
akceptačný test. Skelet nesie vzory, ktoré sa inak vymýšľajú znova a zle — stav
ako `enumeration_map` (`text` sa neprekladá), názov prípadu **bez** stavu
(`Case.title` je `String`), deväť argumentov `createOrUpdateMenuItem`,
`allowedNets` kvôli stĺpcom, `pripoj_do_uzla` v idempotentnej vetve menu, read
arc zo sinku. Dopisuje sa doménová logika, nie appka. Podrobne RUNBOOK 2.

**Pridanie appky Javu nevyžaduje** — `pom.xml` kopíruje `processes/*.xml`
hromadne a `NetRunner` si identifikátor prečíta z `<id>` v XML. Keď sa pri
*pridávaní appky* chystáš editovať Javu, robíš pravdepodobne niečo iné, než si
myslíš.

To **nie je zákaz siahať do Javy.** Appka pre klienta často potrebuje schopnosť,
ktorú platforma nemá — čítanie príloh, odoslanie mailu, cudzie API, nová
závislosť. Vtedy sa platforma rozšíri: nové primitívum v delegáte (vrstva 2),
prípadne servis a závislosť v `pom.xml` (vrstva 3). Podmienka je jediná a je to
tá istá ako pri vrstvách: **vetu, ktoré primitívum na vyššej vrstve chýba, musíš
vedieť napísať**. Tento repozitár tak vznikol `precitajFakturu`, `notifikuj`
aj tesseract v obraze.

Manifest má štyri sekcie v dvoch súboroch (`import`, `bootstrapCase`,
`uriNodes`, `netScope`) a **každá vie chýbať tak, že to nič nepovie**. Preto sa
needituje ručne: `pfnew` pri novej appke, `pfapp` pri appke z iného repa.

## Overovanie

Po zmene siete, v tomto poradí:

```bash
cd etask-configuration
python3 tools/pflint.py processes/        # 0,3 s
python3 tools/pfgroovy.py processes/      # 3 s
python3 tools/pfi18n.py processes/        # každý viditeľný text má preklad
python3 tools/pfview.py                   # frontend vykreslí, čo sieť pýta
python3 tools/pfsync.py --sync            # import + role, len čo sa rozišlo
```

`python3 tools/pfloop.py --fix` spustí ten istý reťazec naraz, aplikuje opravy,
ktoré majú jednoznačné riešenie, a čo zostane, napíše ako zadanie do
`.run/pfloop-zadanie.md` (RUNBOOK 13).

**Keď si siahol na poradie štartu, uzly URI, manifest alebo runnery, pridaj
ešte jeden krok — čistú databázu:**

```bash
tools/up.sh --docker --fresh --build     # ZMAZE data, pýtaj sa pred tým
```

**Bežiaca inštancia nesie stav z minulých behov a presne ten maskuje chyby
poradia.** Uzly a prípady, ktoré tam už sú, prekryjú to, že ich prvý beh vôbec
nevyrobí. Takto vznikli dve chyby, ktoré prežili zelený `pflint`, `pfgroovy`,
`pfview` aj `pfsync`: backend na čistej databáze nenaštartoval, a admin-only
katalóg videl každý prihlásený. Rozbor je v `pfdoc analyza 7`.

**Ground truth je bežiaci engine.** Import pri chybe vracia holé
`{"status":500}` bez dôvodu — príčina je len v logu servera. Bez importu sieť
nie je overená.

`NetRunner` importuje sieť len keď v databáze **chýba**: po zmene existujúceho
XML sa pri štarte nestane nič, engine ďalej drží starý model a nové casy z neho
vznikajú. Nikde sa to neohlási. To rieši `pfsync --sync`.

Dve veci, ktoré z toho vyplývajú a stoja každého aspoň jedno ladenie:

* **Case si drží verziu siete, v ktorej vznikol.** Kto po zmene testuje na
  starom case, testuje starý model.
* **Po pridelení rolí sa treba odhlásiť a prihlásiť.** Prihlásená session drží
  staré `stringId` rolí → zakladanie casu vráti **403**.

Keď si offline nástroj a engine odporujú, **chyba je v nástroji**. Oprav nástroj
a spusti `tools/pftest.sh`.

## Čo nerobiť

* Nepridávať Angular komponent na to, čo sa dá vyjadriť v sieti.
* Nepísať Java servis skôr, než je overené, že delegát to nevie.
* Nedôverovať schéme z hlavičky siete — runtime sa od nej odlišuje.
* Nekontrolovať poradie podelementov `<data>` v nástrojoch (tri zdroje pravdy si
  odporujú, siete porušujú schému a importujú sa).
* **Nespúšťať `pfcheck` ani `pfsync --sync` na produkciu** — importujú novú
  verziu siete.
* Nezavesiť read-only pohľad na read arc z miesta, ktoré nejaký prechod
  konzumuje. Odmietnuté `finish` tú úlohu zmaže a už ju neobnoví
  (`pfdoc.py learnings B8b`; kam ho vešať je B25).
* Nečítať `docs/petriflow_reference.md` celý (27 000 tokenov) — `pfdoc hladaj`.

## Čerstvý checkout

```bash
etask-configuration/tools/up.sh           # kompletný stack, idempotentne
etask-configuration/tools/up.sh --docker  # to isté celé v Dockeri (RUNBOOK 12)
```

`up.sh` volá `bootstrap.sh` sám. Ten vygeneruje JWT podpisový kľúč — je
gitignored, takže po `git clone` chýba, a bez neho engine nepodpíše anonymnú
session a **verejné formuláre vracajú 401** bez správy, ktorá by to s kľúčom
spojila.

`EtaskRunner` pri každom štarte vypíše bezpečnostnú kontrolu (default heslo
admina, testovacie účty, chýbajúci kľúč). Keď to v logu vidíš, nie je to šum.

## Prostredie

* Java **11** (nie 17, nie 21 — Groovy 3 na JDK 21 padne).
* `LANG=C.UTF-8` je povinné, inak import procesu s diakritikou v názve zhodí
  `InvalidPathException`.
* `certificates/private.der` je gitignored (viď Čerstvý checkout).
