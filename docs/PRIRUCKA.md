# Príručka — čo inštancia obsahuje a ako ju používať

Toto je **používateľská** príručka: čo jednotlivé aplikácie robia, kto v nich
čo smie a ako sa nimi preklikať od začiatku do konca. Vývojárske recepty
(rozbeh, nasadenie, pasce Petriflow) sú inde — `docs/RUNBOOK.md`
a `docs/reference/cheatsheet.md`.

Píše sa tu o tom, čo v inštancii **naozaj je** a čo je overené akceptačnými
testami. Zoznam toho, čo zatiaľ nerobí, je v kapitole 9 — patrí do príručky
rovnako ako zvyšok, lebo pri odovzdaní klientovi je to prvá otázka.

---

## 1. Čo je v inštancii

| karta v ľavom menu | kto ju vidí | čo je za ňou |
|---|---|---|
| **Objednávky a faktúry** | zadávateľ, schvaľovateľ, riaditeľ, účtovník | dva priečinky: **Faktúry** (5 zobrazení) a **Objednávky** (3) |
| **Service Desk** | každý prihlásený | podanie požiadavky pre všetkých; tikety, zákazníci a podania len pre rolu `agent` |
| **Dovolenky** | zamestnanec, vedúci | žiadosti o dovolenku a rozhodovanie o nich |
| **Používatelia** | rola `spravca` | zakladanie účtov a prideľovanie rolí |
| **Nastavenia** | `ROLE_ADMIN` | konfigurácia schvaľovania: limit riaditeľa, schvaľovatelia stredísk |
| Majetok, General | admin | rozpracované / systémové dlaždice, do dema nepatria |

Celá appka sa dá rozbehať jedným príkazom, so všetkým v Dockeri (Mongo,
Elasticsearch, Redis, SMTP, backend, frontend — v Docker Desktope je to jeden
stack `etask`):

```bash
etask-configuration/tools/up.sh --docker
```

| adresa | čo tam je |
|---|---|
| http://localhost:4200 | portál |
| http://localhost:8025 | Mailpit — všetky notifikačné maily, ktoré appka poslala |
| http://localhost:8080 | REST API backendu |

Karta v menu je len **viditeľnosť**. Čo za ňou kto uvidí a čo smie spraviť,
riadia oprávnenia v procesoch — skrytie karty nie je bezpečnostné opatrenie.

---

## 2. Účty pre demo

| účet | heslo | roly | čím je dobrý |
|---|---|---|---|
| `super@netgrif.com` | `password` | správca, riaditeľ, všetky strediská, zadávateľ, účtovník, vedúci, agent | admin: konfigurácia, schvaľovanie nad limit |
| `operator@test.local` | `test1234` | zadávateľ, účtovník, schvaľovateľ *wellness*, zamestnanec | „účtovníčka": zapisuje a účtuje faktúry, žiada objednávky |
| `admin@test.local` | `test1234` | schvaľovateľ *reštaurácie* a *wellness*, riaditeľ, účtovník, vedúci, agent, správca | schvaľovateľ strediska a vedúci pri dovolenkách |
| `druhy@test.local` | `test1234` | zadávateľ, zamestnanec | druhý zamestnanec — ukáže, že cudzie veci nevidí |
| `viewer@test.local` | `test1234` | žiadne | ukáže, že bez roly nevidí nič |

Dve veci, ktoré treba vedieť dopredu:

* **`admin@test.local` má `ROLE_ADMIN`**, a tá **obchádza všetky oprávnenia
  Petriflow**. Na ukazovanie hraníc („cudzie stredisko si úlohu nepriradí")
  používaj `operator` alebo `druhy` — na adminovi prejde všetko a demo by
  klamalo.
* **Po zmene rolí sa treba odhlásiť a prihlásiť.** Prihlásená session drží
  staré identifikátory rolí, takže nová rola sa prejaví až po novom prihlásení.

---

## 3. Rozbehanie od nuly

```bash
etask-configuration/tools/up.sh
```

Jeden príkaz: databázy v Dockeri, build, backend na `:8080`, import procesov
a pridelenie rolí. Frontend zvlášť:

```bash
etask-configuration/tools/up.sh --frontend
```

Portál je na `http://localhost:4200`, prihlásenie `super@netgrif.com` /
`password`.

Úplne čistý štart (zahodí databázu, vytvorí testovacie účty):

```bash
ETASK_TEST_PASSWORD=test1234 etask-configuration/tools/up.sh --fresh
```

Bez `ETASK_TEST_PASSWORD` sa testovacie účty **nevytvoria** — je to zámer, aby
sa v ostrej inštancii neobjavili účty s dohodnutým heslom.

---

## 4. Objednávky a faktúry

### Načo to je

Schvaľovanie došlých faktúr a objednávok tak, aby bolo vždy vidno **kto čo
schválil a kedy**, a aby sa nič nezaplatilo bez druhého páru očí. Nadväzuje na
cenovú ponuku pre Hotel Kaskády (Fáza 1 faktúry, Fáza 2 objednávky).

### Roly

| rola | čo smie |
|---|---|
| `zadavatel` | zapísať faktúru, požiadať o objednávku, potvrdiť objednanie |
| `schv_<stredisko>` | schváliť faktúry a objednávky **svojho** strediska |
| `schvalovatel` | záloha: schvaľuje tam, kde stredisko vlastného schvaľovateľa nemá |
| `riaditel` | schvaľuje nad limit |
| `uctovnik` | zaúčtuje schválenú faktúru |

### Faktúra krok za krokom

1. **Zadávateľ**: *Faktúry → Došlé faktúry → +*. Vyplní dodávateľa, číslo,
   sumu, splatnosť, stredisko a za čo to je. Ak má súbor (XML e-faktúru, PDF
   alebo sken), priloží ho a stlačí **Načítať z prílohy** — polia sa vyplnia
   samy (viď nižšie). **Podať na schválenie**.
2. **Schvaľovateľ strediska** vidí faktúru v *Faktúry na schválenie*. Úlohu si
   musí **prevziať** (je zdieľaná), potom *Schváliť / Vrátiť na doplnenie /
   Zamietnuť*. Pri vrátení a zamietnutí je dôvod povinný.
3. **Nad limit** (predvolene 1 000 € s DPH) ide faktúra ešte **riaditeľovi**,
   do limitu rovno na zaúčtovanie.
4. **Účtovník** v *Na zaúčtovanie* zapíše číslo dokladu z účtovníctva
   a **Zaúčtovať**. Bez čísla dokladu to neprejde.
5. Faktúra skončí ako **Uzavretá** — jeden read-only pohľad s celým priebehom:
   kto schválil, kedy, s akou poznámkou, odkiaľ boli údaje.

Stav je v zozname **vlastný stĺpec** (a je preložený — v anglickom portáli je
tam *Posted*, nie *Zaúčtovaná*) a je vidno aj vo farbe riadku: šedá rozpísaná,
modrá čaká na stredisko, indigo u riaditeľa, tyrkysová na zaúčtovanie, zelená
zaúčtovaná, oranžová vrátená, červená zamietnutá.

Vedľa stavu je stĺpec **U koho leží** — mená ľudí, ktorí faktúru práve majú na
stole. Sú to mená, nie roly: „riaditeľ" by v anglickom portáli zostalo
slovenské, a meno je aj užitočnejšie, lebo sa dá zavolať.

Názov prípadu nesie **dodávateľa, číslo a sumu** (u objednávky predmet a cenu),
a kým nie je vyplnený, číslo prípadu (`FAK-…`, `OBJ-…`). Stav v ňom zámerne
nie je: názov prípadu je v engine obyčajný `String`, takže sa neprekladá —
slovenský stav v názve by bol v anglickom portáli jediná slovenská vec v každom
zozname.

### Objednávka krok za krokom

1. **Zadávateľ**: *Objednávky → +*. Napíše, čo treba, a pridá **požiadavky** —
   riadky *položka · množstvo · jednotka · cena za jednotku*. Tlačidlo **Pridať
   požiadavku**; zaškrtnutím a *Odobrať vybrané* sa riadok zmaže. Cena sa
   **počíta zo súčtu**, netypuje sa. Bez aspoň jednej požiadavky sa objednávka
   podať nedá.
2. **Schvaľovateľ strediska** rozhodne, nad limit ešte **riaditeľ**.
3. **Zadávateľ** potvrdí objednanie: dodávateľ a **číslo objednávky**. To číslo
   sa potom používa na faktúre.

### Faktúra na základe objednávky

Na zápise faktúry je pole **Fakturovať na objednávku** — ponúka schválené
objednávky. Po výbere sa doplní číslo objednávky a dodávateľ a appka **porovná
sumy**:

> Vybavenie wellness · objednané za 780.00 € · **POZOR: fakturuje o 120.00 €
> viac, než bolo objednané**

Faktúru to nezastaví (v praxi drobné rozdiely bývajú), ale schvaľovateľ,
riaditeľ aj účtovník to majú pred očami.

### Načítanie z prílohy

| príloha | ako sa polia získajú | istota |
|---|---|---|
| XML e-faktúra (UBL 2.1 / CII podľa EN 16931, ISDOC) | **čítajú sa** z elementov | presné |
| PDF s textovou vrstvou | hádajú sa podľa popiskov | dobré |
| sken, fotka | OCR (`tesseract`), potom tie isté popisky | odhad |

Typ sa určuje **podľa obsahu súboru**, nie podľa prípony. Načítanie **nikdy
neprepíše to, čo si napísal** — vyplní prázdne polia a rozdiel len ohlási.
V priebehu faktúry zostane zapísané, odkiaľ údaje pochádzajú, takže pri
kontrole je rozdiel medzi „čítané z XML" a „odhad OCR" vidno.

OCR treba doinštalovať (`apt-get install tesseract-ocr tesseract-ocr-slk`);
bez neho appka pri skene napíše, že binárka chýba, a beží ďalej.

### Konfigurácia (karta Nastavenia)

Jedna obrazovka, vidí ju len admin:

* **Limit riaditeľa** — nad túto sumu schvaľuje po stredisku ešte riaditeľ.
  Platí rovnako pre faktúry aj objednávky a prejaví sa **okamžite**, bez
  nasadzovania novej verzie procesu.
* **Schvaľovatelia stredísk** — kto schvaľuje Hotel, Reštauráciu, Wellness,
  Údržbu, Marketing, Správu. Ďalej zadávatelia, účtovníci a riaditelia.

Formulár ukazuje **skutočný stav rolí** (nie to, čo si tam niekto naposledy
uložil) a uložením role prideľuje a odoberá. Kto rolu práve dostal, musí sa
odhlásiť a prihlásiť.

### Na čo si dať pozor

* **Stav faktúry.** Na každej faktúre je aj úloha **Stav faktúry** (na
  objednávke *Stav objednávky*) — read-only obrazovka s celým prípadom vrátane
  priebehu, dostupná od podania po uzavretie a viditeľná aj pre zadávateľa.
  Existuje presne preto, že zadávateľ po podaní nemá čo robiť (štvoro očí ho
  vylúči zo schvaľovateľov) a bez nej nemal kde zistiť, či sa podanie vôbec
  podarilo a u koho faktúra leží.
* **Notifikácie.** Pri každom posune príde e-mail tomu, kto je na rade; keď sa
  faktúra uzavrie (zaúčtuje alebo zamietne), príde zadávateľovi. Na demo
  inštancii ich zachytáva Mailpit — **http://localhost:8025** — a nikam
  neodchádzajú. Vypnúť sa dajú premennou `ETASK_NOTIFICATIONS=false`.
  V priebehu prípadu je riadok „upozornenie e-mailom: 2×", takže je
  dohľadateľné, či mail naozaj odišiel.
* **Štvoro očí.** Kto faktúru zapísal, tomu sa na schválenie **nepošle** —
  v zozname úloh ju vôbec neuvidí. Ak si stredisko nemá kto schváliť, appka to
  napíše do priebehu a pošle to všetkým schvaľovateľom, prípadne riaditeľovi.
* **Zdieľané úlohy sa preberajú.** Schválenie a zaúčtovanie sú fronty —
  najprv *Prevziať*, potom sa dá rozhodnúť. Uvoľniť sa dajú tlačidlom
  *Uvoľniť pre iného*.
* **Prípad si drží verziu procesu, v ktorej vznikol.** Po zmene procesu treba
  testovať na novom prípade; do starého nové polia nepribudnú.
* **Jazyk.** Popisky, tlačidlá, možnosti aj stavy sú v SK aj EN. Po anglicky
  nezostávajú len texty, ktoré appka **zapísala v čase udalosti** — priebeh
  prípadu a audit v konfigurácii. Sú to záznamy o tom, čo sa stalo, nie
  popisky, a engine ich prekladať nevie (`Case.title` aj textové polia sú
  obyčajný `String`).

---

## 5. Service Desk

Príkladová aplikácia podpory: požiadavka od zákazníka alebo zamestnanca sa
zmení na tiket, ten prejde triážou k operátorovi a má sledovanú lehotu odozvy.

### Podanie požiadavky

* **Prihlásený zamestnanec**: *Service Desk → Podať požiadavku → +*. Sprievodca
  má štyri kroky (kategória → popis → kontakt → súhrn) a klikanie DOKONČIŤ
  medzi krokmi nepotrebuje. **Meno a e-mail sa predvyplnia** z prihláseného
  účtu.
* **Anonym z verejného odkazu**: ten istý formulár bez prihlásenia. Odkaz je
  `/process/<base64 identifikátora siete>`, teda pre `service_desk/sd_intake`
  → `/process/c2VydmljZV9kZXNrL3NkX2ludGFrZQ==`. Vyžaduje podpisový kľúč
  (`certificates/private.der`) — bez neho vracia verejný formulár 401 bez
  vysvetlenia.

Po odoslaní dostane podávateľ **číslo tiketu** a vznikne prípad v *Tikety*.

### Práca operátora (rola `agent`)

*Tikety* → triáž (priorita, typ, priradenie), práca cez pracovné položky
(*Moje úlohy*), pauza a vyriešenie. Lehota odozvy sa počíta v pracovnom čase
Po–Pi 08:00–16:00 podľa priority (A/B/C = 2/4/8 hodín). *Zákazníci* držia
organizácie a ich tímy — kto je v tíme zákazníka, vidí jeho tikety.

---

## 6. Dovolenky

Jednoduché schvaľovanie pre jedno oddelenie.

1. **Zamestnanec**: *Dovolenky → Žiadosti o dovolenku → +*, vyplní od–do
   a dôvod. Počet dní sa počíta sám, obrátený termín appka nepustí.
2. **Vedúci** rozhodne v jednej úlohe: *Schváliť / Zamietnuť / Vrátiť na
   prerobenie*. Pri vrátení je dôvod povinný a žiadosť sa vráti zamestnancovi
   s pôvodnými hodnotami.
3. Kým sa čaká, žiadateľ nemá čo robiť — stav si prečíta z názvu v zozname.
   Po rozhodnutí majú obaja jeden read-only pohľad s celým priebehom.

Cudziu žiadosť iný zamestnanec nevidí ani vo vyhľadávaní.

---

## 7. Používatelia

Pre rolu `spravca`: založenie účtu (*Nový používateľ*), zmena mena, hesla,
systémových oprávnení a **procesných rolí** — vyberie sa proces, verzia
(„všetky verzie" je to, čo chceš skoro vždy) a roly.

Prideľovanie rolí pre schvaľovanie sa dá robiť aj tu, ale pohodlnejšia je
**karta Nastavenia** — tá pracuje v pojmoch stredísk, nie procesov a verzií.

---

## 8. Demo scenár na 20 minút

Postupnosť, ktorá prejde všetkými aplikáciami a všetkými vetvami. Účty
prepínaj odhlásením (roly sa načítajú pri prihlásení).

**A. Konfigurácia — `super`**

1. *Nastavenia → Konfigurácia schvaľovania*. Ukáž limit a schvaľovateľov
   stredísk. Zmeň limit na `500` a **Uložiť nastavenia**.

**B. Faktúra pod limitom — `operator` → `admin`**

2. `operator`: *Faktúry → Došlé faktúry → +*, dodávateľ „Gastro Trade",
   číslo `2026041`, suma `240,50`, splatnosť, stredisko **Reštaurácia**,
   predmet. **Podať na schválenie**.
3. `admin`: *Faktúry na schválenie* → **Prevziať** → *Vrátiť na doplnenie*
   s dôvodom („chýba skan"). Ukáž, že sa vrátila zadávateľovi.
4. `operator`: doplní a podá znova; `admin` schváli.
5. `operator` (účtovník): *Na zaúčtovanie* → **Prevziať** → skús uložiť bez
   čísla dokladu (odmietne to) → vyplň `DF-2026-00412` → **Zaúčtovať**.
6. Ukáž *Uzavreté faktúry* → celý priebeh na jednej obrazovke.

**C. Nad limit — dve úrovne**

7. `operator`: nová faktúra na `700 €`, stredisko **Wellness**. Pri písaní sumy
   sa ukáže upozornenie, že pôjde aj riaditeľovi (limit je 500).
8. `admin` schváli za stredisko → faktúra je *Čaká na riaditeľa*.
9. `super` schváli ako riaditeľ → ide na zaúčtovanie.

**D. Štvoro očí**

10. `operator`: založí faktúru na stredisko **Wellness** (kde je sám
    schvaľovateľom) a podá ju. Ukáž, že **vo svojom zozname úloh ju nemá** —
    schváliť ju musí niekto iný.

**E. Objednávka a fakturácia na ňu**

11. `druhy`: *Objednávky → +*, pridá dve požiadavky (napr. 200 ks uterákov
    à 3,50 € a 100 ks prestieradiel à 0,80 €) — ukáž, že suma je súčet.
12. `admin` schváli, `druhy` potvrdí objednanie s číslom `OBJ-2026-119`.
13. `operator`: nová faktúra → **Fakturovať na objednávku** → vyber tú
    objednávku. Doplní sa dodávateľ a číslo; zadaj sumu vyššiu ako objednávka
    a ukáž upozornenie o rozdiele.

**F. Service Desk**

14. `druhy`: *Service Desk → Podať požiadavku → +* — sprievodca so
    štyrmi krokmi, kontakt predvyplnený. Odošli a ukáž číslo tiketu.
15. `admin` (agent): *Tikety* → triáž a prevzatie. Ukáž, že `druhy` v tej
    karte vidí len *Podať požiadavku*.

**G. Dovolenky**

16. `operator`: *Dovolenky → +*, termín a dôvod, podaj.
17. `admin` (vedúci): rozhodni. Ukáž vrátenie aj schválenie.

**H. Konfigurácia zaberá**

18. `super`: *Nastavenia* → pridaj `druhy` medzi schvaľovateľov **Marketingu**,
    vráť limit na `1000`, ulož.
19. `druhy` sa odhlási a prihlási; `operator` podá faktúru na marketing —
    `druhy` ju má na schválenie.

**I. Bez roly nevidí nič**

20. `viewer`: v ľavom menu nemá žiadnu kartu aplikácie.

---

## 9. Čo aplikácie (zatiaľ) nerobia

Otvorene, aby sa na to neprišlo až pri odovzdaní:

* **Vstup faktúr e-mailom (IMAP)**, **prihlasovanie cez M365/Azure AD**
  a **export do Softip Profit** nie sú urobené. Zaúčtovanie je preto ľudský
  krok s číslom dokladu.
* **OCR** vyžaduje nainštalovaný `tesseract`; bez neho fungujú XML e-faktúry
  a PDF s textovou vrstvou.
* **Notifikácie e-mailom** nie sú zapnuté (bez nakonfigurovaného SMTP by
  zhodili operáciu).
* **Faktúra sa spätne nezapíše do objednávky** — väzba je jednosmerná,
  cez číslo objednávky.
* **Service Desk**: zákazník po odoslaní stav svojho tiketu nevidí, príloha
  z formulára sa do tiketu neprenáša, SLA nepozná sviatky, verejný formulár
  nemá rate limiting.
* **Majetok** je rozpracovaná appka z inej iterácie, do dema nepatrí.
* Prípady vytvorené pred zmenou procesu bežia na starom modeli — po väčšej
  zmene ich treba zmazať (`python3 tools/sccheck.py --wipe`).

---

## 10. Kde je čo (pre toho, kto to preberá)

| chcem | súbor |
|---|---|
| rozbehať, nasadiť, bežné úlohy | `docs/RUNBOOK.md` |
| pravidlá a pasce Petriflow na jednu stranu | `docs/reference/cheatsheet.md` |
| metódy volateľné z akcie | `docs/reference/action-api.md` |
| čo engine robí inak, než sľubuje | `docs/ENGINE_ISSUES.md` |
| procesy aplikácií | `processes/fa_faktura.xml`, `ob_objednavka.xml`, `sc_menu.xml`, `sc_nastavenia.xml`, `sd_*.xml`, `dv_*.xml`, `pu_*.xml` |
| akceptačné testy proti bežiacemu enginu | `tools/sccheck.py` (faktúry a objednávky), `tools/dvcheck.py`, `tools/pucheck.py` |

Overenie, že inštancia robí to, čo táto príručka tvrdí:

```bash
cd etask-configuration && python3 tools/sccheck.py
```
