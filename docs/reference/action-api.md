# Extension pointy volateľné z Petriflow akcie

> **Generované — needituj ručne.** `python3 tools/pfapi.py > docs/reference/action-api.md`
> Zdroj: `application-engine-6.3.1.jar` + `EtaskActionDelegate.groovy`.

Všetko nižšie sa dá zavolať priamo z `<action>` alebo `<function>` menom,
bez importov. Delegát je dynamický, takže preklep prejde parserom aj
importom a spadne až za behu — o to viac sa vyplatí pozrieť sem.

## Pravidlo: najprv tento zoznam, potom nový kód

Metóda, ktorá tu je, sa nemá písať znova. Nie je to štýlová poznámka —
stálo to hodiny dekompilovania bajtkódu a technický dlh v `UriNodeData`,
kde sú dnes dve polia pre to isté, lebo som nevedel o existujúcom
`setUriNodeData(..., roleIds)`.

## Vlastné metódy tohto projektu — pozri sem PRVÉ

`EtaskActionDelegate` dedí engine a pridáva toto. Sú prispôsobené tomuto
stacku, takže bývajú správnejšie než ekvivalent v enginu.

### `createOrUpdateMenuItem(String id, String uri, String type, String query, String icon, String title, List<String> allowedNets, Map<String, String> roles = [:], Map<String, String> bannedRoles = [:])`
Zaloz alebo uprav polozku menu.

### `createOrUpdateMenuItem(String id, String uri, String type, String query, String icon, I18nString title, List<String> allowedNets, Map<String, String> roles = [:], Map<String, String> bannedRoles = [:])`
To iste s dvojjazycnym nazvom polozky menu.

### `pripoj_do_uzla(Object item, String uri)`
Prepoji existujucu polozku menu na URI uzol danej cesty.

### `updateMenuItemSection(String id, String section = "settings")`
Nahrada za private `ActionDelegate.updateMenuItemRoles`. */

### `updateMenuItemSection(Case menuItem, String section = "settings")`

### `setUriNodeDataFilters(String uri, List<String> menuItemIdentifiers)`
set filters to uri node

### `setUriNodeData(String uri, String title, String section, String icon, boolean isSvgIcon = false, boolean isHidden = false)`
Ikona, sekcia a viditelnost karty uzla URI.

### `canUserAccessMenuItem(Case menuItem, IUser user)`

### `userIdsOf(Object value)`
Vytiahne id uzivatelov z hodnoty userList pola.

### `usersWithRoleAll(String roleImportId, String netIdentifier = null)`
Ci uzivatel drzi procesnu rolu s danym importId.

### `najnovsiCase(String netIdentifier)`
Case danej siete, ktory plati - z NAJNOVSEJ verzie siete a z nej ten

### `hasProcessRole(IUser user, String roleImportId, String netIdentifier = null)`

### `usersWithRole(Object source, String roleImportId, String netIdentifier = null)`
Prienik: z uzivatelov v `source` vrati tych, ktori drzia rolu `roleImportId`.

### `createNewUser(String name, String surname, String email, String password)`

### `createNewUser(String name, String surname, String email, String password, List<String> authorities)`
Vytvori uzivatela aj so systemovymi authorities. Vrati vytvoreneho IUser.

### `setProcessRole(IUser user, String roleImportId, String netIdentifier, String version, boolean assign)`
Pridel alebo odober procesnu rolu. Tenky adapter nad enginovym

### `setProcessRole(String userId, String roleImportId, String netIdentifier, String version, boolean assign)`
Varianta podla ID uctu - a je to tá, ktorú treba volať.

### `changeUserPassword(String userId, String newPassword)`
Zmena hesla podla ID uctu.

### `pozvi(String email)`
Pozvanka e-mailom: ucet vznikne v stave INVITED a clovek si z odkazu

### `processRoleOptions()`
Roly vsetkych aplikacnych sieti v instancii, ako mapa

### `processRoleOptions(String netIdentifier, String version = null)`
Roly JEDNEHO procesu, ako mapa importId -> "Nazov roly".

### `processOptions()`
Procesy (aplikacne siete) instancie, ako mapa identifikator -> "Nazov".

### `processVersionOptions(String netIdentifier)`
Volba "vsetky verzie" v `processVersionOptions`. */

### `userOptions()`
Pouzivatelia instancie, ako mapa id -> "Meno Priezvisko (e-mail)".

### `isRealUser(IUser user)`
Je to ucet cloveka, alebo sluzobny ucet enginu?

### `formPassword(Object value)`
Heslo tak, ako ho poslal FORMULAR - teda dekoduje base64.

### `authorityOptions()`
Systemove authorities instancie, ako mapa nazov -> popis.

### `userSnapshot(String userId)`
Aktualny stav uctu, na predvyplnenie formulara pri uprave.

### `updateUserProfile(String userId, String name, String surname)`
Zmena mena a priezviska existujuceho uctu.

### `setUserAuthorities(String userId, List<String> authorities)`
Nastavi systemove authorities uctu na presne tento zoznam.

### `callAIToolByConfig(Map params)`
`stringId` roly -> identifikator siete, pre vsetky aplikacne siete

### `precitajFakturu(Object priloha, String caseId = null)`
Precita fakturu z prilohy a vrati polia, ktore sa z nej dali vytiahnut.

### `ocrDostupne()`
Je OCR na tomto stroji k dispozicii? Siet to vie povedat cloveku skor,

### `notifikacieZapnute()`
Da sa posielat? Siet sa to pyta, aby o tom vedela napisat do priebehu

### `notifikuj(Object prijemcovia, String predmet, String telo)`
Posle notifikacny mail a vrati, kolkym prijemcom sa to podarilo.

### `emailyOf(Object co)`
E-mailove adresy z coho sa da: userList pole, jeho hodnota, zoznam id,

### `menaUzivatelov(Object co)`
Mena uzivatelov, "Meno Priezvisko" (alebo e-mail, ked meno chyba).

> **Pozor na `createOrUpdateMenuItem`.** Existuje dvakrát: tu (7–9 argumentov,
> funkčná update cesta cez `changeFilter`/`changeMenuItem`) a v enginu
> (11 argumentov, na update volá neexistujúce `updateFilter` a **padne**).
> Rozlišujú sa len aritou. Použi tú s 7 argumentmi. Funkčný príklad je
> v `etask-backend-starter/src/main/resources/petriNets/configuration_tiles.xml`.

## Engine `ActionDelegate`

169 unikátnych metód. Pretaženia sú zlúčené: uvedená je
**najdlhšia** varianta, počet ostatných je v zátvorke. Kratšie varianty
majú spravidla defaulty — presnú signatúru si over v jare.

### Case: zakladanie a hladanie

- `createCase(PetriNet, String, String, IUser, Locale)` → `Case`  _(+9 variantov)_
- `createCaseFilter(Object, String, List<String>, String, String, Object)` → `Case`  _(+4 varianty)_
- `findCase(Closure<Predicate>)` → `Case`
- `findCaseElastic(String)` → `Case`
- `findCases(Closure<Predicate>, Pageable)` → `List<Case>`  _(+1 varianta)_
- `findCasesElastic(String, Pageable)` → `List<Case>`

### Case: vlastnosti a data

- `change(Field)` → `Object`
- `changeCaseProperty(String)` → `Object`
- `changeFieldValidations(Field, Object)` → `void`
- `changeFieldValue(Field, Object)` → `void`
- `changeFilter(Case)` → `Object`
- `changeMenuItem(Case)` → `Object`
- `changeUser(String, String, Object)` → `Object`  _(+3 varianty)_
- `changeUserByEmail(String, String, Object)` → `Object`  _(+1 varianta)_
- `copyBehavior(Field, Transition)` → `Object`
- `makeDataSetIntoChangedFields(Map<String, Map<String, String>>, Case, Task)` → `Map<String, ChangedField>`
- `setData(String, Case, Map)` → `SetDataEventOutcome`  _(+3 varianty)_
- `setDataWithPropagation(String, Case, Map)` → `SetDataEventOutcome`  _(+2 varianty)_

### Task: priradenie a vykonanie

- `assignTask(String, Case, IUser)` → `Task`  _(+4 varianty)_
- `assignTasks(List<Task>, IUser)` → `void`  _(+1 varianta)_
- `cancelTask(String, Case, IUser)` → `Task`  _(+4 varianty)_
- `cancelTasks(List<Task>, IUser)` → `void`  _(+1 varianta)_
- `execute(String)` → `Object`  _(+1 varianta)_
- `executeTask(String, Map)` → `void`
- `executeTasks(Map, String, Closure<Predicate>)` → `void`
- `findTask(Closure<Predicate>)` → `Task`  _(+1 varianta)_
- `findTasks(Closure<Predicate>, Pageable)` → `List<Task>`  _(+1 varianta)_
- `finishTask(String, Case, IUser)` → `void`  _(+4 varianty)_
- `finishTasks(List<Task>, IUser)` → `void`  _(+1 varianta)_
- `getTaskId(String, Case)` → `String`  _(+1 varianta)_

### Uzivatelia a role

- `assignRole(String, String, Version, IUser)` → `IUser`  _(+7 variantov)_
- `deleteUser(String)` → `void`  _(+1 varianta)_
- `findUserByEmail(String)` → `IUser`
- `findUserById(String)` → `IUser`
- `inviteUser(NewUserRequest)` → `MessageResource`  _(+1 varianta)_
- `loggedUser()` → `IUser`
- `removeRole(String, String, Version, IUser)` → `IUser`  _(+7 variantov)_

### Filtre a menu

- `createFilter(Object, String, String, List<String>, String, String, Object)` → `Case`  _(+1 varianta)_
- `createFilterInMenu(String, String, Object, String, String, List<String>, String, Map<String, String>, Map<String, String>, List<String>, String, String)` → `Case`  _(+11 variantov)_
- `createMenuItem(String, String, String, String, String, List<String>, Map<String, String>, Map<String, String>, Case, List<String>)` → `Case`  _(+17 variantov)_
- `createOrUpdateCaseMenuItem(String, String, String, String, String, List<String>, Map<String, String>, Map<String, String>, Case, List<String>)` → `Case`  _(+4 varianty)_
- `createOrUpdateMenuItem(String, String, String, String, String, String, List<String>, Map<String, String>, Map<String, String>, Case, List<String>)` → `Case`  _(+4 varianty)_ ⚠️ **prekryté v projekte**
- `createOrUpdateTaskMenuItem(String, String, String, String, String, List<String>, Map<String, String>, Map<String, String>, Case, List<String>)` → `Case`  _(+4 varianty)_
- `createTaskFilter(Object, String, List<String>, String, String, Object)` → `Case`  _(+4 varianty)_
- `createTaskMenuItem(String, String, String, String, String, List<String>, Map<String, String>, Case, List<String>)` → `Map<String, Case>`  _(+2 varianty)_
- `deleteFilter(Case)` → `Object`
- `deleteMenuItem(Case)` → `Object`
- `exportCases(List<CaseSearchRequest>, File, ExportDataConfig, LoggedUser, int, Locale, Boolean)` → `OutputStream`  _(+8 variantov)_
- `exportCasesToFile(List<CaseSearchRequest>, String, ExportDataConfig, LoggedUser, int, Locale, Boolean)` → `File`  _(+8 variantov)_
- `exportFilters(Collection<String>)` → `FileFieldValue`
- `exportTasks(List<ElasticTaskSearchRequest>, File, ExportDataConfig, LoggedUser, int, Locale, Boolean)` → `OutputStream`  _(+8 variantov)_
- `exportTasksToFile(List<ElasticTaskSearchRequest>, String, ExportDataConfig, LoggedUser, int, Locale, Boolean)` → `File`  _(+7 variantov)_
- `findAllFilters()` → `List<Case>`
- `findDefaultFilters()` → `List<Case>`
- `findFilter(String)` → `Case`
- `findFilters(String)` → `List<Case>`
- `findMenuItem(String, String, String)` → `Case`  _(+2 varianty)_
- `findMenuItemInGroup(String, String, Case)` → `Case`
- `getFilterFromMenuItem(Case)` → `Case`
- `importFilters()` → `List<String>`

### URI uzly (bocne menu)

- `createUri(String, UriContentType)` → `Object`
- `getUri(String)` → `Object`
- `moveUri(String, String)` → `Object`

### Subory a dokumenty

- `generate(String, Closure)` → `Object`
- `generatePDF(Transition, FileField, Case, Case, Transition, String, List<String>, Locale, ZoneId, Integer, Integer)` → `void`  _(+20 variantov)_
- `generatePdf(Transition, FileField, Case, Case, Transition, String, List<String>, Locale, ZoneId, Integer, Integer)` → `void`  _(+25 variantov)_
- `generatePdfWithLocale(String, String, Locale, Case, Case)` → `void`  _(+2 varianty)_
- `generatePdfWithTemplate(String, String, String, Case, Case)` → `void`  _(+2 varianty)_
- `generatePdfWithZoneId(String, String, ZoneId, Case, Case)` → `void`  _(+3 varianty)_
- `saveChangedAllowedNets(CaseField)` → `Object`
- `saveChangedChoices(ChoiceField)` → `Object`
- `saveChangedOptions(MapOptionsField)` → `Object`
- `saveChangedValidation(Field)` → `Object`
- `saveChangedValue(Field)` → `Object`
- `saveFieldBehavior(Field, Transition, Set<FieldBehavior>)` → `Object`
- `saveFileToField(Case, String, String, String, String)` → `void`  _(+1 varianta)_

### Mail a notifikacie

- `sendEmail(List<String>, String, String, Map<String, File>)` → `void`  _(+1 varianta)_
- `sendMail(MailDraft)` → `void`

### Validacie

- `dynamicValidation(String, I18nString)` → `DynamicValidation`
- `validation(String, I18nString)` → `Validation`

### Cache

- `cache(String, Object)` → `Object`  _(+1 varianta)_
- `cacheFree(String)` → `Object`

### Ostatne

- `get(String)` → `Object`
- `getALWAYS_GENERATE()` → `String`
- `getAction()` → `Action`
- `getActionsRunner()` → `FieldActionsRunner`
- `getAlways()` → `Object`
- `getAsync()` → `AsyncRunner`
- `getByCity()` → `Object`
- `getByCode()` → `Object`
- `getByIco()` → `Object`
- `getClose()` → `Object`
- `getConfigurableMenuService()` → `IConfigurableMenuService`
- `getData(String, Case)` → `Map<String, Field>`  _(+3 varianty)_
- `getEditable()` → `Object`
- `getExportConfiguration()` → `ExportConfiguration`
- `getExportService()` → `IExportService`
- `getFileFieldStream(Case, Task, FileField, boolean)` → `FileFieldInputStream`  _(+1 varianta)_
- `getForbidden()` → `Object`
- `getHidden()` → `Object`
- `getHistoryService()` → `IHistoryService`
- `getImpersonationService()` → `IImpersonationService`
- `getInit()` → `Object`
- `getInitValueExpressionEvaluator()` → `IInitValueExpressionEvaluator`
- `getInitValueOfField()` → `Object`
- `getInitial()` → `Object`
- `getLog()` → `Logger`
- `getMap()` → `Object`
- `getMenuImportExportService()` → `IMenuImportExportService`
- `getONCE_GENERATE()` → `String`
- `getOnce()` → `Object`
- `getOptional()` → `Object`
- `getOutcomes()` → `List<EventOutcome>`
- `getPdfGenerator()` → `IPdfGenerator`
- `getPublicViewProperties()` → `PublicViewProperties`
- `getRegistrationService()` → `IRegistrationService`
- `getRequired()` → `Object`
- `getScheduler()` → `Scheduler`
- `getTRANSITIONS()` → `String`
- `getTask()` → `Optional<Task>`
- `getTransitions()` → `Object`
- `getUNCHANGED_VALUE()` → `String`
- `getUnchanged()` → `Object`
- `getUseCase()` → `Case`
- `getVisible()` → `Object`
- `i18n(String, Map<String, String>)` → `I18nString`
- `init(Action, Case, Optional<Task>, FieldActionsRunner)` → `Object`  _(+1 varianta)_
- `initFieldsMap(Map<String, String>)` → `Object`
- `initTransitionsMap(Map<String, String>)` → `Object`
- `make(List<Field>, Closure)` → `Object`  _(+1 varianta)_
- `makeUrl(String, String)` → `String`  _(+1 varianta)_
- `orsr(Closure, String)` → `Object`
- `psc(Closure, String)` → `Object`
- `searchCases(Closure<Predicate>)` → `List<String>`
- `set(String, Object)` → `void`
- `setAction(Action)` → `void`
- `setActionsRunner(FieldActionsRunner)` → `void`
- `setAlways(Object)` → `void`
- `setAsync(AsyncRunner)` → `void`
- `setByCity(Object)` → `void`
- `setByCode(Object)` → `void`
- `setByIco(Object)` → `void`
- `setClose(Object)` → `void`
- `setConfigurableMenuService(IConfigurableMenuService)` → `void`
- `setEditable(Object)` → `void`
- `setExportConfiguration(ExportConfiguration)` → `void`
- `setExportService(IExportService)` → `void`
- `setForbidden(Object)` → `void`
- `setHidden(Object)` → `void`
- `setHistoryService(IHistoryService)` → `void`
- `setImpersonationService(IImpersonationService)` → `void`
- `setInitValueExpressionEvaluator(IInitValueExpressionEvaluator)` → `void`
- `setInitValueOfField(Object)` → `void`
- `setInitial(Object)` → `void`
- `setMap(Object)` → `void`
- `setMenuImportExportService(IMenuImportExportService)` → `void`
- `setOnce(Object)` → `void`
- `setOptional(Object)` → `void`
- `setOutcomes(List<EventOutcome>)` → `void`
- `setPdfGenerator(IPdfGenerator)` → `void`
- `setPublicViewProperties(PublicViewProperties)` → `void`
- `setRegistrationService(IRegistrationService)` → `void`
- `setRequired(Object)` → `void`
- `setScheduler(Scheduler)` → `void`
- `setTask(Optional<Task>)` → `void`
- `setTransitions(Object)` → `void`
- `setUnchanged(Object)` → `void`
- `setUseCase(Case)` → `void`
- `setVisible(Object)` → `void`

