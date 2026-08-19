# Handout pre ďalšie vlákno

POC: **kategorizácia a vyťaženie klientskej komunikácie** pomocou LLM, konfigurovateľné
z Petriflow. Nasadenie Netgrif Platform 6.3.1, single-tenant, lokálne.

Predchádzajúce vlákno postavilo backend a procesy. **Toto vlákno robilo frontend — UI/UX** —
a popri tom refactorovalo procesy a spravilo audit portálu. Handout z prvého vlákna je
archivovaný v `docs/archive/handoff-01-backend-poc.md`; niektoré jeho tvrdenia už neplatia,
viď kap. 2 a 8.

---

## 0. Kde čo je

Tri repozitáre, ktoré sa v ďalšom vlákne **zlučujú do jedného priečinka**:

| repo | čo |
|---|---|
| `Desktop/Configuration` | tento priečinok — procesy, dokumentácia, nástroje |
| `IdeaProjects/etask-backend-starter` | backend (Java/Groovy), branch `dev` |
| `WebstormProjects/etask-frontend-starter` | frontend (Angular 13) |

Po zlúčení treba prepnúť `FE_ROOT` v `tools/sassc.js` (je to premenná prostredia, viď
`tools/README.md`) a cesty v tomto dokumente.

```
Configuration/
├── HANDOFF.md                        ← si tu
├── processes/
│   ├── ai_config.xml                 hlavný proces, singleton case, 3 trvalé tasky
│   ├── single_settings.xml           1 case = 1 konfigurácia
│   └── test-examples/                4 testovacie komunikácie + README
├── docs/
│   ├── FRONTEND_LEARNINGS.md         ⭐ nové — knižnica, kaskáda, pasti
│   ├── PETRIFLOW_LEARNINGS.md        ⭐ kde je klientova príručka nesprávna
│   ├── BACKEND.md                    ako je zapojený backend
│   ├── PLAN.md                       návrh; časti o faktúrach sú prekonané
│   ├── petriflow_reference.md        príručka od klienta, má vecné chyby
│   └── archive/handoff-01-…          handout z prvého vlákna
└── tools/                            meracie nástroje, viď tools/README.md
```

**Audit portálu** (samostatný dokument, zdieľateľný):
https://claude.ai/code/artifact/84d93bbf-0a75-43ac-97e9-d103705b6b5c

---

## 1. ⚠️ Prvá vec: rotovať Anthropic kľúč

**Kľúč treba rotovať.** Vypadol do výstupu predchádzajúceho sessionu (moja chyba pri
redigovaní) a navyše je v lokálnom git commite.

Presné zistenie, aby sa to nemuselo znovu overovať:

```
commit ccc819d ("-init") obsahuje sk-ant-api03   → 1× potvrdené
git branch -r --contains ccc819d                 → nič
origin/master / origin/HEAD                      → 3a8cca2 (rodič ccc819d)
```

Takže commit **nie je na GitHube** (`netgrif/etask-backend-starter`). Expozícia je zatiaľ
lokálna + transcript.

Čo urobiť:

1. **Rotovať kľúč** v Anthropic konzole
2. **Nepushovať `dev`** v súčasnom stave — `ccc819d` je nepushnutý, takže sa dá prepísať
   bez zásahu do zdieľanej histórie
3. `application.properties` **už je opravený** na `ai.anthropic.api-key=${ANTHROPIC_API_KEY:}`
   podľa pôvodnej kap. 2. Backend teda bez tej premennej AI volanie nespustí a vyhodí
   „Nie je nastavený ANTHROPIC_API_KEY" — to je zámer

Git históriu som **nepísal** — nezvratná operácia na cudzom repozitári.

> Toto **opravuje** `docs/archive/handoff-01-backend-poc.md` kap. 2, ktorá tvrdí, že kľúč
> v histórii nie je (*„overené `git log -S`"*). To už neplatí.

---

## 2. Ako spustiť

```bash
# backend
export ANTHROPIC_API_KEY=sk-ant-...        # bez toho AI volanie nepobeží
export ETASK_TEST_PASSWORD=...             # nepovinné, default test1234
cd <backend> && mvn -DskipTests install

# frontend
cd <frontend> && npm start                 # ng serve, čaká backend na :8080
```

Ak build padne na `handshake_failure` z Maven Central — je to prerušované a Maven si
zlyhanie zacachuje:

```bash
find ~/.m2/repository -name "*.lastUpdated" -delete && mvn -U -DskipTests install
```

Testovací účty (vytvorí ich `EtaskUserCreator` pri starte, existujúce preskočí):

| email | authorities |
|---|---|
| `admin@test.local` | ROLE_ADMIN, ROLE_USER |
| `operator@test.local` | ROLE_USER |
| `viewer@test.local` | ROLE_USER |
| `druhy@test.local` | ROLE_USER |

Heslo z `${ETASK_TEST_PASSWORD:test1234}`. Rozdiel authority je vidno na viewe `workflows`,
ktorý `nae.json` dáva len `ROLE_ADMIN`. **Procesné roly** (napr. `admin` v `ai_config`) sa
priraďujú v appke cez Konzolu, nie v properties.

---

## 3. Stav frontendu: čo je overené za behu

Merané v prihlásenej aplikácii, dark aj light.

| | výsledok |
|---|---|
| rám editovateľného poľa | `1.05 → 3.19 : 1` (dark), `3.30` (light) |
| editable vs read-only | box vs **žiadny box**, hodnota `10.43 → 13.96 : 1` |
| popis poľa | clamp na 2 riadky + popover, `fieldShift: 0` |
| popis nad všetkými typmi polí | `correct: true` pre 11/11, popover len keď je text zrezaný |
| footer panelu | 68 → **44.8 px** |
| taby | 48 → 40 px, `min-width: 0` |
| hustota cases aj tasks | margin 8 px, search 4/12, header 6/0 |
| stĺpec Priorita | **preč** (`Prípad │ Názov │ Riešiteľ │ Dátum priradenia`) |
| farebné riadky casov | prekryv + 4px akcentový pás, bez preblikávania |
| zbalený rail | `overlapsTabStrip: false` |
| boolean varianty | všetkých 5 renderuje, `iconOn/iconOff`, chip tóny, fallbacky |
| tab strip | `white → #1c1d22` |

### Čo NIE je overené za behu

Session vypadla na `/login` a prihlásiť sa nemôžem (heslá nezadávam), takže tieto zmeny sú
odmerané len staticky:

1. **`variant=section` v nasadenom nete.** XML je nasadené (`ai_config` v4.0.0), ale
   overenie chevronu naživo som už nestihol
2. **Žľab pri zbalenom raile** — presunul som ho z celého obsahového stĺpca len na blok
   vyhľadávania, aby zoznamy nestrácali 48 px šírky
3. **Upload pill** vo workflow view (ikona + text „Nahrať proces")
4. **Ikony a titulky na dashboarde**
5. **Testovací účty** — potrebujú reštart backendu

---

## 4. Frontend architektúra: seam, cez ktorý sa to dá meniť

Detail v `docs/FRONTEND_LEARNINGS.md`. Tri veci, ktoré treba vedieť hneď:

**Knižnice sú npm závislosti, pinnuté na 6.3.1.** Meniť `node_modules` je zbytočné. Update-safe
sú dve vrstvy: **téma** (knižnica posiela SCSS ako zdroj) a **app kód**.

**Vlastné field komponenty** idú cez existujúci `@Input`:

```
EtaskTaskPanelComponent → EtaskTaskContentComponent
  → EtaskFieldComponentResolverComponent → vlastné polia
```

Resolver je hardcoded `ngSwitch` **bez registry**, takže vlastný komponent znamená vlastniť
šablónu. Aktuálne vlastníme `boolean` a `button`.

**Pozor na `nc-task-list`.** Knižničný task list renderuje knižničný panel a teda knižničný
resolver — vlastné polia sa nezobrazia **vôbec**. Toto bola najdrahšia chyba vlákna a
neodhalí ju build. Správne je `<app-etask-task-list>`. Opravené na dvoch miestach.

---

## 5. Čo pridal frontend do Petriflow

Vlastný boolean komponent číta `<component><properties>`, ktoré knižnica ignoruje:

```xml
<component>
    <name>toggle</name>
    <properties><property key="variant">section</property></properties>
</component>
```

| variant | na čo | properties |
|---|---|---|
| `section` | klikací riadok s chevronom, nadpis sekcie | `iconOn`, `iconOff` |
| `segmented` | dve spojené tlačidlá | — |
| `checkbox` | najnižšia výška | — |
| `chip` | farebná bodka + text | `chipTrue`, `chipFalse` |
| `toggle` | pôvodné, **default** | — |

Default je `toggle`, takže pole bez properties sa chová presne ako predtým.

Vlastný **button** rieši B7: ikonu sa z akcie zmeniť nedá, ale hodnota buttonu sa pri kliku
inkrementuje, takže parita **je** stav. `iconOn`/`iconOff` sa vyberajú podľa nej.

Potvrdené na úrovni enginu: `change <field>` podporuje **iba** `value`, `choices`, `options`,
`allowedNets`, `validations` (`ActionDelegate.groovy:565`). `placeholder` tam nie je.

---

## 6. Stav procesov

Nasadené ako **`ai_config` v4.0.0**. Čo sa zmenilo:

- **Zmazané 4 páry nápoved** (`show_*_help` + `help_*`) — existovali len ako obchádzka
  zrezaného `<desc>`, ktorý je teraz opravený
- **`single_settings` má sekcie**: `Identifikácia`, `Model a limity`, `Prompty`
- **Auditné polia** presunuté na koniec do zbaľovacej `Diagnostika` (`show_audit`)
- **16 popisov skrátených** (`temperature` 141→80, `origin` 127→70, …)
- **`div_active` zrušený** — s `variant=section` je boolean nadpisom sekcie sám

Validované: parsovanie, **žiadne kolízie v mriežke** v 4 transitions, žiadne osirelé
`dataRef`, unikátne action id, **nula zvyšných odkazov** na 9 zmazaných polí, konce riadkov
zachované (`ai_config` CRLF, `single_settings` LF — nie sú rovnaké!).

**Po každom uploade treba nové casy** (B3) — case si drží svoju verziu siete.

### Boolean komponent je teraz použitý len raz na proces

Dôsledok mazania nápoved: `show_active` (len `t_config`) a `show_audit` (single_settings).
Na `t_codebook` a `t_test` **nie je žiadny**.

Navrhnuté, **neimplementované** (čaká na súhlas, lebo sú to nové polia → ďalší upload
a nové casy):

- `show_add` — zbalí polia na pridanie modelu, štartuje zbalené
- `show_raw` — zbalí `models_json`

`t_test` by som nechal — polia tam už skrýva prepínač režimu.

---

## 7. Otvorené veci, v poradí podľa efektu

**Frontend, app kód — bezpečné**

1. **Menu a dashboard.** Ikony sa hľadali presnou zhodou názvu uzla a `uriNodeIcons.json` mal
   jediný záznam „Reklamácie" — pozostatok starej domény, ktorý sa netrafil na nič, takže
   **každý uzol dostal generický `folder`**. Opravené: vyhľadávanie odolné na veľkosť písmen,
   podčiarkovníky a diakritiku, 17 ikon, titulok cez `getNodeTitle()`.
   **Chýba:** reálne názvy URI uzlov a `menu_item_identifier` existujúcich menu-item casov —
   `custom_views.json` obsahuje len `["general"]` a práve tým filtruje karty na dashboarde.
   Toto sú **dáta**, treba ich odčítať z prihlásenej appky.
2. **Hierarchia sekcií draweru** — Kategórie / Zobrazenia / Nastavenia / Archív majú rovnakú
   váhu, hoci prvé dve sú obsah a druhé dve nastavenia
3. **Dashboard je jedna karta** — najlacnejšie miesto na prehľad stavu

**Frontend, vyžaduje prevzatie knižničnej šablóny**

4. **Nahrávanie aplikácií** (`nc-import-net`): chýba drop zóna, `accept="text/xml"` môže na
   Windows skryť platné `.xml` (MIME sa hlási ako `application/xml` alebo prázdne), voľba
   Release nevysvetľuje dôsledok, po nahratí nie je potvrdenie čo sa nahralo
5. **Zoznam aplikácií** — stránkovanie chýba. *Vyhľadávanie existuje*, ale je skryté v
   `more_vert` menu hlavičky, takže je to problém objaviteľnosti

**Procesy**

6. Sekcie v `t_codebook` (kap. 6)
7. **Prompt vracia JSON, ale nikto ho neparsuje** — `test_result` je len text. Ďalší krok POC
   je proces, ktorý JSON rozparsuje do polí a založí case podľa kategórie. *Toto je jediná
   vec zo zadania POC, ktorá nie je hotová.*

**Backend**

8. `AiHttp` vytvára **nového `HttpClient` na každý request** — leak selector threadu a
   connection poolu. Odporúčam jeden zdieľaný klient + jeden retry na `IOException`
9. `MailPayloadService.extractText()` — PDF vráti `null`, doplnenie cez PDFBox je v
   `BACKEND.md` kap. 6
10. OpenAI a Gemini adaptéry **nikdy nezavolané**

---

## 8. Vecné opravy predchádzajúceho handoutu

Okrem kap. 1 (kľúč v histórii):

- **`handshake_failure` z AI volania nebolo o JDK ani o sieti.** Overené trianguláciou: ten
  istý POST z toho istého JDK 11+28 na tú istú URL prejde (`HTTP 401 via HTTP_2`, 6/6).
  `api.anthropic.com` **vyžaduje ALPN** a Java pri `HTTP_1_1` ALPN vôbec neposiela → handshake
  bez ALPN je odmietnutý (0/6). To isté platí pre Maven Central a OpenAI, nie pre Google.
  Najpravdepodobnejšie: Java spadla na HTTP/1.1 fallback, čím **zakryla pôvodnú príčinu**.
  Preto to odporúčanie v kap. 7 bod 8.
- **Bodka v `Llama 3.1 70B` nie je frontendová chyba.** Odmerané na živých dátach: kľúč
  `claude-opus-4-8` má label **„Claude Opus 4.8"** — bodka sa renderuje správne. Label
  s bodkou chýba už v `models_json`. Podozrenie: label sa niekde odvodí z kľúča, ktorý už
  prešiel slugovaním. **Tretí z troch pôvodných UX problémov je tým uzavretý** — patrí do
  číselníka, nie do FE.

---

## 9. Návyky, ktoré sa v tomto vlákne vyplatili

- **Neveriť kaskáde, merať ju.** `tools/cascade.js` odhalil, že dark scope re-emituje
  knižničné pravidlá s vyššou špecificitou. Čítaním sa to nedá uvidieť.
- **Neveriť kontrastu, počítať ho.** Prvý pokus o okraj dal 2.97:1 pri cieli 3:1. Rozdiel
  medzi „vyzerá dobre" a „prejde" je jeden odtieň.
- **Spustiť appku.** Chyba s `nc-task-list` prešla buildom aj každou statickou kontrolou;
  odhalilo ju až prekliknutie.
- **Overiť si vlastný testovací postup.** Dvakrát som skoro nahlásil neexistujúcu chybu —
  raz kvôli getteru bez settera, raz kvôli zbalenému panelu. Keď meranie vyzerá divne,
  najprv podozrievať meranie.
- **Byte-level kontrola pri zápise cudzích súborov.** `grep -c $'\r'` mi dal falošný pozitív
  a prepísal som LF súbor na CRLF. Počítať CRLF/LF v Node.
- **Po každej zmene XML validovať** — parsovanie, kolízie v mriežke, osirelé `dataRef`,
  odkazy v Groovy. Groovy odkaz na zmazané pole padne až za behu.
