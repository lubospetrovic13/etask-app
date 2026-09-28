# Náklady: chargeable eventy a prevádzka na AWS

Stav k 28. 9. 2026. Ceny AWS: región Frankfurt, Linux, bez DPH, z verejného cenníka AWS.

## V skratke

| | malý zákazník (táto appka) | Agel |
| --- | --- | --- |
| objem | 2 000 faktúr a 500 objednávok mesačne | 100 000 faktúr ročne, 150 appiek, \~1 milión prípadov ročne |
| chargeable eventy | \~70 000 mesačne, \~830 000 ročne | \~2,1 milióna mesačne, \~25 miliónov ročne |
| licencia, nový cenník (6 € / 100 000) | \~50 € ročne, s free allowance 0 € | \~1 500 € ročne, s free allowance 1 M/mes. \~800 € |
| licencia, dnešný cenník (26 € / 10 000) | \~2 150 € ročne | \~66 000 € ročne |
| AWS | 164 USD mesačne (1 server) | 1 700 – 2 400 USD mesačne |

Najväčšia neistota nie je objem, ale **čo presne EE ráta ako chargeable event** a **aká veľká bude free allowance**. Obe treba rozhodnúť, než sa čísla ukážu zákazníkovi.

## Koľko eventov robí jeden prípad

Namerané na bežiacom engine (NAE 6.3.1, kolekcia `eventLogs`), na 14 faktúrach a 7 objednávkach od zápisu po uzavretie, vrátane vrátení a schválenia riaditeľom:

| | faktúra | objednávka |
| --- | --- | --- |
| založenie prípadu | 1 | 1 |
| prevzatie úlohy | 6 | 3 |
| dokončenie úlohy | 6 | 3 |
| uloženie dát | 16 | 19 |
| **spolu** | **28** | **26** |

**Predpoklad, čo je event:** založenie prípadu, prevzatie a dokončenie úlohy, uloženie dát. Otvorenie formulára (čítanie) tu nie je. Ak ho EE ráta, pripočítaj \~35 %: \~10 čítaní na faktúru, \~6 na objednávku.

Faktúry a objednávky sú schvaľovacia appka s niekoľkými úrovňami. Jednoduchšia appka (žiadosť, jedno schválenie) urobí menej, zhruba 15 eventov na prípad.

## Malý zákazník: 2 000 faktúr a 500 objednávok mesačne

**Eventy:** 2 000 × 28 + 500 × 26 = **69 000 mesačne**, 828 000 ročne. Pri častých vráteniach až 110 000 mesačne, pri priamej ceste 50 000.

**Licencia:** pri novom cenníku 828 000 / 100 000 × 6 € = **\~50 € ročne**. Ak bude free allowance aspoň 1 milión mesačne, neplatí nič. Pri dnešnom cenníku (26 € za 10 000 nad balík) je to \~180 € mesačne, \~2 150 € ročne.

**AWS: jeden server, 164 USD mesačne On-Demand** (so Savings Plan na 1 rok \~112 USD). Celý stack beží v Docker Compose tak ako dnes. [Odhad v AWS Pricing Calculator](https://calculator.aws/#/estimate?id=6098f5f53f5a9b1ef28a0dd843ff7938f81a2e38).

| položka | konfigurácia | USD mesačne |
| --- | --- | --- |
| EC2 | t3.xlarge (4 vCPU, 16 GB), On-Demand | 140,16 |
| EBS | gp3, 150 GB (prílohy \~15 GB ročne) | 14,28 |
| snapshoty | denne | 9,72 |
| **spolu** |  | **164,16** |

Stačí to s rezervou: backend, Elasticsearch a Mongo dnes spolu zaberú \~3,3 GB RAM a OCR skenu vyťaží jedno jadro na pár sekúnd.

## Agel: 100 000 faktúr ročne, 150 appiek, \~1 milión prípadov ročne

### Eventy

Faktúry počítame nameranými 28 eventmi, ostatných \~900 000 prípadov v 149 appkách 25 eventmi (stred medzi jednoduchou žiadosťou a schvaľovaním faktúr):

| scenár | eventov na faktúru / na iný prípad | ročne | mesačne |
| --- | --- | --- | --- |
| nízky: väčšina appiek jednoduchá | 20 / 15 | 15,5 M | 1,3 M |
| **stredný** | **28 / 25** | **25,3 M** | **2,1 M** |
| vysoký: veľa vrátení a úprav | 45 / 40 | 40,5 M | 3,4 M |

Výpočet strednej hodnoty: 100 000 × 28 + 900 000 × 25 = 25,3 milióna ročne. Ak sa rátajú aj čítania formulárov, \~34 miliónov.

### Licencia

| scenár | nový cenník, bez allowance | nový cenník, allowance 1 M mesačne | dnešný cenník |
| --- | --- | --- | --- |
| nízky | 930 € ročne | 210 € ročne | \~40 000 € ročne |
| **stredný** | **1 520 € ročne** | **800 € ročne** | **\~66 000 € ročne** |
| vysoký | 2 430 € ročne | 1 710 € ročne | \~105 000 € ročne |

Nový cenník: 6 € za každých 100 000 eventov mesačne nad free allowance. Pri allowance 100 miliónov (druhá hodnota zo zadania) Agel neplatí za eventy nič. Dnešný cenník: 26 € za 10 000 eventov mesačne nad balík, bez odpočtu balíka.

### Infraštruktúra

Agel má dnes on-premise \~60 CPU a \~120 GB RAM. Na AWS sú dve cesty:

| | A: rovnaký výkon ako dnes | B: odhad podľa záťaže, s vysokou dostupnosťou |
| --- | --- | --- |
| servery | 4 × c6i.4xlarge (16 vCPU, 32 GB) | backend 2 × m6i.2xlarge (8 vCPU, 32 GB), Mongo 3 × r6i.large (2 vCPU, 16 GB), Elasticsearch 3 × m6i.xlarge (4 vCPU, 16 GB) |
| spolu | 64 vCPU, 128 GB | 34 vCPU, 160 GB |
| EC2 On-Demand | 2 266 USD | 1 508 USD |
| disky gp3 a snapshoty | \~145 USD (1 000 GB) | \~175 USD (1 300 GB) |
| load balancer | – | \~25 USD |
| **spolu mesačne On-Demand** | **\~2 410 USD** | **\~1 710 USD** |
| so Savings Plan na 1 rok | \~1 570 USD | \~1 150 USD |
| ročne On-Demand | \~28 900 USD | \~20 500 USD |

Ceny inštancií za hodinu: c6i.4xlarge 0,776 USD, m6i.2xlarge 0,46 USD, m6i.xlarge 0,23 USD, r6i.large 0,152 USD; gp3 0,0952 USD za GB. Savings Plan je prepočítaný pomerom z kalkulačky pre t3.xlarge (\~63 % On-Demand ceny), presnú cenu treba overiť v kalkulačke.

**Prečo B stačí.** 25 miliónov eventov ročne je \~100 000 za pracovný deň, v priemere 3–4 za sekundu, v rannej špičke desiatky. To backend zvládne na pár jadrách. B rastie hlavne v RAM: Elasticsearch drží index všetkých prípadov (\~5 miliónov za 5 rokov) a Mongo replika potrebuje cache. Tri uzly Mongo a Elasticsearch a dva backendy znamenajú, že výpadok jedného servera appku nezastaví.

**B je odhad, nie meranie.** Kým sa nevyskúša záťažový test s 150 appkami, patrí do ponuky A ako strop a B ako cieľ.

## Čo treba rozhodnúť a spresniť

- **Definícia chargeable eventu v EE.** Ak sa ráta čítanie formulára, čísla stúpnu o \~35 %. Ak len založenie prípadu a dokončenie úlohy, klesnú zhruba na štvrtinu (faktúra 7 eventov namiesto 28).
- **Veľkosť free allowance.** V zadaní zaznel 1 milión aj 100 miliónov. Pri Agel je to rozdiel medzi \~800 € a 0 € ročne.
- **Eventy ostatných appiek Agel.** Počítané 25 na prípad. Dá sa to zmerať rovnako ako pri faktúrach: appku prejsť akceptačným testom a spočítať `eventLogs`.
- **Skeny a prílohy.** OCR beží na backende. Ak by väčšina zo 100 000 faktúr boli skeny v dávkach, treba viac CPU alebo samostatný OCR server. Prílohy nad \~0,5 MB zväčšujú disk, pri veľkých objemoch patria do S3.
- **Integrácie** (IMAP, sieťový priečinok, účtovný systém) zatiaľ nie sú postavené. Automatické založenie prípadu pridá eventy za kroky, ktoré dnes robí človek.
