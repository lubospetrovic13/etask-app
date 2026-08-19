# Handout pre ďalšie vlákno

POC: **kategorizácia a vyťaženie klientskej komunikácie** pomocou LLM, konfigurovateľné
z Petriflow. Nie faktúry — doména sa zmenila v priebehu práce, staré zmienky o faktúrach
v `PLAN.md` sú preto miestami neaktuálne (XML a prompty aktuálne sú).

---

## 1. Kde čo je

**Procesy** — `C:\Users\petro\Desktop\Configuration`

| súbor | čo to je |
|---|---|
| `ai_config.xml` | hlavný proces, singleton case, 3 trvale otvorené tasky |
| `single_settings.xml` | 1 case = 1 konfigurácia (model + prompty + limity) |
| `test-examples/*.json` | 4 testovacie komunikácie + README s tým, čo kontrolovať |
| `PLAN.md` | návrh a rozhodnutia; časti o faktúrach sú prekonané |
| `BACKEND.md` | ako je zapojený backend |
| `petriflow_reference.md` | príručka od klienta, **má vecné chyby** — viď `PETRIFLOW_LEARNINGS.md` |
| `PETRIFLOW_LEARNINGS.md` | čo príručka nepokrýva alebo pokrýva nesprávne |

**Backend** — `C:\Users\petro\IdeaProjects\etask-backend-starter`

| cesta | čo |
|---|---|
| `src/main/groovy/com/netgrif/etask/EtaskActionDelegate.groovy` | tenký, jedna metóda `callAIToolByConfig(Map)` presmeruje do služby |
| `src/main/groovy/com/netgrif/etask/ai/` | 10 nových súborov: orchestrácia, 3 adaptéry, skladanie mailu, DTO |
| `src/main/resources/application.properties` | blok `ai.*` na konci |
| `.gitignore` | pridané pravidlá pre lokálne konfigy s tajomstvami |

Nič nie je commitnuté — všetko je v pracovnej kópii (`git status`: 4× M, 1× untracked adresár).

---

## 2. ⚠️ Prvá vec, ktorú treba spraviť

**V `src/main/resources/application.properties` je živý Anthropic API kľúč v plaintexte.**
Súbor je trackovaný v gite. V histórii kľúč zatiaľ **nie je** (overené `git log -S`), takže
stačí ho odtiaľ dostať pred commitom a netreba nič rotovať.

Náprava:
1. `ai.anthropic.api-key=${ANTHROPIC_API_KEY:}` namiesto hodnoty
2. Kľúč do IntelliJ run configuration → Environment variables

Alebo do `application-local.properties` (už je v `.gitignore`) a spúšťať s profilom `dev,local`.

---

## 3. Architektúra v troch vetách

Číselník modelov je JSON v skrytom poli casu `ai_config`. `single_settings` z neho plní
ponuku modelov. Admin vyberie jednu konfiguráciu a klikne **Aktivovať** — tým sa jej
hodnoty prepíšu do snapshotu `active_*` v `ai_config`, a **výhradne ten snapshot** číta
backend.

```
ai_config                                 single_settings
├── t_codebook   číselník modelov  ──────► ponuka modelov (findCases + JSON)
├── t_config     výber + snapshot  ◄────── gather pri Aktivovať
│                                  ◄────── stale_signal pri zmene promptu
└── t_test       test volania      ──────► EtaskActionDelegate.callAIToolByConfig
                                                    │
                                           AiCallService
                                           ├── MailPayloadService (form/zip/json)
                                           └── adaptér podľa providera
                                               ├── AnthropicAdapter
                                               ├── OpenAiCompatibleAdapter
                                               └── GeminiAdapter
```

### Rozhodnutia, ktoré netreba znovu otvárať

- **Snapshot, nie live čítanie.** Backend robí jeden lookup a beh sa nemení uprostred.
  Cena je riziko zastaranej kópie, ošetrené `stale_signal` → stav *Zmenená*.
- **Provider patrí ku modelu v číselníku**, nie do nastavení. Model a protokol idú spolu,
  inak si admin vyberie nekompatibilnú kombináciu.
- **Prefix procesov sa odvodzuje z `useCase.processIdentifier`**, nie z `workspace`.
  Nasadenie je single-tenant Netgrif Platform, kde `workspace` neexistuje.
- **Žiadny IMAP.** Dáta na test dodá používateľ formulárom, ZIP-om alebo JSON-om.
- **Žiadne Anthropic SDK.** Konflikt Kotlin stdlib, viď kap. 5.

---

## 4. Stav: čo je overené a čo nie

### Overené za behu používateľom

- Číselník sa renderuje, pridávanie aj odoberanie modelov funguje
- Ponuka modelov v `single_settings` sa naplní z číselníka
- Aktivovať konfiguráciu dá stav **Platná**
- Test volania odošle reálny request na Anthropic API (odpoveď padla na SDK, viď nižšie)

### Overené mnou, nie za behu

- `mvn install` prechádza aj offline, v strome závislostí nie je SDK ani konfliktný Kotlin
- XML: well-formed, žiadne osirelé `dataRef`, žiadne kolízie v mriežke, sekvenčné action id

### Neoverené — treba pozrieť pri prvom spustení

1. **Nový spôsob pridávania modelov** (3 polia + select namiesto textarey s rúrkami) —
   napísaný po poslednom teste, nikto ho ešte neklikol.
2. **Boolean prepínače sekcií** — nahradili buttony, tiež netestované.
3. **Anthropic cez HTTP** — SDK bolo vymenené za priamy POST, request neprebehol.
4. **OpenAI a Gemini adaptéry** — napísané podľa verejnej dokumentácie, **nikdy nezavolané**.
   Kým nebudú kľúče, over ich na jednom requeste.
5. **`immediate="true"`** — atribút prevzatý z `ticket_vacation.xml`, jeho presná semantika
   nie je potvrdená. Predpoklad: posiela hodnotu okamžite namiesto čakania na blur.
6. **Čítanie ZIP-u** — `useCase.dataSet[id]?.value` → `.path`. Idióm `dataSet["x"].value`
   je v projekte použitý, ale na `file` poli neoverený.

---

## 5. Prečo tam nie je Anthropic SDK

Bolo, a padalo **za behu**, nie pri kompilácii:

```
NoClassDefFoundError: kotlin/jvm/optionals/OptionalsKt
  at com.anthropic.models.messages.ContentBlock$Deserializer.deserialize
```

`kotlin.jvm.optionals.OptionalsKt` pribudol v Kotlin stdlib **1.8**. Netgrif Application
Engine 6.3.1 so Spring Bootom 2.x pinuje Kotlin **1.6.21**. Request odišiel, spadla
deserializácia odpovede.

Druhá možnosť bola prepísať `<kotlin.version>` na 1.9.x — Kotlin stdlib je binárne
spätne kompatibilný, takže by to pravdepodobne fungovalo. Nezvolil som to, lebo by to
menilo stdlib pod celou platformou bez možnosti overiť dôsledky. Ak by SDK bolo
potrebné (typované chyby, retry, nové featury), toto je cesta.

Vedľajší efekt: projekt nepotrebuje **žiadnu** novú závislosť a zmizol aj problém
s lámavými TLS handshakami na Maven Central.

---

## 6. Otvorené veci

**Dva zámerné švíky v backende:**

- `MailPayloadService.extractText()` — textové formáty idú rovno, PDF vráti `null`
  a test skončí zrozumiteľnou hláškou. Doplnenie cez PDFBox je v `BACKEND.md` kap. 6.
  Na skeny treba napojiť to isté OCR, čo pôjde produkčne.
- Prílohy z formulára sa delia riadkom `---`. Funkčné, ale primitívne.

**Nedoriešené:**

- Prompt vracia JSON, ale **nikto ho neparsuje** — `test_result` je len text. Ďalší krok
  je proces, ktorý JSON rozparsuje do polí a založí case podľa kategórie.
- `PLAN.md` má na viacerých miestach ešte faktúrovú doménu.
- Duplicitné casy `ai_config`: singleton stráž len ofarbí case červeno a napíše poznámku,
  nič nebráni vytvoriť druhý. `find_ai_config()` uprednostní ten s naplneným číselníkom.

---

## 7. Ako to spustiť a otestovať

```bash
# 1. kluc do prostredia (alebo IntelliJ env vars)
export ANTHROPIC_API_KEY=sk-ant-...

# 2. build
cd C:/Users/petro/IdeaProjects/etask-backend-starter
mvn -DskipTests install
```

Ak build padne na `handshake_failure` z Maven Central — je to prerušované a Maven si
zlyhanie zacachuje:

```bash
find ~/.m2/repository -name "*.lastUpdated" -delete && mvn -U -DskipTests install
```

Potom v aplikácii:

1. Nahraj `ai_config.xml` a `single_settings.xml`
2. **Vytvor nový case** `ai_config` — pridanie dátových polí do siete sa do existujúcich
   casov nepropaguje, starý case by na chýbajúcich poliach padal
3. Prideľ si rolu `admin`
4. Task **Platná konfigurácia** → Nová konfigurácia → vyber model → **Aktivovať**
5. Task **Test volania** → režim *Vyplniť formulár* má predvyplnenú reklamáciu →
   **Spustiť test**

Diagnostika: pole **Zdroj číselníka** v konfigurácii ukáže, z ktorého casu `ai_config`
sa ponuka načítala a koľko casov existuje. Pole **Výsledok testu** obsahuje pri chybe
typ výnimky aj odoslané parametre (bez obsahu komunikácie).

---

## 8. Návyky, ktoré sa v tomto vlákne vyplatili

- **Po každej zmene XML spustiť validáciu** — parsovanie, `dataRef` bez `data`, kolízie
  v mriežke, sekvenčné action id. Odhalilo to viac chýb než čítanie.
- **Groovy nekontroluje volania metód pri kompilácii.** `mvn compile` nič nedokazuje.
  Pri externých knižniciach overiť podpisy cez `javap` proti jaru.
- **Pri každom runtime probléme sa najprv pozrieť, či to nie je problém verzie casu.**
  Trikrát to bola príčina, ktorú sa nedalo uhádnuť z kódu.
- **Neveriť `petriflow_reference.md` doslova** — má vecné chyby, viď `PETRIFLOW_LEARNINGS.md`.

---

## 9. Čo bude ďalšie vlákno robiť: grafické úpravy frontendu

Do ďalšieho vlákna príde tretí repozitár **`etask-frontend-starter`**, ktorý v tomto
vlákne **nebol** — nič z neho nie je preskúmané ani zdokumentované.

Podľa zadania je to projekt s **dvoma knižnicami**:

- **FE Netgrif logika** — dátové modely, služby, komunikácia s backendom
- **FE Netgrif komponenty** — vizuálna vrstva, **tú bude treba meniť**

Cieľ: grafické úpravy komponentov.

### Čo si v novom vlákne overiť ako prvé

Nič z tohto neviem, treba to zistiť:

1. **Ako sú knižnice zapojené** — sú to lokálne balíky v monorepe (`projects/` v Angular
   workspace), git submodule, alebo npm závislosti z registry? Rozhoduje to o tom, či sa
   dajú meniť priamo, alebo treba fork / patch / override.
2. **Angular verzia a build** — či sa knižnica buildí zvlášť (`ng build <lib>`) a linkuje,
   alebo sa kompiluje priamo so aplikáciou.
3. **Ako sa štýluje** — či majú komponenty vlastné SCSS, či je nad tým Angular Material
   téma, a či existuje spôsob prepísať vzhľad **bez** zmeny knižnice (téma, CSS custom
   properties, `::ng-deep`). Toto je dôležité: zmena knižnice sa pri jej update prepíše,
   zmena témy nie.
4. **Ktoré komponenty sa reálne renderujú** v našich troch taskoch — polia typu
   `text`/`textarea`, `enumeration_map` (select), `multichoice_map` (list), `boolean`,
   `button` s `icon`, `i18n` s `divider`, `file`, `taskRef`.

### Prečo je to relevantné pre to, čo je hotové

Z tohto vlákna sú tri otvorené UX veci, ktoré sú **frontendové, nie procesné** —
v Petriflow sa vyriešiť nedajú:

- **`<desc>` sa zobrazuje skrátené na jeden riadok** (viď screenshoty). Preto vznikli
  rozbaľovacie nápovedy ako obchádzka. Ak sa dá `desc` zobraziť poriadne, veľká časť
  tých nápoved je zbytočná.
- **Ikonu `button` sa z akcie zmeniť nedá** (C17 v learnings, B7). Preto sú prepínače
  sekcií `boolean` a nie strelky. Vlastný komponent by to vyriešil.
- **Bodka v zobrazovanom texte option zmizne** (`Llama 3.1 70B` → `Llama 31 70B`).
  Kľúč je v poriadku, je to len render — pravdepodobne opraviteľné na FE.

### Súvislosť s Petriflow

Zmena komponentov môže zmeniť, čo je v procesoch potrebné. Napríklad ak vznikne
komponent pre rozbaľovaciu sekciu, `make ... on transitions` prepínanie viditeľnosti
sa dá zjednodušiť alebo zrušiť. Pred väčšou zmenou procesov sa preto vyplatí vedieť,
čo FE zvládne.
