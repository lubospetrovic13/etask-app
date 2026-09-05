# eTask

Petriflow-first aplikačný stack nad Netgrif Application Engine 6.3.1.
**Aplikačná logika je v Petriflow sieťach, nie v Jave a nie v Angulari** — framework
je ~5 500 riadkov, siete ~7 500 a ten pomer je zámer.

```bash
etask-configuration/tools/up.sh
```

Jeden príkaz: JWT kľúč, Java 11, Docker, Mongo + Elasticsearch + Redis, build,
backend. Idempotentný — čo beží, nechá bežať. Potom
http://localhost:8080, prihlásenie `super@netgrif.com` / `password`.

## Kam ísť ďalej

| chcem… | kde |
|---|---|
| rozbehať, pridať appku, menu, používateľov, anonymný prístup, tému, komponent | **[`docs/RUNBOOK.md`](etask-configuration/docs/RUNBOOK.md)** |
| písať Petriflow siete | [`.claude/skills/petriflow/SKILL.md`](.claude/skills/petriflow/SKILL.md) |
| zoznam volateľných metód v akciách | [`reference/action-api.md`](etask-configuration/reference/action-api.md) |
| prečo je repozitár takto postavený | [`docs/AI_STARTER_ANALYSIS.md`](etask-configuration/docs/AI_STARTER_ANALYSIS.md) |
| pravidlá pre AI agenta | [`CLAUDE.md`](CLAUDE.md) |

## Nová aplikácia

```bash
cd etask-configuration
cp examples/skeleton.xml processes/mojaapp.xml   # prepíš <id>, <initials>, <title>
# dopíš "mojaapp.xml" do processes.json → "import"
python3 tools/pflint.py processes/mojaapp.xml
```

Do Javy ani do `pom.xml` sa nesiaha. Ak sa pri pridávaní appky chystáš editovať
framework, je to signál, že robíš niečo iné, než si myslíš.

## Štruktúra

```
etask-configuration/    siete, dokumentácia, nástroje
  processes/            aplikačná logika (.xml)
  processes.json        čo sa importuje, menu karty, bootstrap casy
  examples/skeleton.xml najmenšia funkčná sieť
  tools/                up.sh, pflint, pfgroovy, pfcheck, pfseed, pfapi, pftest
etask-backend-starter/  Java/Groovy — engine, EtaskActionDelegate, runnery
etask-frontend-starter/ Angular 13 — téma a vlastné field komponenty
deploy/                 docker-compose a pipeline na VPS
```

**Service Desk (`processes/sd_*.xml`) je príkladová aplikácia, nie časť
frameworku** — runtime ju nepozná po mene. Odstráni sa zmazaním tých sietí a ich
riadkov v `processes.json`.

## Overovanie

```bash
cd etask-configuration
python3 tools/pflint.py processes/                    # štruktúra, tiché pasce
python3 tools/pfgroovy.py processes/                  # syntax Groovy
tools/pfcheck.sh --log ../.run/backend.log processes/ # ground truth: import do enginu
tools/pftest.sh                                       # regresia nástrojov
```

Ground truth je bežiaci engine — import endpoint pri chybe vracia holé
`{"status":500}` bez dôvodu a príčina je len v logu servera. `pfcheck` a `pfseed`
zapisujú do inštancie, takže **nie proti produkcii**.

## Prostredie

Java **11** (Groovy 3 na JDK 17+ padá), `LANG=C.UTF-8` (inak import siete
s diakritikou zhodí `InvalidPathException`), `certificates/private.der` je
gitignored a bez neho verejné formuláre vracajú 401. `up.sh` sa o všetky tri
postará.
