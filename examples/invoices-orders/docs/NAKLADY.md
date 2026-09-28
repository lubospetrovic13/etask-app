# Náklady: chargeable eventy a prevádzka na AWS

Stav k 28. 9. 2026. Cenník: interný návrh stránky Pricing (Production). Ceny AWS: región
Frankfurt, Linux, bez DPH, z verejného cenníka AWS.

## V skratke

| | malý zákazník (táto appka) | Agel |
| --- | --- | --- |
| objem | 2 000 faktúr a 500 objednávok mesačne | 100 000 faktúr ročne, 150 appiek, \~1 milión prípadov ročne |
| chargeable eventy | \~57 500 mesačne, \~690 000 ročne | \~1,7 milióna mesačne, \~20 miliónov ročne |
| licencia (Production) | prvý milión zadarmo vystačí na \~17 mesiacov, potom \~41 € ročne | \~1 160 € prvý rok, potom \~1 220 € ročne |
| AWS | 164 USD mesačne (1 server) | 1 700 – 2 400 USD mesačne |

Pri takýchto objemoch je licencia zlomok ceny prevádzky. Zákazník, ktorý potrebuje SLA
a zmluvné garancie (Agel pravdepodobne áno), ide na Enterprise, ktorý sa nacenuje
individuálne; čísla vyššie sú cena za eventy.

## Cenník

- **Community:** zadarmo, na vývoj a skúšanie.
- **Production:** token s plnou funkcionalitou (SSO, pluginy, škálovanie). **Prvý milión
  eventov zadarmo**, potom **6 € za 100 000 eventov mesačne**, fakturované ročne. Používatelia
  sa nerátajú, interní ani externí.
- **Enterprise:** SLA až 24/7/365, zmluvné garancie, cena podľa dohody.

**Chargeable event** je len: založenie prípadu (`CreateCaseEvent`), dokončenie úlohy
(`FinishTaskEvent`) a zmena hodnoty poľa (`SetDataEvent`), bez ohľadu na to, či ich urobí
človek alebo systém. Prevzatie úlohy ani otvorenie formulára sa neráta.

## Koľko eventov robí jeden prípad

Namerané na bežiacom engine (NAE 6.3.1, kolekcia `eventLogs`), na 14 faktúrach a 7 objednávkach
od zápisu po uzavretie, vrátane vrátení a schválenia riaditeľom:

| | faktúra | objednávka |
| --- | --- | --- |
| založenie prípadu | 1 | 1 |
| dokončenie úlohy | 6 | 3 |
| zápis dát | 16 | 19 |
| **chargeable spolu** | **23** | **23** |
| prevzatie úlohy (nepočíta sa) | 6 | 3 |

Faktúry a objednávky sú schvaľovacia appka s niekoľkými úrovňami. Jednoduchšia appka
(žiadosť, jedno schválenie) urobí okolo 12 eventov na prípad.

## Malý zákazník: 2 000 faktúr a 500 objednávok mesačne

**Eventy:** 2 000 × 23 + 500 × 23 = **57 500 mesačne**, 690 000 ročne. Pri priamej ceste bez
vrátení \~41 000 mesačne, pri častých vráteniach \~90 000.

**Licencia:** prvý milión zadarmo vystačí na **\~17 mesiacov**. Potom 57 500 / 100 000 × 6 € =
3,45 € mesačne, teda **\~41 € ročne**.

**AWS: jeden server, 164 USD mesačne On-Demand** (so Savings Plan na 1 rok \~112 USD). Celý
stack beží v Docker Compose tak ako dnes.
[Odhad v AWS Pricing Calculator](https://calculator.aws/#/estimate?id=6098f5f53f5a9b1ef28a0dd843ff7938f81a2e38).

| položka | konfigurácia | USD mesačne |
| --- | --- | --- |
| EC2 | t3.xlarge (4 vCPU, 16 GB), On-Demand | 140,16 |
| EBS | gp3, 150 GB (prílohy \~15 GB ročne) | 14,28 |
| snapshoty | denne | 9,72 |
| **spolu** |  | **164,16** |

Stačí to s rezervou: backend, Elasticsearch a Mongo dnes spolu zaberú \~3,3 GB RAM a OCR skenu
vyťaží jedno jadro na pár sekúnd.

## Agel: 100 000 faktúr ročne, 150 appiek, \~1 milión prípadov ročne

### Eventy

Faktúry počítame nameranými 23 eventmi, ostatných \~900 000 prípadov v 149 appkách 20 eventmi
(medzi jednoduchou žiadosťou a schvaľovaním faktúr):

| scenár | eventov na faktúru / na iný prípad | ročne | mesačne |
| --- | --- | --- | --- |
| nízky: väčšina appiek jednoduchá | 16 / 12 | 12,4 M | 1,0 M |
| **stredný** | **23 / 20** | **20,3 M** | **1,7 M** |
| vysoký: veľa vrátení a úprav | 37 / 33 | 33,4 M | 2,8 M |

Výpočet strednej hodnoty: 100 000 × 23 + 900 000 × 20 = 20,3 milióna ročne.

### Licencia (Production)

| scenár | mesačne | prvý rok (bez prvého milióna) | ďalšie roky |
| --- | --- | --- | --- |
| nízky | \~62 € | \~680 € | \~740 € |
| **stredný** | **\~100 €** | **\~1 160 €** | **\~1 220 €** |
| vysoký | \~170 € | \~1 940 € | \~2 000 € |

Výpočet: 20,3 M / 100 000 × 6 € = 1 218 € ročne; prvý rok bez prvého milióna 19,3 M → 1 158 €.

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

Ceny inštancií za hodinu: c6i.4xlarge 0,776 USD, m6i.2xlarge 0,46 USD, m6i.xlarge 0,23 USD,
r6i.large 0,152 USD; gp3 0,0952 USD za GB. Savings Plan je prepočítaný pomerom z kalkulačky pre
t3.xlarge (\~63 % On-Demand ceny), presnú cenu treba overiť v kalkulačke.

**Prečo B stačí.** 20 miliónov eventov ročne je \~80 000 za pracovný deň, v priemere 2–3 za
sekundu, v rannej špičke desiatky. To backend zvládne na pár jadrách. B rastie hlavne v RAM:
Elasticsearch drží index všetkých prípadov (\~5 miliónov za 5 rokov) a Mongo replika potrebuje
cache. Tri uzly Mongo a Elasticsearch a dva backendy znamenajú, že výpadok jedného servera appku
nezastaví.

**B je odhad, nie meranie.** Kým sa nevyskúša záťažový test s 150 appkami, patrí do ponuky A ako
strop a B ako cieľ.

## Čo spresniť

- **Eventy ostatných appiek Agel.** Počítané 20 na prípad. Dá sa to zmerať rovnako ako pri
  faktúrach: appku prejsť akceptačným testom a spočítať `CreateCaseEvent`, `FinishTaskEvent`
  a `SetDataEvent` v `eventLogs`.
- **Zápisy dát tvoria väčšinu.** Pri faktúre je to 16 z 23. Appka, ktorá ukladá pole pri každom
  písaní (`saveWhileTyping`), ich vyrobí viac; oplatí sa to pri návrhu formulárov sledovať.
- **Skeny a prílohy.** OCR beží na backende. Ak by väčšina zo 100 000 faktúr boli skeny v dávkach,
  treba viac CPU alebo samostatný OCR server. Prílohy nad \~0,5 MB zväčšujú disk, pri veľkých
  objemoch patria do S3.
- **Integrácie** (IMAP, sieťový priečinok, účtovný systém) zatiaľ nie sú postavené. Automatické
  založenie prípadu pridá eventy za kroky, ktoré dnes robí človek.
