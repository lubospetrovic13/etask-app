| `anthropic` | `POST {base}/v1/messages` + `x-api-key` | `ai.anthropic.api-key` || `AnthropicAdapter.groovy` | Anthropic Messages API cez HTTP |# Backend —**Overené:** `mvn install` prechádza aj offline, v závislostiach nie je Anthropic SDK
ani konfliktný Kotlin. Anthropic request má tvar podľa verejnej dokumentácie
Messages API - `POST /v1/messages`, hlavičky `x-api-key` a `anthropic-version`,
odpoveď v `content[].text`, metriky v `usage.input_tokens` a `output_tokens`.
LLM podľa AI konfigurácie

Projekt: `C:\Users\petro\IdeaProjects\etask-backend-starter`

---

## 1. Štruktúra

`EtaskActionDelegate` zostáva tenký — obsahuje jednu metódu, ktorá presmeruje do služby:

```groovy
String callAIToolByConfig(Map params) {
    return aiCallService.callByConfig(params)
}
```

Logika je v novom balíku `com.netgrif.etask.ai`:

| súbor | čo robí |
|---|---|
| `AiCallService.groovy` | orchestrácia: zloží request, vyberie adaptér, poskladá report |
| `MailPayloadService.groovy` | zloží text mailu z formulára / JSON-u / ZIP-u |
| `AiProvider.groovy` | enum poskytovateľov + odvodenie z názvu modelu |
| `AiRequest.groovy`, `AiResult.groovy` | DTO |
| `AiProviderClient.groovy` | rozhranie adaptéra |
| `AnthropicAdapter.groovy` | Anthropic cez oficiálne Java SDK |
| `OpenAiCompatibleAdapter.groovy` | OpenAI, Ollama, vLLM, LM Studio, custom |
| `GeminiAdapter.groovy` | Google Gemini generateContent |
| `AiHttp.groovy` | minimálny JSON HTTP klient (Java 11) |

`mvn compile` prechádza.

### Pridanie ďalšieho poskytovateľa

1. Nová hodnota v `AiProvider`.
2. Nová trieda so `@Service`, ktorá implementuje `AiProviderClient`.

`AiCallService` si adaptéry vyzbiera cez `List<AiProviderClient>` — nikde sa nič
neregistruje ručne, netreba upravovať existujúci kód.

---

## 2. Providery a routovanie

> Vsetci traja poskytovatelia sa volaju priamo cez HTTP, ziadne SDK.
> Anthropic Java SDK 2.34.0 je skompilovane proti Kotlin stdlib 1.8+, kym
> Netgrif Application Engine so Spring Bootom 2.x pinuje Kotlin 1.6.21.
> Kompilacia presla, ale deserializacia odpovede padala na
> NoClassDefFoundError kotlin/jvm/optionals/OptionalsKt. Projekt tak nepotrebuje
> ziadnu novu zavislost.

Provider je **vlastnosť modelu v číselníku**, nie samostatné nastavenie — model
a protokol patria k sebe, takže sa nedá vybrať nekompatibilná kombinácia.

| provider | cesta | konfigurácia |
|---|---|---|
| `anthropic` | oficiálne Java SDK | `ANTHROPIC_API_KEY` v prostredí |
| `openai` | `POST {base}/v1/chat/completions` | `ai.openai.base-url`, `ai.openai.api-key` |
| `gemini` | `POST {base}/{ver}/models/{model}:generateContent` | `ai.gemini.api-key` |
| `local` | `POST {base}/v1/chat/completions`, bez kľúča | `ai.local.base-url` |
| `custom` | `POST {base}/v1/chat/completions` + Bearer | `ai.custom.base-url`, `ai.custom.api-key` |

V číselníku sa provider zapisuje ako tretie pole riadku:

```
claude-opus-5 | Claude Opus 5 | anthropic
llama3.1:70b  | Llama 3-1 70B | local
```

**Ak sa neuvedie, odvodí sa** — `claude-*` → anthropic, `gpt-*` / `o1..o9` → openai,
`gemini*` → gemini, inak podľa Pôvodu (Lokálny → local, Externý → custom). Tú istú
logiku má proces (`infer_provider`) aj Java (`AiProvider.resolve`), takže prázdna
hodnota nie je chyba — len sa rozhodne o krok neskôr.

### Prečo má Gemini vlastný adaptér

Tvar requestu je iný než OpenAI: system prompt ide do samostatného
`system_instruction`, správy do `contents` s `parts`, limity do `generationConfig`,
a odpoveď je v `candidates[0].content.parts[].text`. Zdieľanie s OpenAI cestou by
znamenalo vetvenie v každom kroku.

### Temperature sa na Anthropic neposiela

Na Claude Opus 5, Sonnet 5, Opus 4.8 a novších je parameter `temperature`
**odstránený z API** a request s ním končí chybou 400. Adaptér ho vynecháva a report
o tom píše poznámku. Na ostatných providerov sa posiela normálne.

---

## 3. Konfigurácia

```properties
# Lokálny runtime - Ollama, vLLM, LM Studio
ai.local.base-url=http://localhost:11434

# OpenAI
ai.openai.base-url=https://api.openai.com
ai.openai.api-key=${OPENAI_API_KEY:}
# novšie OpenAI modely chcú max_completion_tokens namiesto max_tokens
ai.openai.use-max-completion-tokens=false

# Google Gemini
ai.gemini.base-url=https://generativelanguage.googleapis.com
ai.gemini.api-version=v1beta
ai.gemini.api-key=${GEMINI_API_KEY:}

# Iný OpenAI kompatibilný endpoint (Groq, Together, OpenRouter, ...)
ai.custom.base-url=
ai.custom.api-key=${AI_CUSTOM_API_KEY:}

ai.timeout-seconds=180
```

**Anthropic kľúč** - properties ho čítajú z prostredia:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Ani jeden kľúč nedávaj do Petriflow poľa — skončil by v datasete casu a v exportoch.

---

## 4. Zdroj dát pre test — bez IMAP

Schránka sa nečíta. Používateľ v tasku **Test volania** vyberie jeden z troch režimov:

| režim | čo vyplní |
|---|---|
| `form` | Od, Komu, Predmet, Telo mailu, Prílohy - text (viac príloh oddelí riadkom `---`) |
| `zip` | archív s `mail.json` a/alebo textovými prílohami; oboje sa spojí |
| `json` | objekt priamo v poli, predvyplnená ukážka je v poli |

Tvar JSON-u — rovnaký pre režim `json` aj pre `mail.json` v ZIP-e:

```json
{
  "from": "dodavatel@firma.sk",
  "to": "faktury@nasafirma.sk",
  "subject": "Faktúra 2026001",
  "body": "V prílohe posielame faktúru.",
  "attachments": [
    { "name": "faktura.txt", "text": "FAKTÚRA č. 2026001 ..." }
  ]
}
```

Zo všetkých troch režimov vznikne **ten istý textový blok** (`Od:`, `Komu:`,
`Predmet:`, `Telo mailu:`, `Príloha N (nazov):`), takže prompt nemusí riešiť,
odkiaľ dáta prišli. Ten blok sa vloží namiesto `{{message}}` v user prompte;
ak zástupný text v prompte nie je, pripojí sa na koniec.

---

## 5. Vstup a výstup metódy

| kľúč v `params` | odkiaľ |
|---|---|
| `caseId` | `useCase.stringId` |
| `modelKey` | `active_model_key` |
| `provider` | `active_provider` (môže byť prázdny → odvodí sa) |
| `origin` | `active_origin` |
| `systemPrompt`, `userPrompt` | snapshot |
| `temperature`, `maxTokens` | snapshot |
| `inputMode` | `form` / `zip` / `json` |
| `mailFrom`, `mailTo`, `mailSubject`, `mailBody`, `mailAttachments` | režim `form` |
| `mailJson` | režim `json` |
| `zipFieldId` | `"test_zip"` |

Vracia report do poľa `test_result`:

```
Model:    claude-opus-5
Provider: anthropic
Vstup:    formulár (1043 znakov)
Volané:   anthropic (Messages API 2023-06-01)
Trvanie:  4312 ms
Tokeny:   vstup 1204, výstup 312
Pozn.:    temperature sa na Anthropic modely neposiela...

--- Odpoveď modelu ---
{ "category": "reklamacia", "confidence": 0.92, ... }
```

Chyba sa nikdy nepremietne do výnimky navonok — skončí v tom istom poli s typom
a správou. Akcia v XML má navyše vlastný try/catch, ktorý pri páde vypíše odoslané
parametre **bez obsahu mailu**, aby sa do poľa nedostali osobné údaje.

---

## 6. Jedno miesto na dorobenie

`MailPayloadService.extractText(String entryName, byte[] bytes)` — textové formáty
(`.txt`, `.md`, `.csv`, `.json`, `.xml`, `.html`, `.eml`) fungujú rovno. PDF vráti
`null`, takže test s PDF skončí zrozumiteľnou hláškou a vypíše, ktoré súbory
preskočil.

Doplnenie cez PDFBox:

```xml
<dependency>
    <groupId>org.apache.pdfbox</groupId>
    <artifactId>pdfbox</artifactId>
    <version>3.0.3</version>
</dependency>
```

```groovy
if (lower.endsWith(".pdf")) {
    return new PDFTextStripper().getText(Loader.loadPDF(bytes))
}
```

Na skenované faktúry napoj to isté OCR, ktoré pôjde na produkčné spracovanie — inak
test meria inú cestu než ostrá prevádzka.

---

## 7. Overené a neoverené

**Overené:** `mvn install` prechádza aj offline (`-o`), v strome závislostí už nie je
Anthropic SDK ani konfliktný Kotlin. Anthropic request má tvar podľa verejnej
dokumentácie Messages API — `POST /v1/messages`, hlavičky `x-api-key`
a `anthropic-version: 2023-06-01`, odpoveď v `content[].text`, metriky
v `usage.input_tokens` a `usage.output_tokens`.

**Prečo nie oficiálne SDK.** Bolo tam a padalo za behu: SDK 2.34.0 je skompilované
proti Kotlin stdlib 1.8+, kým Netgrif Application Engine so Spring Bootom 2.x pinuje
Kotlin 1.6.21. Kompilácia prešla, request odišiel, a deserializácia odpovede padla na
`NoClassDefFoundError kotlin/jvm/optionals/OptionalsKt`. Druhá možnosť bola zdvihnúť
`<kotlin.version>` na 1.9.x — Kotlin stdlib je binárne spätne kompatibilný, takže by to
pravdepodobne fungovalo, ale menilo by to stdlib pod celou platformou bez možnosti to
overiť. Jeden POST request má menší dosah.

**Neoverené, treba pozrieť pri prvom spustení:**

Prístup k hodnote `file` poľa v `MailPayloadService.fromZip`:

```groovy
def fileValue = useCase.dataSet[zipFieldId]?.value
def zipPath = Paths.get(fileValue.path as String)
```

Zápis `useCase.dataSet["id"].value` sa v projekte už používa (`updateMenuItemSection`),
takže by mal sedieť. Ak nie, alternatíva je poslať cestu z Groovy akcie —
`zipPath: test_zip.value?.path` v mape a v službe čítať `params.zipPath`.

Tvary requestov pre OpenAI a Gemini sú napísané podľa ich verejného API, ale
neotestované volaním — kým nebudú kľúče, over ich najprv na jednom requeste.

---

## 8. Test na tri kroky

1. `export ANTHROPIC_API_KEY=sk-ant-...`, reštart backendu.
2. AI konfigurácia → číselník už obsahuje 4 Claude modely s providerom `anthropic`.
   Vytvor konfiguráciu, vyber model, klikni **Aktivovať konfiguráciu** →
   stav **Platná**, v snapshote je vidno **Provider: anthropic**.
3. Task **Test volania** → režim **Vyplniť formulár** → do Prílohy - text vlož text
   faktúry → **Spustiť test**.

Ak sa vráti JSON s údajmi faktúry, funguje celá cesta číselník → konfigurácia →
snapshot → delegate → služba → adaptér → model.
