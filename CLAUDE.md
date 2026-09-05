# eTask — pravidlá pre AI agenta

Petriflow-first aplikačný stack. **Aplikačná logika patrí do Petriflow sietí, nie
do Javy a nie do Angularu.** Framework je ~5 500 riadkov, siete ~7 500 — ten
pomer je zámer.

## Než začneš čokoľvek meniť

Ak sa úloha týka Petriflow sietí, procesov, akcií, oprávnení alebo formulárov,
**načítaj skill `petriflow`**. Je v `.claude/skills/petriflow/SKILL.md` a obsahuje
rozhodovací postup, tiché pasce a odkaz na inventár extension pointov.

**Pre bežné úlohy je hotový recept v `etask-configuration/docs/RUNBOOK.md`** —
neimprovizuj, keď tam je overený postup. Pokrýva to, čo sa na tomto repozitári
reálne žiada:

| úloha | recept |
|---|---|
| rozbehať appku | `etask-configuration/tools/up.sh` (RUNBOOK 1) |
| nová sieť / aplikácia | RUNBOOK 2 |
| logika v Jave volaná z Petriflow | RUNBOOK 3 |
| karta a priečinok v bočnom menu | RUNBOOK 4 |
| úprava vizuálu, téma | RUNBOOK 5 |
| nový field komponent | RUNBOOK 6 |
| noví používatelia a roly | RUNBOOK 7 |
| anonymný / verejný prístup | RUNBOOK 8 |

Skoro každá z nich má pascu, ktorá sa neprejaví ako chyba — chýbajúci JWT kľúč
vracia 401 bez správy, re-import siete ticho odoberie roly, `nc-task-list`
nezobrazí vlastné polia a build o tom mlčí. Tie pasce sú v RUNBOOKu pri
príslušnom kroku.

## Tri vrstvy

```
1. Petriflow XML          ← default. Stav, prechody, dáta, oprávnenia case-u.
2. Custom action delegate ← I/O, cudzie API, výpočet nevyjadriteľný v akcii.
3. Framework/runtime kód  ← len render, HTTP layer, a čo engine neposkytuje.
```

**Nikdy nezačínaj na vrstve 3.** Prechod nižšie musí byť odôvodnený vetou, ktorá
povie, ktoré primitívum na vyššej vrstve chýba. Ak ju nedokážeš napísať, problém
patrí vyššie.

Vrstva 2 nie je záchranná brzda — **je to miesto, kde rastie jazyk**. Metóda
pridaná do `EtaskActionDelegate` je nové Petriflow primitívum, volateľné menom
z každej siete. Keď ten istý Groovy píšeš v druhej sieti, presuň ho tam.

## Pred písaním novej metódy

Otvor `etask-configuration/reference/action-api.md` — generovaný inventár 169
metód enginu plus vlastných metód projektu, volateľných z akcie menom.

Existujúcu metódu nepíš znova. Delegát je dynamický, takže preklep prejde
parserom aj importom a spadne až za behu; tento zoznam je jediná obrana. Vznikol
preto, že bez neho bola postavená horšia verzia už existujúceho extension pointu
— podrobne v `etask-configuration/docs/AI_STARTER_ANALYSIS.md`, časť 0.

## Nová aplikácia

```bash
cd etask-configuration
cp examples/skeleton.xml processes/mojaapp.xml    # prepíš <id>, <initials>, <title>
# dopíš "mojaapp.xml" do processes.json → "import"
```

Toto je celý postup. **Žiadny zásah do Javy ani do `pom.xml`** — inak by stack
protirečil vlastnému pravidlu, že aplikačná logika patrí do Petriflow. `NetRunner`
číta `processes.json` a identifikátor si berie z `<id>` v XML.

Manifest nesie aj `bootstrapCase` (siete, ktorých má pri štarte existovať jeden
case — typicky tá, čo stavia zobrazenia menu) a `uriNodes` (ikona a viditeľnosť
karty v bočnom menu). Service Desk je príkladová aplikácia postavená len na
týchto troch sekciách; runtime ho nepozná po mene a odstráni sa zmazaním sietí
a ich riadkov v manifeste.

## Overovanie

Po zmene siete, v tomto poradí:

```bash
cd etask-configuration
python3 tools/pflint.py processes/                 # 0,3 s
python3 tools/pfgroovy.py processes/              # 3 s
tools/pfcheck.sh --log <backend.log> processes/   # ground truth
python3 tools/pfseed.py                           # role po re-importe
```

**Ground truth je bežiaci engine.** Import endpoint pri chybe vracia holé
`{"status":500}` bez dôvodu — príčina je len v logu servera. Bez `pfcheck` sieť
nie je overená.

Keď si offline nástroj a engine odporujú, **chyba je v nástroji**. Oprav nástroj
a spusti `tools/pftest.sh`.

## Čo nerobiť

* Nepridávať Angular komponent na to, čo sa dá vyjadriť v sieti.
* Nepísať Java servis skôr, než je overené, že delegát to nevie.
* Nedôverovať schéme z hlavičky siete — runtime sa od nej odlišuje.
* Nekontrolovať poradie podelementov `<data>` v nástrojoch (tri zdroje pravdy si
  odporujú, siete porušujú schému a importujú sa).
* Nespúšťať `pfcheck` na produkciu — importuje novú verziu siete.

## Čerstvý checkout

```bash
etask-configuration/tools/up.sh          # kompletný stack, idempotentne
```

`up.sh` volá `bootstrap.sh` sám. Keď treba len kľúč a nič viac:

```bash
etask-configuration/tools/bootstrap.sh
```

Vygeneruje JWT podpisový kľúč (je gitignored, takže po `git clone` chýba) a vypíše
zvyšok postupu. Bez kľúča engine nepodpíše anonymnú session a **verejné formuláre
vracajú 401** bez chybovej správy, ktorá by to s kľúčom spojila.

`EtaskRunner` pri každom starte skontroluje bezpečnostnú pozíciu — default heslo
admina, vytvorené testovacie účty, chýbajúci kľúč — a nájdené veci vypíše ako
WARN. Keď to v logu vidíš, nie je to šum.

## Prostredie

* Java **11** (nie 17, nie 21 — Groovy 3 na JDK 21 padne).
* `LANG=C.UTF-8` je povinné, inak import procesu s diakritikou v názve zhodí
  `InvalidPathException`.
* `certificates/private.der` je gitignored. Bez neho engine nepodpíše anonymnú
  session a **verejné formuláre vrátia 401** — po čerstvom checkoute ho treba
  vygenerovať (postup v `etask-configuration/docs/SERVICE_DESK.md`).
