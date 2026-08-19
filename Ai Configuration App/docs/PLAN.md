# POC — AI konfigurácia pre digitalizáciu došlých faktúr

Plán implementácie **2 Petriflow procesov**. Reálne volanie LLM rieši Java na backende
(`callAIToolByConfig()`), Petriflow je len konfiguračná vrstva.

---

## 1. Celkový obraz

```
┌──────────────────────────────────────────────────────────────────────┐
│  ai_config (AIC) — singleton case, dva trvale otvorené tasky         │
│                                                                       │
│  ┌── t_codebook ──────────────┐  ┌── t_config ─────────────────────┐ │
│  │ ČÍSELNÍK MODELOV           │  │ PLATNÁ KONFIGURÁCIA             │ │
│  │ textarea + 2 buttony       │  │ selector + taskRef preview      │ │
│  │ multichoice local/external │  │ btn_apply → snapshot active_*   │ │
│  │ zdroj pravdy: models_json  │  │                                 │ │
│  └────────────┬───────────────┘  └──────────────┬──────────────────┘ │
└───────────────│─────────────────────────────────│────────────────────┘
                │ models_json (čítané cez getFieldValue)
                ▼                                 │ gather (Apply)
┌──────────────────────────────────────────────┐  │
│  single_settings (SST) — 1 case = 1 variant  │◄─┘
│  origin + model + system/user prompt         │
└──────────────────────────────────────────────┘
                │
                ▼  snapshot active_* v ai_config
        JAVA: callAIToolByConfig(...)
```

**Poradie implementácie:** `ai_config` (číselník + kostra) → `single_settings` →
gather v `ai_config` → Java konzument.
Číselník musí existovať prvý, lebo `single_settings` z neho plní options.

> Vzájomný odkaz: `single_settings` číta `ai_config.models_json`, `ai_config` číta
> settings pri gatheri. Nie je to cyklus (čítania sú v rôznych momentoch), ale
> znamená to, že **case `ai_config` musí vzniknúť ako prvý** a musí byť práve jeden.

### Prefix procesov — `workspace` sa nepoužíva

Nasadenie je **single-tenant Netgrif Platform**, kde premenná `workspace` neexistuje
a `processIdentifier` je holé `ai_config` / `single_settings` bez prefixu.
Referenčná gotcha 21 („vždy `workspace + id`") platí pre multi-tenant eTask — tu by
spôsobila, že `findCases` nenájde nič.

Namiesto toho sa prefix odvodí z `processIdentifier` vlastného casu. Tieto dva
riadky sú na začiatku každej akcie, ktorá siaha na iný proces:

```groovy
def pid = useCase.processIdentifier
def prefix = pid.contains("/") ? pid.substring(0, pid.lastIndexOf("/") + 1) : ""
```

Single-tenant: `pid = "ai_config"` → `prefix = ""` → hľadá sa `single_settings`.
Multi-tenant: `pid = "ws/ai_config"` → `prefix = "ws/"` → hľadá sa `ws/single_settings`.
Ten istý kód funguje v oboch, takže sa pri prípadnom presune nasadenia nemení nič.

Je to process funkcia `net_prefix(useCase)` v oboch procesoch. Process funkcie berú
**obyčajné `def` parametre**, nie len dátové polia, dajú sa volať navzájom a dajú sa
preťažovať podľa počtu argumentov — overené na `ticket_vacation.xml`. V
`single_settings` na tom stoja aj `find_ai_config()` a `model_slug()`.

---

## 2. Proces `ai_config` (AIC)

| Vlastnosť | Hodnota |
|---|---|
| id | `ai_config` |
| initials | `AIC` |
| icon | `settings_suggest` |
| defaultRole / anonymousRole | `true` / `false` |
| role | `admin`, `system` |
| režim | **singleton** — jeden case pre celú inštanciu |

### Sieť

```
[p_alive : tokens=1] ──read──► [t_codebook]     (priority 2)
                     └─read──► [t_config]       (priority 1)
```

Jedno miesto s tokenom, dva read arcy, dva trvale otvorené tasky (Pattern 16b).
Žiadne výstupné arcy. Splnené: presne jeden `tokens=1`, žiadny orphan read arc.

> Prečo dva tasky a nie jedna dlhá forma: na transition smie byť len **jeden**
> `<dataGroup>` (gotcha 4), takže obe sekcie by museli byť v jednej mriežke s ~25
> poliami. Rozdelenie na dva tasky dá dve čisté obrazovky. Ak by si predsa chcel
> jednu, je to jeden dataGroup + `i18n` polia s `<component><name>divider</name>`.

---

### 2a. Task `t_codebook` — číselník modelov

**Zdroj pravdy je `models_json`, nie options multichoicu.** Options sa vždy
prerátajú z JSON-u — nespoliehame sa na to, že runtime options prežijú reload,
a Java si vie ten istý JSON prečítať priamo.

> ⚠️ **Kľúč options nesmie obsahovať bodku ani dolár.** Options mapa ide do Mongo
> ako dokument a Mongo tie znaky v názve poľa nepovoľuje — `llama3.1:70b` zhodí
> uloženie s hláškou *„Map key … contains dots but no replacement was configured"*.
> Riešenie: v options je **slug** (`.` → `__D__`, `$` → `__S__`), reálny API kľúč
> zostáva v `models_json` a dohľadá sa cez slug. V `single_settings` ho drží
> samostatné pole **`model_key`** — a práve to číta gather do `active_model_key`,
> nie hodnotu enumu. Enum `model` drží slug a Java ho nikdy nevidí.

Formát:
```json
[{"key":"claude-opus-5","label":"Claude Opus 5","origin":"external"},
 {"key":"llama3.1:70b","label":"Llama 3.1 70B","origin":"local"}]
```

#### Pomenovanie modelov — `key` je API identifikátor

`key` posiela Java do API bez úprav, takže musí sedieť na znak. `label` je len
zobrazovaný text.

**Predplnené v `<init>` poľa `models_json`** (aktuálne Anthropic ID, bez
dátumovej prípony — `claude-opus-5`, nikdy `claude-opus-5-20260101`):

| key | label | kedy |
|---|---|---|
| `claude-opus-5` | Claude Opus 5 | najsilnejší, na zložité alebo zle čitateľné faktúry |
| `claude-sonnet-5` | Claude Sonnet 5 | pomer cena/výkon, rozumný default pre POC |
| `claude-haiku-4-5` | Claude Haiku 4.5 | najlacnejší, na jednoduché extrakcie vo veľkom objeme |
| `claude-opus-4-8` | Claude Opus 4.8 | záložný model |

Pri **inom externom poskytovateľovi** treba ID skopírovať presne z jeho
dokumentácie — nevymýšľať ho. Pri **lokálnych** modeloch je `key` tag runtimu
(Ollama `llama3.1:70b`, vLLM celá cesta k modelu), takže sa nedá určiť vopred —
dopĺňa ho administrátor podľa toho, čo má nasadené.

Tá istá tabuľka je aj v poli `help_models` priamo vo formulári.

#### Polia

| id | typ / komponent | poznámka |
|---|---|---|
| `models_json` | `text` | **hidden na oboch taskoch**, zdroj pravdy; predplnený zoznamom nižšie |
| `div_add` | `i18n` + `divider` | „Pridanie modelov" |
| `help_models` | `text` + `textarea` | read-only nápoveda k formátu a k pomenovaniu modelov |
| `new_models_origin` | `enumeration_map` | `local` \| `external` — kam sa pridáva |
| `new_models_input` | `text` + `textarea` | jeden model na riadok, `kluc \| nazov` |
| `btn_add_models` | `button` | placeholder „Pridať" |
| `div_list` | `i18n` + `divider` | „Existujúce modely" |
| `models_local` | `multichoice_map` | options = lokálne modely, value = výber na odobratie |
| `models_external` | `multichoice_map` | options = externé modely |
| `btn_remove_models` | `button` | placeholder „Odobrať vybrané" |
| `codebook_message` | `text` | spätná väzba („Pridané: 3, preskočené: 1") |

`<placeholder>` na `new_models_input`:
`Jeden model na riadok, formát kluc | nazov`
(bez `<`, `>`, `&` — C6; znak `|` je v poriadku)

#### Process funkcia — prekreslenie ponuky

```xml
<function scope="process" name="render_codebook"><![CDATA[
{ models_json, models_local, models_external ->
    def list = models_json.value ? new groovy.json.JsonSlurper().parseText(models_json.value) : []
    change models_local    options { list.findAll { it.origin == "local"    }.collectEntries { [(it.key): it.label] } }
    change models_external options { list.findAll { it.origin == "external" }.collectEntries { [(it.key): it.label] } }
}
]]></function>
```

Volá sa z: `t_codebook` **assign PRE**, po Pridať, po Odobrať.

#### Pridávanie — `new_models_input` set POST (nie z buttonu!)

> **Button nesmie čítať hodnotu textarey.** Overené na behu: textarea posiela
> hodnotu na server až pri strate fokusu, čo nastane v tom istom okamihu ako klik
> na button — obe zmeny idú v jednej setData požiadavke a event buttonu sa spracuje
> skôr, než sa hodnota textarey aplikuje. `phase="post"` to nerieši, lebo „post" je
> relatívne k **vlastnému** poľu buttonu, nie k celej dávke. Prejav: „Pridané: 0,
> preskočené: 0" a model sa objaví až po druhom kliku.
>
> Selecty a checkboxy tento problém **nemajú** — posielajú hodnotu okamžite pri
> zmene, takže sú uložené ešte pred klikom. Preto `btn_remove_models` (číta
> multichoice), `btn_apply` a `refresh` (čítajú enumeration) môžu zostať na buttone
> s `phase="post"`.
>
> Pravidlo: **hodnotu textového / textarea poľa spracuj v `set` evente toho poľa,
> nikdy nie z buttonu.**

Logika pridávania teda sedí na `new_models_input` `set` POST. Button
`btn_add_models` zostáva ako spúšťač blur-u a jeho akcia už len volá
`render_codebook` — správu o výsledku píše event textarey, takže sa neprepíše.

Textarea sa po pridaní **nečistí** — vyčistenie by muselo prísť z buttonu a to má
rovnaký problém s poradím. Text zostane v poli, opakovaný klik nič nepokazí
(duplicity sa preskočia).

```groovy
new_models_input: f.new_models_input, new_models_origin: f.new_models_origin,
models_json: f.models_json, codebook_message: f.codebook_message,
models_local: f.models_local, models_external: f.models_external;

def list = models_json.value ? new groovy.json.JsonSlurper().parseText(models_json.value) : []
def added = 0, skipped = 0
(new_models_input.value ?: "").split("\\r?\\n").each { line ->
    def parts = line.split("\\|").collect { it.trim() }
    def key = parts[0]
    if (!key) return
    if (list.any { it.key == key }) { skipped++; return }
    list << [key: key,
             label: (parts.size() > 1 && parts[1]) ? parts[1] : key,
             origin: new_models_origin.value]
    added++
}
change models_json      value { groovy.json.JsonOutput.toJson(list) }
change new_models_input value { "" }
change codebook_message value { "Pridané: " + added + ", preskočené (duplicita): " + skipped }
render_codebook(models_json, models_local, models_external)
```

#### `btn_remove_models` — set POST

```groovy
models_local: f.models_local, models_external: f.models_external,
models_json: f.models_json, codebook_message: f.codebook_message;

def list = models_json.value ? new groovy.json.JsonSlurper().parseText(models_json.value) : []
def toRemove = ((models_local.value ?: []) + (models_external.value ?: [])) as Set
def kept = list.findAll { !(it.key in toRemove) }

change models_json      value { groovy.json.JsonOutput.toJson(kept) }
change models_local     value { [] }
change models_external  value { [] }
change codebook_message value { "Odobraté: " + (list.size() - kept.size()) }
render_codebook(models_json, models_local, models_external)
```

> `"key" in field.value` je správny test členstva pre `multichoice_map` (gotcha 1).
> Nikdy `.contains()` — value je Set, nie String.

> Odobratie modelu, ktorý je použitý v niektorom `single_settings`, sa **nerieši
> tu** — ošetrí to stale-check pri načítaní settings (kap. 3).

---

### 2b. Task `t_config` — výber platnej konfigurácie

#### Polia — výber

| id | typ | poznámka |
|---|---|---|
| `settings_selector` | `enumeration_map` | options = všetky `single_settings` casy, key = `stringId` |
| `btn_refresh_settings` | `button` | znovunačítanie ponuky |
| `btn_new_settings` | `button` | vytvorí nový `single_settings` case (Pattern 24) |
| `settings_case_id` | `text` | hidden |
| `settings_preview` | `taskRef` | live embed `t_settings` vybraného casu |
| `btn_apply` | `button` | „Aktivovať konfiguráciu" — spustí gather |

#### Polia — snapshot (všetky `visible`, nikdy `editable`)

`active_settings_name`, `active_origin`, `active_model_key`, `active_model_label`,
`active_system_prompt`, `active_user_prompt`, `active_temperature`, `active_max_tokens`,
`activated_at` (`dateTime`), `activated_by` (`text`),
`config_status` (`enumeration_map`: `ok` \| `stale` \| `invalid`), `config_message` (`text`).

#### Plnenie selectora — `t_config` assign PRE + `btn_refresh_settings` set POST

```groovy
settings_selector: f.settings_selector;
change settings_selector options {
    findCases { it.processIdentifier.eq(prefix + "single_settings") }
        .collectEntries { [(it.stringId): (it.getFieldValue("settings_name") ?: it.stringId)] }
}
```

#### Live preview — `settings_selector` set POST

```groovy
settings_selector: f.settings_selector, settings_preview: f.settings_preview,
settings_case_id: f.settings_case_id;
change settings_case_id value { settings_selector.value }
def t = findTask { it.transitionId.eq("t_settings").and(it.caseId.eq(settings_selector.value)) }
change settings_preview value { t ? [t.stringId] : [] }
```

> Ak panel zostane prázdny, doplniť `assignTask(t)` — v `set` evente je to
> legitímna výnimka (gotcha 25/38).

#### Gather — `btn_apply` set POST

Toto je jadro aktualizačnej logiky:

```groovy
settings_selector: f.settings_selector, models_json: f.models_json,
active_settings_name: f.active_settings_name, active_origin: f.active_origin,
active_model_key: f.active_model_key, active_model_label: f.active_model_label,
active_system_prompt: f.active_system_prompt, active_user_prompt: f.active_user_prompt,
active_temperature: f.active_temperature, active_max_tokens: f.active_max_tokens,
activated_at: f.activated_at, activated_by: f.activated_by,
config_status: f.config_status, config_message: f.config_message;

def sc = settings_selector.value ? findCase { it._id.eq(settings_selector.value) } : null
if (!sc) {
    change config_status  value { "invalid" }
    change config_message value { "Nie je vybraná konfigurácia" }
    changeCaseProperty("color").about { "red" }
    return
}

change active_settings_name value { sc.getFieldValue("settings_name") }
change active_origin        value { sc.getFieldValue("origin") }
change active_model_key     value { sc.getFieldValue("model") }
change active_model_label   value { sc.getFieldValue("model_label") }
change active_system_prompt value { sc.getFieldValue("system_prompt") }
change active_user_prompt   value { sc.getFieldValue("user_prompt") }
change active_temperature   value { sc.getFieldValue("temperature") }
change active_max_tokens    value { sc.getFieldValue("max_tokens") }

// validácia proti číselníku
def list = models_json.value ? new groovy.json.JsonSlurper().parseText(models_json.value) : []
def entry = list.find { it.key == sc.getFieldValue("model") }
def problems = []
if (!sc.getFieldValue("model"))          problems << "nie je vybraný model"
if (sc.getFieldValue("model") && !entry) problems << "model nie je v číselníku"
if (entry && entry.origin != sc.getFieldValue("origin")) problems << "model nepatrí k zvolenému pôvodu"
if (!sc.getFieldValue("system_prompt"))  problems << "chýba system prompt"
if (!sc.getFieldValue("user_prompt"))    problems << "chýba user prompt"

change config_status  value { problems ? "invalid" : "ok" }
change config_message value { problems ? problems.join(", ") : "Konfigurácia je platná" }
change activated_at   value { java.time.LocalDateTime.now() }
change activated_by   value { userService.loggedOrSystem.email }
changeCaseProperty("color").about { problems ? "red" : "green" }
```

#### `btn_new_settings` — set PRE

```groovy
settings_selector: f.settings_selector, settings_preview: f.settings_preview;
def c = createCase(prefix + "single_settings")
def t = findTask { it.transitionId.eq("t_settings").and(it.caseId.eq(c.stringId)) }
if (t) assignTask(t)
change settings_preview value { t ? [t.stringId] : [] }
change settings_selector options {
    findCases { it.processIdentifier.eq(prefix + "single_settings") }
        .collectEntries { [(it.stringId): (it.getFieldValue("settings_name") ?: it.stringId)] }
}
change settings_selector value { c.stringId }
```

#### Singleton stráž — `caseEvents` create POST

Ak už existuje iný case `ai_config`, nastaviť `config_status = invalid`,
`config_message = "Duplicitná konfigurácia — použi pôvodný case"`, farba `red`.
Nehádžeme výnimku, aby sa POC dal odkliknúť.

---

### 2c. Task `t_test` — reálne testovacie volanie

Tretí trvale otvorený task nad tým istým miestom `p_alive`. Slúži na overenie, že
aktívna konfigurácia naozaj funguje, ešte pred tým, než sa pustí spracovanie faktúr.

| id | typ | poznámka |
|---|---|---|
| `div_test` | `i18n` + `divider` | „Test volania" |
| `config_status` | (zdieľané) | read-only, aby bolo vidno, či sa vôbec dá spustiť |
| `active_model_label` | (zdieľané) | read-only, ktorý model sa zavolá |
| `test_email` | `text`, `immediate` | schránka s testovacou faktúrou |
| `test_zip` | `file` | archív s testovacími faktúrami |
| `btn_run_test` | `button` | „Spustiť test" |
| `test_result` | `text` + `textarea` | návratová hodnota alebo popis chyby |

**Buď e-mail, alebo ZIP.** Akcia to kontroluje explicitne — pri oboch aj pri žiadnom
vypíše hlášku a nič nezavolá. Beží len keď `config_status == "ok"`.

#### Kontrakt na Javu

Button volá jednu metódu Spring beanu:

```groovy
def res = aiToolService.callAIToolByConfig(params)
```

`params` je `Map` s týmito kľúčmi:

| kľúč | zdroj | poznámka |
|---|---|---|
| `caseId` | `useCase.stringId` | aby si Java vedela vytiahnuť ZIP zo storage |
| `modelKey` | `active_model_key` | presný API identifikátor |
| `origin` | `active_origin` | `local` / `external` — podľa toho Java volí klienta a endpoint |
| `systemPrompt` | `active_system_prompt` | |
| `userPrompt` | `active_user_prompt` | obsahuje `{{invoice_text}}`, nahrádza Java |
| `temperature` | `active_temperature` | |
| `maxTokens` | `active_max_tokens` | |
| `testEmail` | `test_email` alebo `null` | |
| `zipFieldId` | `"test_zip"` alebo `null` | Java si súbor načíta z casu podľa tohto id |

**Bean sa volá `aiToolService`** — to je jediné, čo treba zladiť s Javou. Ak sa bude
menovať inak, prepíš ten jeden riadok v akcii `btn_run_test`.

Kým Java neexistuje, volanie hodí `MissingPropertyException`, akcia to odchytí a do
`test_result` vypíše názov chyby **plus všetky odoslané parametre v JSON-e**. Formulár
je teda použiteľný hneď a slúži zároveň ako kontrola, že sa skladajú správne dáta.

---

### 2d. Rozbaľovacie sekcie — jednotlačidlový prepínač

Prevzaté z `ticket_vacation.xml`. Hodnota buttonu sa pri každom kliku zvýši, takže
parita robí prepínač — netreba dve tlačidlá:

```groovy
boolean showIt = (((btn_toggle_help.value ?: 0) as Integer) % 2) == 1
make help_models, visible on transitions when { showIt }
make help_models, hidden  on transitions when { !showIt }
```

`on transitions` (množné číslo) platí na všetky tasky, netreba importovať konkrétny
`t.t1`. Východiskový stav určuje `<behavior>` v `dataRef`, nie akcia — preto:

| sekcia | dataRef | parita | správanie |
|---|---|---|---|
| nápoveda v `t_codebook` | `hidden` | `% 2 == 1` | zbalená, prvý klik rozbalí |
| snapshot v `t_config` | `visible` | `% 2 == 0` | rozbalená, prvý klik zbalí |

Snapshot sa zbaľuje po poliach — `make` berie jedno pole na riadok, takže 10 polí
znamená 20 riadkov. `config_status` a `config_message` zostávajú viditeľné vždy,
aby bolo aj po zbalení vidno, či je konfigurácia platná.

---

## 3. Proces `single_settings` (SST) — prerobenie existujúceho XML

Layout zostáva, menia sa ID polí a dopĺňa sa logika.

| teraz | po zmene | dôvod |
|---|---|---|
| `localVSexternal` | `origin` | zjednotenie s číselníkom |
| `text_0` | `system_prompt` | čitateľnosť v akciách |
| `text_1` | `user_prompt` | |
| `model` bez options | `model` + dynamické options z `models_json` | |
| `t1` | `t_settings`, roleRef `admin` **+** `system` | admin ho otvorí zo zoznamu, system rola umožní embed cez `taskRef` |
| — | `settings_name` | názov variantu = title casu |
| — | `model_label` | hidden, snapshot názvu modelu |
| — | `model_key` | hidden, **reálny API kľúč** — enum `model` drží len Mongo-bezpečný slug |
| — | `temperature`, `max_tokens` | patrí ku konfigurácii |
| — | `updated_at`, `updated_by` | audit + podklad pre stale signál |

### Sieť

```
[p_settings : tokens=1] ──read──► [t_settings]     (Pattern 16b)
```

Trvalá živosť je **nutná** — inak by `taskRef` panel v `ai_config` bol prázdny (gotcha 11).

### Markdown pre prompty — odporúčanie

**Zostať pri `type="text"` + `<component><name>textarea</name></component>`.**

Markdown *je* plain text — Java dostane presne to, čo je v poli. `richtextarea`
by uložil **HTML** (`<p>`, `<br>`, entity) a to by šlo rovno do promptu.
Zmena typu by teda kvalitu promptu zhoršila, nie zlepšila.

Do `user_prompt` odporúčam konvenciu placeholderu, napr. `{{invoice_text}}`,
ktorý Java nahradí OCR textom faktúry. Zdokumentovať v `<placeholder>`.

### Plnenie options modelu — jedna process funkcia, štyri spúšťače

```xml
<function scope="process" name="load_models"><![CDATA[
{ origin, model, model_label ->
    def cfg = findCases { it.processIdentifier.eq(prefix + "ai_config") }
                  ?.sort { it.creationDate }?.find { true }
    def raw = cfg?.getFieldValue("models_json")
    def list = raw ? new groovy.json.JsonSlurper().parseText(raw) : []
    def opts = list.findAll { it.origin == origin.value }
                   .collectEntries { [(it.key): it.label] }
    change model options { opts }

    if (model.value && !opts.containsKey(model.value)) {
        change model       value { null }      // model bol odobratý / zmenil pôvod
        change model_label value { "" }
    } else if (model.value) {
        change model_label value { opts[model.value] }
    }
}
]]></function>
```

| spúšťač | fáza | prečo |
|---|---|---|
| `t_settings` **assign PRE** | pre | prvé načítanie pri otvorení tasku |
| `origin` **set POST** | post | prepnutie local ↔ external prefiltruje ponuku |
| `refresh` button **set POST** | post | admin medzitým doplnil model do číselníka |

`model` **set POST** funkciu **nevolá** — `load_models` vie pole `model` vynulovať
(stale-check), čo by znovu spustilo ten istý set event. Label si preto rozlúskne
sám priamym prečítaním `models_json`. Zároveň volá `mark_updated` len keď
`model.value` nie je prázdny, aby vynulovanie pri otvorení tasku nespamovalo
stale signál.

> Filter podľa hodnoty poľa **nesmie** byť v QueryDSL bloku (gotcha 27) — najprv
> `findCases` podľa `processIdentifier`, potom `findAll` / parsovanie v Groovy.

### Ostatné akcie

- `settings_name` set POST → `changeCaseProperty("title").about { settings_name.value }`
- zmena `system_prompt` / `user_prompt` / `model` set POST →
  `updated_at = java.time.LocalDateTime.now()`, `updated_by = userService.loggedOrSystem.email`
  + push stale signálu do `ai_config` (kap. 4)

---

## 4. Snapshot vs. live — rozhodnutie

**Ide sa snapshotom** (`active_*` v `ai_config`). Dôvody:

- Java potrebuje jeden lookup, nie reťaz `ai_config → settings → číselník`.
- Beh faktúry sa nesmie zmeniť uprostred spracovania.
- `activated_at` / `activated_by` dá auditovateľnosť.

Cena je riziko zastaranej kópie. Ošetrenie — **stale signál (Pattern 25)**:

- `ai_config` má `text` pole `stale_signal` so `set` eventom (na `t_config`, ktorý je trvale živý).
- `single_settings` pri zmene promptu / modelu urobí:
  ```groovy
  def cfg = findCases { it.processIdentifier.eq(prefix + "ai_config") }?.find { true }
  if (cfg) setData("t_config", cfg, ["stale_signal": ["value": useCase.stringId, "type": "text"]])
  ```
- Set event v `ai_config`: ak `stale_signal == settings_case_id` a `config_status == "ok"`,
  nastaví `config_status = "stale"`,
  `config_message = "Konfigurácia bola zmenená — treba znovu aktivovať"`, farba `orange`.

Java potom berie len `config_status == "ok"` → zastaraná konfigurácia sa nepoužije.
Je to ~15 riadkov a je to presne tá poistka, ktorá zo snapshotu robí bezpečný vzor.

---

## 5. Java konzument — `callAIToolByConfig()`

Petriflow neposiela nič von. Java si vyhľadá posledný platný `ai_config` case a
prečíta z neho snapshot.

### Vyhľadanie

Filtrovať casy s `processIdentifier == <workspace>/ai_config`, ponechať tie s
`dataSet["config_status"].value == "ok"`, zoradiť podľa `activated_at` zostupne,
zobrať prvý. Pri singletone je to ten jeden case — ale defenzívne písaný lookup
funguje aj keby ste neskôr chceli viac paralelných konfigurácií, takže to napíšte
takto rovno.

### DTO, ktoré z toho vypadne

| Java pole | zdroj (`dataSet[...]`) |
|---|---|
| `modelKey` | `active_model_key` |
| `origin` | `active_origin` (`local` / `external` → výber klienta) |
| `systemPrompt` | `active_system_prompt` |
| `userPrompt` | `active_user_prompt` (nahradiť `{{invoice_text}}`) |
| `temperature` | `active_temperature` |
| `maxTokens` | `active_max_tokens` |
| `activatedAt` | `activated_at` (na logovanie, ktorá verzia bežala) |

Endpoint / API kľúč / provider **nie sú v Petriflow** — mapuje ich Java podľa
`origin` + `modelKey` (napr. `local` → interný vLLM/Ollama endpoint, `external` →
podľa prefixu kľúča modelu). Ak by to Java robiť nemala, stačí rozšíriť riadok
číselníka na `kluc | nazov | base_url` a doplniť pole do JSON-u — štruktúra to
unesie bez prepisovania.

**Odporúčam logovať `activatedAt` + `modelKey` ku každému spracovaniu faktúry** —
bez toho sa spätne nedá zistiť, ktorý prompt vyprodukoval ktorý výsledok.

---

## 6. Kontrolný zoznam pred odovzdaním XML

Podľa CHECKLIST v `petriflow_reference.md`:

- [ ] `initials` presne 3 veľké písmená (`AIC`, `SST`)
- [ ] žiadne `&`, `<`, `>` v `<title>` / `<label>` / `<option>` / `<placeholder>` (C6)
- [ ] prompty sú `type="text"` + `<component><name>textarea</name></component>`, nie `type="textarea"` (C7)
- [ ] `<component>` používa `<name>`, nie `<n>` (C8)
- [ ] `<init>` len v `<data>`, nikdy v `<dataRef>` (C10)
- [ ] `button` polia majú `<init>1</init>` a `<placeholder>` ako popisku (gotcha 19)
- [ ] všetky selekčné polia sú `_map` varianty (čítame ich v Groovy)
- [ ] každé pole použité v tele akcie je v import hlavičke (C5), žiadne `f.x` v tele
- [ ] **Nepoužívať `workspace`** — cieľom je single-tenant Netgrif Platform, kde táto premenná neexistuje. Prefix sa odvodí z vlastného casu (viď nižšie)
- [ ] filter podľa hodnoty poľa až mimo QueryDSL bloku (gotcha 27)
- [ ] trvale otvorené tasky: **len** read arc z miesta s `tokens=1`, žiadny výstupný arc (gotcha 23)
- [ ] presne jedno miesto s `tokens=1` v každom procese
- [ ] `action id` unikátne a sekvenčné v rámci celého dokumentu
- [ ] jeden `<dataGroup>` na transition (gotcha 4)
- [ ] `x`/`y` na každom `<place>` aj `<transition>`, žiadne duplicitné súradnice
- [ ] `</document>` na konci, nič useknuté (C9)

Import: https://builder.netgrif.cloud/modeler → test: https://etask.netgrif.cloud/

---

## 7. Otvorené body

1. **`temperature` / `max_tokens`** — plán ich dáva do `single_settings` (per konfigurácia).
   Ak ich má riešiť Java globálne, vypadnú aj zo snapshotu.
2. **Rozšírenie riadku číselníka** o `base_url` — potrebné len ak Java nemá endpoint
   odvodiť z `origin` + `modelKey`.
3. **História konfigurácií** — teraz singleton, „posledná platná" = ten jeden case.
   Ak by mala byť konfigurácia zvlášť pre hlavičku faktúry a zvlášť pre položky,
   pribudne pole `usage_type` a `ai_config` prestane byť singleton; Java lookup
   napísaný podľa kap. 5 to znesie bez zmeny.
