# Objednávky a faktúry – chargeable eventy a náklady na AWS

28. 9. 2026 · živá verzia na úpravy a komentáre: https://claude.ai/code/artifact/9927b63f-0c86-431d-bb40-b28bb36aa087

## Zhrnutie

Pri 2 000 faktúrach a 500 objednávkach mesačne appka vyrobí **okolo 70 000 chargeable eventov za mesiac** (rozpätie 50 000 – 110 000), teda **\~830 000 za rok**. Ak sa rátajú aj čítania formulárov, je to \~92 000 mesačne a \~1,1 milióna ročne.

- **Voucher 500 000 eventov** tomuto zákazníkovi vystačí na **\~7 mesiacov**, s čítaniami na \~5,5 mesiaca.
- **AWS:** jeden server s rezervou pre 50 používateľov a OCR vyjde na **164 USD mesačne** On-Demand (1 970 USD ročne), so Savings Plan na 1 rok na \~112 USD. Presné položky a link sú v sekcii AWS kalkulačka.
- Počty eventov sú **namerané** z logu bežiaceho enginu, nie odhadnuté z modelu. Odhad je len objem a to, čo presne EE ráta ako chargeable event.

## Vstupy a predpoklady

Počíta sa s appkou Objednávky a faktúry tak, ako je dnes nasadená (vetva `feature/referent-doklad` v tomto repozitári).

| vstup | hodnota |
| --- | --- |
| používatelia | 50 (zadávatelia, referenti, schvaľovatelia stredísk, riaditeľ, účtovníci) |
| faktúry | 2 000 mesačne, \~100 za pracovný deň |
| objednávky | 500 mesačne, \~25 za pracovný deň |
| prílohy | každá faktúra má prílohu (XML, PDF alebo sken), \~0,5 MB |

**Cesta faktúry:** zápis s prílohou (čítanie pri nahratí, OCR pri skene) → kontrola referentom a párovanie s objednávkou → schválenie strediskom → riaditeľ nad limit 1 000 € → zaúčtovanie a export XML. Faktúra krytá schválenou objednávkou ide rovno na zaúčtovanie. Vrátenie je možné na ktorúkoľvek predošlú úroveň.

**Cesta objednávky:** žiadosť s položkami → schválenie strediskom → riaditeľ nad limit → potvrdenie objednania číslom.

**Čo je chargeable event (predpoklad):** každá udalosť procesu, ktorú engine zapíše do histórie: založenie case, prevzatie úlohy, dokončenie úlohy, uloženie dát. Čítanie formulára (GetData) je uvedené zvlášť, lebo nie je jasné, či ho EE ráta.

## Namerané eventy na jeden case

Jedna faktúra od zápisu po zaúčtovanie vyrobí priemerne **28 eventov**, objednávka **26**. Čítania formulárov sú zvlášť: v portáli ich je rádovo 10 na faktúru a 6 na objednávku.

Zdroj: kolekcia `eventLogs` v Mongo bežiaceho enginu (NAE 6.3.1). Merané na 14 dokončených faktúrach a 7 dokončených objednávkach z akceptačných testov, ktoré prechádzajú celou cestou vrátane vrátení a schválenia riaditeľom. Počíta sa len fáza POST, engine každú udalosť zapisuje aj vo fáze PRE.

| udalosť | faktúra (priemer, min–max) | objednávka (priemer) |
| --- | --- | --- |
| založenie case | 1 | 1 |
| prevzatie úlohy | 5,9 (3–9) | 3 |
| dokončenie úlohy | 5,9 (3–9) | 3 |
| uloženie dát | 15,6 (12–25) | 18,9 |
| **spolu bez čítaní** | **28,4** | **25,9** |
| čítanie formulára v portáli (odhad) | \~10 | \~6 |

Testy sa na dáta pýtajú po každom kroku (72 čítaní na faktúru, 162 na objednávku). Preto je počet čítaní v portáli odhadnutý: jedno až dve otvorenia na každú úlohu plus prehľad.

## Eventy mesačne a ročne

Stredný scenár je **69 000 eventov mesačne** a 828 000 ročne. Voucher 500 000 pokryje \~7 mesiacov prevádzky.

| scenár | eventov na faktúru / objednávku | mesačne | ročne | voucher 500k vystačí |
| --- | --- | --- | --- | --- |
| nízky: priama cesta, bez vrátení | 20 / 20 | 50 000 | 600 000 | 10 mesiacov |
| **stredný: ako namerane** | **28 / 26** | **69 000** | **828 000** | **7 mesiacov** |
| vysoký: časté vrátenia, viac úprav | 45 / 40 | 110 000 | 1 320 000 | 4,5 mesiaca |
| stredný + čítania formulárov | 38 / 32 | 92 000 | 1 104 000 | 5,4 mesiaca |

Výpočet: 2 000 × eventov na faktúru + 500 × eventov na objednávku. Stredný scenár: 2 000 × 28 + 500 × 26 = 69 000.

Nezaťažujú to: prihlásenia 50 používateľov, e-mailové notifikácie a zmeny nastavení. Sú to jednotky až stovky eventov mesačne.

## Infraštruktúra

Na tento objem stačí **jeden server s 4 vCPU a 16 GB RAM**, na ktorom beží celý stack v Docker Compose tak ako dnes. Pri 2 500 casoch mesačne je zaťaženie nízke, rezerva je pre OCR skenov a špičky ráno.

Namerané na bežiacom stacku (pokoj, testovacie dáta):

| kontajner | RAM |
| --- | --- |
| backend (NAE, Java 11) | 1,7 GB |
| Elasticsearch 7.17 | 1,25 GB |
| MongoDB 6 | 0,26 GB |
| Redis, nginx (frontend), mailpit | 0,09 GB |

**Prečo táto zostava:**

- **16 GB RAM:** backend pri 50 používateľoch potrebuje 3–4 GB heapu, Elasticsearch 2 GB a Mongo cache \~2 GB. Zvyšok je pre OS a tesseract.
- **4 vCPU (t3.xlarge):** OCR skenu zaberie jedno jadro na pár sekúnd. Pri \~100 faktúrach denne je to bez front. Burstable inštancia stačí, priemerné zaťaženie je hlboko pod baseline 40 %.
- **Disk 150 GB gp3:** prílohy \~0,5 MB × 2 500 mesačne = \~15 GB ročne. Plus databáza, index a obrazy kontajnerov. Vystačí na \~5 rokov.
- **Zálohy:** denný snapshot disku. Mongo a prílohy sú na tom istom disku, takže snapshot zálohuje všetko naraz.
- **Bez spravovanej DB:** Amazon DocumentDB nie je plná náhrada MongoDB 6 a pri tomto objeme by náklady znásobila. Mongo ostane v kontajneri.

## AWS kalkulačka

Zostava vyjde na **164,16 USD mesačne On-Demand**, 1 969,92 USD ročne. So záväzkom na 1 rok (EC2 Instance Savings Plan, bez platby vopred) je to \~112 USD mesačne.

[Odhad v AWS Pricing Calculator](https://calculator.aws/#/estimate?id=6098f5f53f5a9b1ef28a0dd843ff7938f81a2e38), región Europe (Frankfurt), ceny bez DPH.

| položka | konfigurácia | USD mesačne |
| --- | --- | --- |
| EC2 | t3.xlarge (4 vCPU, 16 GB), Linux, 1 inštancia, 100 % času, On-Demand | 140,16 |
| EBS | gp3, 150 GB | 14,28 |
| EBS snapshoty | denne, \~2 GB zmien na snapshot | 9,72 |
| **spolu On-Demand** |  | **164,16** |

**Porovnanie platby za server** (disk a snapshoty ostanú 24 USD):

| model | server USD mesačne | spolu USD mesačne |
| --- | --- | --- |
| On-Demand | 140,16 | 164,16 |
| Compute Savings Plan, 1 rok | 116,22 | 140,22 |
| EC2 Instance Savings Plan, 1 rok | 88,33 | 112,33 |

V kalkulačke nie je prenos dát von. Pri 50 používateľoch je to \~20 GB mesačne, pod bezplatným limitom 100 GB. Nie je tam ani verejná IPv4 adresa (\~3,60 USD mesačne) a SMTP (napr. Amazon SES, pri tomto objeme pod 1 USD).

## Riziká a čo spresniť

- **Definícia chargeable eventu v EE.** Najväčšia neistota. Ak sa ráta aj čítanie formulára, čísla stúpnu o tretinu. Ak len založenie case a dokončenie úlohy, klesnú na \~12 000 mesačne.
- **Podiel skenov.** OCR beží na tom istom serveri. Ak by skeny tvorili väčšinu z 2 000 faktúr a prichádzali v dávkach, treba zvážiť väčšie CPU (m6i.xlarge, \~+40 USD).
- **Rast príloh.** Počítané s 0,5 MB na faktúru. Pri skenoch po 3–5 MB je to \~100 GB ročne a disk treba zväčšiť skôr, alebo prílohy presunúť do S3.
- **Dostupnosť.** Jeden server nemá záložný. Výpadok znamená obnovu zo snapshotu, rádovo desiatky minút. Vysoká dostupnosť (dva servery, spravovaná DB, load balancer) by náklady zhruba strojnásobila.
- **Integrácie z dokumentu kolegov** (IMAP, sieťový priečinok, účtovný systém, archív) zatiaľ nie sú postavené. Každá pridá eventy za automatické založenie case a kroky, ktoré dnes robí človek.
