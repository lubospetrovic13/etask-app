# Chyby enginu a knižnice — kopa na opravu upstream

Toto je **prvá z dvoch kôp**. Sú tu veci, ktoré nie sú „takto to funguje, treba
to vedieť", ale **defekty**: engine alebo `@netgrif/components` sa správa inak,
než sľubuje vlastný model, a skoro vždy o tom mlčí. Druhá kopa — správanie,
ktoré je v poriadku a treba ho len poznať — je v `PETRIFLOW_LEARNINGS.md`,
`RUNBOOK.md` a `docs/reference/cheatsheet.md`.

Rozdelenie má praktický dôvod. Znalosť z druhej kopy je trvalá a patrí do
dokumentácie. Znalosť z tejto kopy je **odpisujúce sa aktívum**: každý riadok
tu prestane platiť v momente, keď sa tá vec opraví — a to je aj cieľ. Kým sa
tak nestane, každý z nich stojí každého, kto na platforme stavia, aspoň jedno
ladenie, a väčšinu z nich nezachytí ani build, ani import, ani log.

Verzia, na ktorej je to merané: **application-engine 6.3.1**,
**@netgrif/components 6.3.x**. Každý záznam má tvar
**príznak → príčina → dôkaz → obídenie → návrh opravy**.

Zoradené podľa toho, koľko to stojí toho, kto na to narazí.

---

## E1. `removeRole` z akcie procesnú rolu neodoberie a mlčí

**Príznak.** Akcia zavolá `removeRole(...)`, dostane návratovú hodnotu, `finish`
vráti `success`, v logu nič — a rola je na účte ďalej.

**Príčina.** `AbstractUserService` si rolu vytiahne podľa **importId**, hoci
parameter je **stringId**:

```java
@Override
public IUser addRole(IUser user, String roleStringId) {
    ProcessRole role = processRoleService.findById(roleStringId);      // správne
    ...
}

@Deprecated(since = "6.2.0")
@Override
public IUser removeRole(IUser user, String roleStringId) {
    return removeRole(user, processRoleService.findByImportId(roleStringId));
    //                                        ^^^^^^^^^^^^^^ podľa importId
}
```

Podľa `stringId` teda `findByImportId` nenájde nič, `user.removeProcessRole(null)`
neodoberie nič a `save` uloží nezmenený dokument. Do tejto metódy vedú **všetky**
varianty `ActionDelegate.removeRole(...)`, takže z Petriflow akcie sa rola
v 6.3.1 odobrať nedá vôbec.

Druhá polovica: keby jej niekto dal `importId`, `findByImportId` vracia *prvú*
rolu s tým importId spomedzi všetkých sietí a verzií — čiže náhodnú.

**Dôkaz.** Akcia nahlásila „odobraná rola" a rola tam po nej bola. Regresia je
v `tools/pucheck.py`.

**Obídenie.** Odobrať rolu priamo; objekt `ProcessRole` je zo siete dostupný:

```groovy
IUser fresh = userService.findById(userId, false)
fresh.removeProcessRole(role)
userService.save(fresh)
```

Cena: chránená varianta popri uložení obnovuje aj security context, toto nie —
prihlásená session si odobranú rolu podrží do odhlásenia.

**Návrh opravy.** `findById` namiesto `findByImportId`, alebo parameter
premenovať a metódu zosúladiť s `addRole`. Je označená `@Deprecated`, ale
`ActionDelegate` ju stále používa — buď opraviť ju, alebo prepnúť delegáta na
`removeRole(IUser, ProcessRole)`.

---

## E2. Zobrazenie typu Task obchádza vlastné komponenty aplikácie

**Príznak.** V zobrazení typu `Task` sa nevykreslia vlastné field komponenty
aplikácie a neplatia providery, ktoré si aplikácia vešia na vlastný task panel.
V zobrazení typu `Case` to isté funguje.

**Príčina.** Zobrazenie typu Task inštancuje knižnica sama a použije knižničný
`nc-task-panel` a `nc-field-component-resolver`. Aplikácia nemá kam vstúpiť —
nejde o jej šablónu, takže sa to nedá prebiť ani prepísaním vlastnej.

**Dôkaz.** Namerané v DOM, tá istá appka, dve zobrazenia:

| | Task zobrazenie | Case zobrazenie |
|---|---|---|
| `nc-task-panel` | **1** | 0 |
| `app-etask-task-panel` | 0 | **1** |
| `nc-field-component-resolver` | **20** | 0 |
| `nc-button-field` | **3** | 0 |

**Obídenie.** Zatiaľ žiadne čisté. Nepoužívať Task zobrazenia tam, kde appka má
vlastné komponenty.

**Návrh opravy.** Nechať Task zobrazenie prevziať `panelContentComponent`
rovnako, ako to už vie `nc-task-list` cez `@Input` — teda dať aplikácii jedno
miesto, kde povie, ktorý panel sa má použiť, a rešpektovať to vo všetkých
typoch zobrazení.

**Prečo je to drahé.** Je to tá istá chyba ako „`nc-task-list` obchádza vlastné
komponenty" (v tomto repozitári najdrahšia chyba histórie frontendu), len
inými dverami. Statická kontrola `pfview` ju nezachytí, lebo nemá čo označiť.

---

## E3. ~~`title` udalosti sa nedostane ku klientovi~~ — STAŽENÉ, bolo to nesprávne

**Toto nie je chyba enginu.** Zapísal som to ako chybu a bolo to zmerané zle;
nechávam to tu ako stiahnutý záznam, nie ako prázdne miesto, aby sa tvrdenie
nedalo znova prevziať z niečoho, čo naň medzitým odkazuje.

**Ako to skončilo v katalógu.** Zmeral som payload tasku, nenašiel v ňom
o udalostiach nič a z tej **absencie** som usúdil, že API titulky neposiela.
Sieť, na ktorej som to meral, ale žiadny titulok udalosti nedefinovala —
a Jackson `null` položky vynecháva. Meral som teda vlastný prázdny vstup.

**Ako to je.** Funguje to celé, vrátane prekladu. Namerané na 6.3.1 na sieti,
ktorá definuje všetky štyri udalosti:

| kľúč v payloade tasku | `Accept-Language: sk` | `Accept-Language: en` |
|---|---|---|
| `title` | `Vyplňte` | `Fill it in` |
| `assignTitle` | `Prevziať` | `Take` |
| `cancelTitle` | `Vrátiť` | `Give back` |
| `finishTitle` | `Podať` | `Submit` |
| `delegateTitle` | `''` | `''` |

Knižnica ich číta a pri chýbajúcom titulku padne na globálny kľúč:

```js
getFinishTitle() {
    return (task.finishTitle === '' || task.finishTitle)
        ? task.finishTitle : 'tasks.view.finish';
}
canFinish() { return this._permissionService.canFinish(task) && this.getFinishTitle() !== ''; }
```

Z čoho vyplýva druhá polovica, ktorá nie je nikde napísaná: **prázdny titulok
tlačidlo skryje.** `<title></title>` na udalosti je teda spôsob, ako z panela
odobrať `delegate` alebo `cancel` bez zásahu do oprávnení. Jediná výnimka je
`canReassign()`, ktorý titulok nekontroluje.

Ako sa to píše, je v `PETRIFLOW_LEARNINGS.md` B23.

**Čo si z toho odniesť.** Absencia kľúča v JSON payloade nie je dôkaz, že ho
server nikdy neposiela — je to dôkaz, že ho neposlal pre **tento** vstup.
Merať treba na vstupe, ktorý tú vlastnosť naozaj používa.

---

## E4. `change <pole> options { }` v `create` udalosti prípadu sa neuchová

**Príznak.** Na čerstvo založenom prípade sú `options` toho poľa prázdne. Zápis
hodnoty do neho potom zlyhá na HTTP 500 s „Could not parse value of field".

**Príčina.** Zápis možností počas zakladania prípadu sa stratí. Nevidno to,
lebo tá istá akcia býva aj v `assign` udalosti a kto úlohu otvorí, si ju
priradí — takže sa možnosti doplnia. Praskne to až vtedy, keď hodnotu zapíše
niekto zvonka cez `setData` z akcie inej siete: to úlohu nepriraďuje, `assign`
nebeží a hodnota ide do poľa bez možností.

**Dôkaz.** Prípad založený cez `POST /api/workflow/case` má po `create` akcii,
ktorá možnosti nastavuje, `options: {}`.

**Obídenie.** Nastavovať možnosti tam, kde sa zapisuje hodnota.

**Návrh opravy.** Buď zmeny z `create` udalosti ukladať, alebo aspoň nahlásiť,
že sa zahadzujú.

---

## E5. `immediate` na `multichoice_map` s runtime možnosťami zhodí indexáciu

**Príznak.** Prípad sa uloží, ale **neindexuje** — v zoznamoch nie je a Elastic
dopyt ho nenájde.

**Príčina.**

```
ERROR WorkflowService : Indexing failed [<caseId>]
java.lang.NullPointerException
  at ElasticCaseMappingService.collectTranslations(ElasticCaseMappingService.java:182)
  at ElasticCaseMappingService.transformMultichoiceMapField(...)
```

Mapper očakáva na možnostiach preklady, ktoré možnosti nastavené za behu
(`change ... options`) nemajú.

**Obídenie.** Nedávať `immediate` na `multichoice_map` s dynamickými možnosťami.

**Návrh opravy.** Ošetriť chýbajúci preklad v `collectTranslations`; hodnota bez
prekladu je legitímna.

---

## E6. `createOrUpdateMenuItem` na update ceste padne a `deleteMenuItem` nechá osirelý filter

**Príznak.** Zmena existujúcej položky menu skončí na
`MissingMethodException: updateFilter()`.

**Príčina.** `updateFilter` **existuje** — ale je `private`:

```groovy
// ActionDelegate.groovy
private void updateFilter(Case filter, Map dataSet) {          // :1884
    setData(DefaultFiltersRunner.DETAILS_TRANSITION, filter, dataSet)
}
private void updateMenuItemRoles(Case item, Closure cl, String roleFieldId) { … }  // :1648
```

Uzávery v `changeFilter` a `changeMenuItem` ich volajú **dynamicky**, takže sa
volanie rieši cez metaclass inštancie. A tou inštanciou je podtrieda aplikácie
(`EtaskActionDelegate`), ktorá privátne metódy predka nevystavuje:

```
groovy.lang.MissingMethodException: No signature of method:
com.netgrif.etask.EtaskActionDelegate.updateFilter() is applicable
for argument types: (Case, LinkedHashMap)
```

Čo to znamená: **`changeFilter` a `changeMenuItem` fungujú len vtedy, keď si
nikto `ActionDelegate` nerozšíri** — a rozšírenie delegáta je dokumentovaný
spôsob, ako pridať vlastné akcie. Týka sa to teda každej aplikácie. Zasiahnuté
sú `query`, `visibility`, `allowedNets`, `filterMetadata` a `allowedRoles` /
`bannedRoles`; `title`, `icon` a `uri` privátnu metódu nevolajú a prejdú.

Prejaví sa to až pri **druhom** importe: prvý ide create cestou (položka
neexistuje), druhý vráti HTTP 500.

Druhá polovica: `deleteMenuItem` maže položku a jej `filter` case nechá.
Po niekoľkých behoch ich je v databáze hromada a `getFilterFromMenuItem` potom
vracia nesprávny.

**Obídenie.** Dve možnosti. Vo vlastnej metóde delegáta zapísať priamo —
`setData("t2", filter, [...])` je presne to, čo `updateFilter` robí, a `setData`
je verejné; tak to má `EtaskActionDelegate.createOrUpdateMenuItem`. Kde to nie
je vlastná metóda (napr. `createFilterInMenu`), položku zahodiť a postaviť
znova, v poradí `deleteMenuItem` → `deleteFilter` (naopak padne — `deleteMenuItem`
si filter ešte raz načíta podľa id na položke).

**Návrh opravy.** Zmeniť `private` na `protected` — jeden riadok na dvoch
metódach. Alebo uzávery neriešiť dynamicky. A `deleteMenuItem` nech maže aj
filter.

---

## E7. Uzol URI prežije zmazanie sietí a nemá REST na odstránenie

**Príznak.** Po odstránení appky zostane v menu karta, ktorá vedie do prázdna.
Dôvod sa nedá nájsť ani v manifeste, ani v Mongu.

**Príčina.** Uzol URI je samostatný dokument v **Elasticsearchi** (`etask_uri`),
nie v Mongu, a nikde sa negeneruje znova. Zmazanie sietí ho neodstráni
a endpoint na jeho zmazanie neexistuje.

**Obídenie.** Ručne cez Elastic — vyhodiť z `childrenId` koreňa a zmazať
dokument (recept je v `RUNBOOK.md`, časť 2).

**Návrh opravy.** Zmazať uzol spolu s poslednou sieťou, ktorá naň ukazuje,
alebo pridať `DELETE /api/v2/uri/{id}`.

---

## E8. Odmietnuté `finish` zmaže súrodenecké úlohy a už ich neobnoví

**Príznak.** Používateľ dostane chybu z validácie, klikne preč — a read-only
pohľad, ktorý visel na tom istom mieste, je nenávratne preč.

**Príčina.** Odmietnuté `finish` zmaže ostatné úlohy, ktoré povoľuje vstupné
miesto toho prechodu, a pri vrátení tokenu ich neobnoví.

**Obídenie.** Read-only pohľad vešať len na read arc zo **sinku**, alebo ho
nemať samostatný. Zdokumentované ako B8b.

**Návrh opravy.** Pri návrate tokenu obnoviť úlohy, ktoré boli zmazané.

---

## E9. Textové pole s komponentom `password` posiela base64 a nikto to nedekóduje

**Príznak.** Účet založený cez formulár sa nedá prihlásiť tým heslom, ktoré
človek napísal. Prihlási sa base64 podobou.

**Príčina.** Frontend hodnotu pred odoslaním zakóduje:

```js
// FieldConverterService.formatValueForBackend
if (resolveType(field) === TEXT && field.component.name === 'password') {
    return encodeBase64(value);
}
```

Na strane servera tomu nezodpovedá nič. Kto to nevie, zahashuje base64.

**Obídenie.** Dekódovať v akcii. Rozhodnúť „je to base64?" podľa obsahu nejde —
`password` je platný base64 reťazec — takže to musí byť pravidlo, nie hádanie.

**Návrh opravy.** Buď kódovanie zrušiť (nič nechráni, HTTPS to rieši), alebo ho
symetricky dekódovať na serveri, alebo to aspoň napísať do dokumentácie
komponentu.

---

## E10. `GET /api/task/case/{id}` neoveruje oprávnenia

**Príznak.** Kto pozná id prípadu, prečíta jeho úlohy bez ohľadu na `view`.

**Príčina.** Filtrovanie podľa oprávnení robí `POST /api/task/search`
a `/assign`; priame GET podľa id nie.

**Dôkaz.** Overené na dvoch nesúvisiacich appkách účtom bez akejkoľvek roly:
HTTP 200 v oboch prípadoch. Je to teda vlastnosť HTTP vrstvy, nie konkrétnej
siete. V UI to vidno nie je, lebo zoznamy stavajú na `/search`.

**Návrh opravy.** Overovať `view` aj na priamom GET.

---

## E11. Import siete vracia pri chybe holé `{"status":500}`

**Príznak.** Import zlyhá a odpoveď neobsahuje dôvod. Ten je len v logu servera.

**Obídenie.** `tools/pfcheck.sh` dôvod vytiahne z logu.

**Návrh opravy.** Vrátiť správu z výnimky.

---

## E12. `GET /api/auth/login` vracia 405, hoci prihlásenie prebehne

**Príznak.** Klient dostane 405 Method Not Allowed a pritom **token je
v hlavičke** — autentifikačný filter beží pred handlerom.

**Obídenie.** Čítať `X-Auth-Token` aj z chybovej odpovede.

**Návrh opravy.** Namapovať GET, alebo vracať 200.

---

## E13. Sieť s diakritikou v `<title>` sa naimportuje, ale jej XML sa neuloží

**Príznak.** `GET /api/petrinet/{id}/file` vracia navždy 500 a nástroje na
porovnanie so zdrojom (`pfsync`) sieť nikdy neprečítajú.

**Príčina.** Beží pri JVM bez `-Dsun.jnu.encoding=UTF-8`: sieť sa uloží do
Mongu, ale súbor do `storage/uploadedModels` sa nezapíše. Navyše Tomcat
odmietne dať diakritiku do hlavičky:

```
java.lang.IllegalArgumentException: The Unicode character [ž] at code point
[382] cannot be encoded as it is outside the permitted range of 0 to 255
```

**Obídenie.** Spúšťať JVM s `-Dfile.encoding=UTF-8 -Dsun.jnu.encoding=UTF-8`
(`tools/up.sh` to robí) a sieť re-importovať.

**Návrh opravy.** Názov súboru neskladať z titulku, alebo ho normalizovať.
`Content-Disposition` kódovať podľa RFC 5987.

---

## E14. `PdfRunner` asserts na relatívne cesty a zhodí štart

**Príznak.** Aplikácia nenaskočí, hoci siete sa naimportovali — log vyzerá
polovične úspešne.

```
PowerAssertionError: assert resource.fontTitleResource.exists()
  URL [file:src/main/resources/pdfGenerator/fonts/Roboto-Light.ttf]
```

**Príčina.** Cesty sú relatívne k pracovnému adresáru, nie ku classpath.

**Obídenie.** Spúšťať jar z adresára modulu.

**Návrh opravy.** Čítať z classpath, alebo neasertovať pri štarte.

---

## E15. `<i18n locale="en-US">` sa naimportuje a nikdy sa nepoužije

**Príznak.** Preklady sú v XML, import prejde bez slova — a appka ich nezobrazí.
Ten istý súbor s `locale="en"` funguje.

**Príčina.** Importer uloží kľúč **verbatim** z atribútu:

```java
protected void addTranslation(I18NStringType i18NStringType, String locale) {
    translation.addTranslation(locale, i18NStringType.getValue());   // "en-US"
}
```

Vyhľadanie ide vždy cez `Locale`, teda cez **dvojpísmenový** jazyk:

```java
public String getTranslation(Locale locale) {
    return getTranslation(locale.getLanguage());                     // "en"
}
```

`en-US` sa teda nemá ako trafiť. XSD atribút nijako neomedzuje, importer
nekontroluje nič a v logu nie je nič.

**Dôkaz.** Sieť s oboma blokmi naraz — `locale="en"` s hodnotou `Your name`
a `locale="en-US"` s hodnotou `FULL LOCALE en-US` na tom istom kľúči. Na
`Accept-Language: en-US` vrátil engine `Your name`. Blok `en-US` je mŕtvy kód.

**Obídenie.** Písať v `<i18n>` len dvojpísmenový kód: `sk`, `en`, `de`.

**Návrh opravy.** Kľúč pri importe normalizovať na `Locale.forLanguageTag(...)
.getLanguage()`, alebo pri neznámom tvare odmietnuť import.

---

## E16. Knižnica zahodí preklad názvu zobrazenia v ľavom menu

**Príznak.** Položka menu je založená ako `I18nString` s prekladmi, payload ich
naozaj nesie — a v menu je stále jazyk, v ktorom položka vznikla.

**Príčina.** Rozhodnutie je na klientovi (server túto hodnotu nelokalizuje) a
klient si vyberie `defaultValue`:

```js
// AbstractNavigationDoubleDrawerComponent.resolveFilterCaseToViewNavigationItem
title: filter.immediateData.find(f => f.stringId === 'entry_name')?.value?.defaultValue
       || filter.title
```

`entry_name` na `preference_filter_item` je typu `enumeration`, takže jeho
hodnota **je** `I18nString` a preklady sú k dispozícii — knižnica ich len
nepoužije.

**Dôkaz.** Namerané na 6.3.1, `POST /api/workflow/case/search` nad
`preference_filter_item`, s `Accept-Language: sk` aj `en` rovnako:

```json
"entry_name": {"defaultValue": "Tikety", "translations": {"en": "Tickets"}}
```

**Obídenie.** Prebiť `resolveFilterCaseToViewNavigationItem` a vybrať preklad
podľa aktuálneho jazyka (`view-title.ts` v tomto repozitári). Pozor: kaskáda
`translations[lang] → defaultValue → filter.title` musí zostať, inak položka
založená obyčajným reťazcom zmizne.

**Návrh opravy.** Vybrať `translations[currentLang]`, keď existuje. Kaskáda
ostáva rovnaká, takže je to spätne kompatibilné.

---

## E17. Nabídka stĺpcov sa pri zmene jazyka neobnoví

**Príznak.** Portál sa prepne do angličtiny, ale hlavičky stĺpcov postavené
z dátových polí zostanú v pôvodnom jazyku. Po načítaní stránky sú správne.

**Príčina.** `AbstractHeaderService` si `fieldsGroup` — nabídku stĺpcov
odvodenú z polí povolených sietí — načíta raz a drží. Preklad prichádza zo
servera podľa `Accept-Language`, takže po prepnutí by stačilo znova sa spýtať,
ale servis na to nemá verejné miesto: `initializeHeaderState` a
`initializeDefaultHeaderState` pracujú nad už načítaným `fieldsGroup`.

**Dôkaz.** Namerané na zobrazení dovoleniek: po prepnutí `Stav | Dátum od |
Dátum do`, po reloade `Status | Date from | Date to`. Meta stĺpec `Názov` ↔
`Title` sa pritom prepne hneď — ten ide cez `translate` pipe.

**Obídenie.** Načítať stránku. `location.reload()` z prepínača by to vyriešilo
jednou riadkou, ale zahodí rozpísaný formulár v otvorenej úlohe, takže sa to
nerobí.

**Návrh opravy.** Buď verejná metóda, ktorá nabídku znova načíta, alebo
odber `LanguageService.getLangChange$()` v samotnom servise — rovnako, ako to
musí robiť každý komponent, ktorý drží preložený reťazec.

---

## E18. Výnimka z akcie v udalosti `assign` vráti holé HTTP 500 bez dôvodu

**Príznak.** Akcia v `<event type="assign"><actions phase="pre">` odmietne
priradenie úlohy vyhodením výnimky — správne — ale klient dostane

```json
{"timestamp":1788969468781,"status":500,"error":"Internal Server Error",
 "path":"/api/task/assign/6aa181fc9a68db34ef289fd4"}
```

Text výnimky sa v odpovedi **neobjaví nikde**. Používateľ vidí „Internal Server
Error" namiesto vety, ktorá mu povie, prečo si tú úlohu prevziať nemôže.

**Príčina.** `finish` má pre odmietnutie z akcie vlastnú cestu — vráti HTTP 200
a dôvod v tele ako `error`. `assign` takú cestu nemá, takže výnimka prepadne
až na default error handler Springu, ktorý telo výnimky nezverejňuje.

**Dôkaz.** Zmerané na `schvalovanie/fa_faktura` v1.0.0, kontrola štyroch očí
(`nie_vlastnu`): tá istá výnimka z tej istej process funkcie vrátila z `assign`
holé 500 (vyššie) a z `finish`

```json
{"error":"Faktúru, ktorú ste zapísali, nemôžete schváliť ako schvaľovateľ
 strediska. Nech ju schváli niekto iný."}
```

Token sa v oboch prípadoch nepohol a úloha zostala, takže **ochrana funguje** —
nefunguje len jej vysvetlenie.

**Obídenie.** Kontrolu dať do `finish`, nie do `assign` (tak to robí
`fa_faktura` aj `ob_objednavka`). Cena za to je, že úlohu si zablokovaný
používateľ **prevzať vie** a kým ju drží, nemá ju kto vykonať; pustí ju
`cancel` — ktorý sa preto nesmie zakazovať — alebo `ROLE_ADMIN`.

**Návrh opravy.** Spracovať výnimku z akcie v `assign` rovnako ako vo `finish`:
HTTP 200 a `error` s textom výnimky.

---

## E19. Nahranie súboru s neúplným telom vráti HTTP 200 a nenahrá nič

**Príznak.** `POST /api/task/{id}/file/{fieldId}` s multipart telom, v ktorom
časť `data` nie je mapa `{taskId: fieldId}` (napríklad prázdny objekt `{}`),
vráti **HTTP 200 s telom `{}`**. Súbor sa neuloží, hodnota poľa zostane prázdna
a klient nemá z čoho zistiť, že sa nič nestalo.

**Príčina.** V logu servera je `NullPointerException` v
`TaskService.getMainOutcome` (volané z `AbstractTaskController.saveFile`) —
výnimka sa zaloguje ako ERROR, ale odpoveď sa zloží z prázdneho outcome
a odošle sa ako úspech.

**Dôkaz.** Namerané pri písaní `tools/sccheck.py` proti 6.3.1: s `data` = `{}`
odpoveď `HTTP 200 {}` a v logu NPE; s `data` = `{"<taskId>": "<fieldId>"}`
odpoveď `HTTP 200 {"success": "Data field values have been successfully set"}`
a súbor v storage. Test najprv „prešiel“ a až čítanie prílohy odhalilo,
že príloha tam nie je.

**Obídenie.** Posielať `data` tak, ako to robí knižnica
(`{taskId: fieldId}`), a po nahraní si hodnotu poľa prečítať.

**Návrh opravy.** Pri chýbajúcom outcome vrátiť 400 s dôvodom; NPE nikdy
neposielať ako 200.

---

## E20. Redis sa nedá nastaviť štandardným `spring.redis.*`

**Príznak.** Kontejner s `SPRING_REDIS_HOST=redis` (štandardné Spring Boot
property pre Redis) spadne pri štarte:

```
BeanCreationException: Error creating bean with name
  'enableRedisKeyspaceNotificationsInitializer'
Caused by: JedisConnectionException: Could not get a resource from the pool
Caused by: java.net.ConnectException: Connection refused
```

Redis pritom beží a je zdravý — appka sa pripája na `localhost`.

**Príčina.** Engine si `JedisConnectionFactory` stavia sám
(`configuration/SessionConfiguration`) a adresu čita cez

```java
@Value("${spring.session.redis.host}")
@Value("${spring.session.redis.port}")
```

`spring.session.redis.host` **nie je** Spring Boot property (Spring Session má
pod tým prefixom `namespace` a `flush-mode`, nie host), takže autokonfigurácia
ani relaxed binding zo `SPRING_REDIS_HOST` sa naň nedostane. Hodnotu musí
dodať `application.properties` — v tomto startere z `${REDIS_HOST:localhost}`.
Fallback `hostName == null ? "localhost"` v tej metóde navyše zaručí, že
nesprávna konfigurácia sa neprejaví ako chyba konfigurácie, ale ako odmietnuté
spojenie na localhost.

**Dôkaz.** Namerané pri prevode stacku do Dockera (6.3.1): s
`SPRING_REDIS_HOST=redis` padá vyššie uvedenou výnimkou, s `REDIS_HOST=redis`
nabehne. Ten istý omyl bol v `deploy/docker-compose.prod.yml`, takže čerstvé
produkčné nasadenie by nenabehlo vôbec.

**Obídenie.** Používať `REDIS_HOST` a `REDIS_PORT` (tak, ako ich čaká
`application.properties`), nie `SPRING_REDIS_*`.

**Návrh opravy.** Čítať štandardné `spring.redis.*` (alebo aspoň logovať, na
akú adresu sa engine pripája), a nemať v konfigurácii tichý fallback na
`localhost`.

---

## E21. Hľadanie procesov podľa `title` nenájde nikdy nič

`POST /api/petrinet/search` vyzerá, že názov procesu hľadať vie —
`PetriNetService.search` má práve tri kľúče, ktoré porovnáva regexom
namiesto rovnosti, a `title` je jeden z nich:

```java
else if (key.equalsIgnoreCase("title") || key.equalsIgnoreCase("initials") || key.equalsIgnoreCase("identifier"))
    valueCriteria = Criteria.where(key).regex((String) value, "i");
```

Lenže `PetriNet.title` **nie je reťazec**. V Mongu je to `I18nString`:

```json
{"defaultValue": "Nástup nového zamestnanca", "translations": {"en": "Employee onboarding"}}
```

Regex nad dokumentom sa nemá o čo oprieť, takže dopyt vráti prázdny zoznam —
HTTP 200, žiadna chyba, žiadny záznam v logu. Namerané:

```
{"identifier": "onboarding"}   -> 2 siete
{"initials": "NZM"}            -> 2 siete
{"title": "ástup"}             -> 0    (a "Nástup nového zamestnanca" existuje)
{"title.defaultValue": "Nástup nového zamestnanca"} -> 1
```

Posledný riadok je aj celé obídenie, aj jeho hranica: `title.defaultValue`
nájde sieť, ale ako **presnú zhodu** — kľúč nie je v tej trojici vyššie, takže
ide cez `Criteria.is()`. Hľadanie podreťazca v názve sa cez toto API napísať
nedá a preklad z `translations` sa nehľadá vôbec.

Oprava je jednoriadková: regexovať `title.defaultValue` (prípadne aj
`translations.*`) namiesto `title`.

Vedľajší nález z toho istého endpointu: hodnota ide do regexu **neescapovaná**,
takže `{"title": "("}` vráti **HTTP 500** z neplatného vzoru a vzor typu
`(a+)+` je otvorená cesta k zahlteniu. Klient si preto musí escapovať sám —
robí to `EtaskWorkflowViewService`.

**Dôsledok pre nás:** vyhľadávanie v sekcii Workflow ponúka `Identifikátor`
a `Skratku`, nie `Názov`. Ponúknuť názov by znamenalo pole, ktoré vždy vráti
prázdno — presne ten druh ticha, kvôli ktorému tento súbor existuje.

## E22. `changeType()` vráti pri nula výsledkoch surovú odpoveď namiesto poľa

**Príznak.** Zobrazenie, ktoré nenájde ani jeden prípad, **zhodí komponent**:

```
TypeError: e.content.filter is not a function
```

Nie prázdny zoznam, nie hláška — biela plocha. A čo je horšie, prejaví sa to až
u toho, kto má prázdny filter: na stroji, kde dáta sú, je všetko v poriadku.

**Príčina.** `getResourcePage()` mapuje odpoveď cez `changeType()`
(`netgrif-components-core`, ~r. 2762–2793). Tá sa rozhoduje podľa toho, či
odpoveď má `_embedded`:

```js
if (!r.hasOwnProperty('_embedded')) { return r; }   // <- celý surový objekt
```

Lenže **HAL odpoveď bez `_embedded` je pre nula záznamov úplne normálna**. Volajúci
teda dostane namiesto `Array<Case>` celý wrapper (`{page: {...}, _links: {...}}`),
`page.content` je objekt a ktorékoľvek `.filter`/`.map` nad ním padne.

**Obídenie.** Typ sa musí overiť, nie iba null:

```ts
const cases = Array.isArray(page?.content) ? page.content : [];
```

`?? []` **nechráni** — hodnota je definovaná a truthy, len to nie je pole. Presne
preto to prežilo review: vyzerá to ako ošetrený prípad. V tomto repe to stálo
navigáciu na dashboarde (klik na kategóriu skončil na roote) a je to ošetrené
v `dashboard.component.ts`.

**Oprava.** Vrátiť `[]`, keď `_embedded` chýba.

## E23. „Table mode" existuje, ale knižničné case view komponenty si ho vypnú

**Príznak.** V hlavičke zoznamu je v editačnom móde prepínač **Table mode**
(`headers.overflowMode`) so šírkou stĺpca a počtom stĺpcov. V našom portáli sa
buď nezobrazil vôbec, alebo — po pridaní providera — sa zobrazil, dal sa zapnúť,
ale **zoznam sa nerozšíril**. Žiadna chyba, žiadny log.

**Príčina je dvojitá** a to je na tom to zákerné:

1. `OverflowService` **nie je** `providedIn: 'root'` a všetci jeho konzumenti ho
   injectujú `@Optional()`. Bez explicitného providera je teda `null`,
   `AbstractHeaderComponent` nastaví `canOverflow = false` a prepínač sa
   nevykreslí (`*ngIf="canOverflow"`).
2. Aj **s** providerom to nestačí. `DefaultTabbedCaseViewComponent`
   (~r. 2967) aj `FilterFieldTabbedCaseViewComponent` (~r. 5148) volajú:

   ```js
   super(caseViewService, loggerService, injectedTabData, undefined, ...)
   ```

   Štvrtý argument je `_overflowService` a je **natvrdo `undefined`** — hoci
   `AbstractTabbedCaseViewComponent` (r. 27483) ho do `AbstractCaseViewComponent`
   forwarduje správne. Výsledok: `nc-header` inštanciu má (má vlastnú DI cestu,
   takže prepínač funguje a stav si aj zapamätá), ale `getWidth()`
   a `getOverflowStatus()` na case view čítajú `undefined` a vracajú `'100%'`
   a `false`. Prepínač teda prepína niečo, na čo sa nikto nepozerá.

**Obídenie.** Vlastná komponenta nad `AbstractTabbedCaseViewComponent`, ktorá si
`OverflowService` injectne a **prepustí ho do `super()`** — v tomto repe
`EtaskTabbedCaseViewComponent` (a `SideNavCasesCaseViewComponent` pre netabovú
cestu). Providery treba opísať z originálu celé, nielen `OverflowService`:
bez `CaseViewService`, `SearchService`, `ViewIdService`, `CategoryFactory`
a tovární `filterCaseTabbedData*` z `@netgrif/components` komponenta spadne na
`NullInjectorError` a tab ostane prázdny.

**Oprava.** Prepustiť injectnutú inštanciu do `super()`; ideálne k tomu
`providedIn: 'root'`, nech to nie je opt-in, o ktorom sa nikde nepíše.

## E24. `setData` s poľom `dateTime` padne na chýbajúcom JSR310 module

**Príznak.** Akcia zapíše do payloadu `setData` hodnotu typu `LocalDateTime`
a engine vráti:

```
Java 8 date/time type `java.time.LocalDateTime` not supported by default:
add Module "com.fasterxml.jackson.datatype:jackson-datatype-jsr310"
```

Používateľ pritom videl len „Požiadavku sa nepodarilo odoslať".

**Príčina.** Serializer, cez ktorý ide telo `setData`, nemá registrovaný
`JavaTimeModule`. Týka sa to iba tejto cesty — pole typu `dateTime` zapísané
cez `change ... value { }` je v poriadku.

**Obídenie.** Poslať ISO reťazec, ktorý `LocalDateTime.toString()` aj tak vracia;
engine si ho pri zápise poľa parsuje sám:

```groovy
payload["src_started"] = ["value": (req_started.value as java.time.LocalDateTime).toString(),
                          "type": "dateTime"]
```

**Oprava.** Zaregistrovať `JavaTimeModule` do toho `ObjectMapper`-a.

## E25. Po zmene rolí vracia stará session 403, hoci `/user/me` novú rolu už hlási

**Príznak.** Používateľovi sa pridelí rola. On si stránku obnoví, vidí sa
ako držiteľ tej roly, a každá akcia, ktorá ju vyžaduje, mu vráti **403**.
Pomôže až odhlásenie a prihlásenie.

**Meranie.** Rovnaký účet, dva tokeny: jeden získaný pred pridelením roly,
druhý po ňom.

```
POST /api/user/{id}/role/assign   (rola agent)

GET  /api/user/me       stará session → role: ['agent']
GET  /api/user/me       nová session  → role: ['agent']

POST /api/workflow/case stará session → 403
POST /api/workflow/case nová session  → 200
```

**Prečo to bolí viac, než by muselo.** Keby stará session rolu nehlásila,
bolo by z čoho pochopiť, čo sa deje. Ona ju ale hlási, lebo `/user/me` číta
z databázy, kým oprávnenia sa vyhodnocujú proti `stringId` rolí uloženým
v session. Používateľ teda vidí stav, ktorý pre neho neplatí, a odpoveď
403 nemá s čím spojiť.

**Dôsledok pre appky.** Obnovenie stránky nestačí a žiadne množstvo
načítavania na frontende to nevyrieši — stará je session, nie stránka.
Kto prideľuje role, musí človeku povedať, že sa má znova prihlásiť.

**Oprava.** Po zmene rolí zneplatniť sessiony toho účtu, alebo oprávnenia
vyhodnocovať proti aktuálnemu stavu účtu namiesto kópie v session.

## E26. `role/assign` role NAHRADÍ, vrátane systémovej `default`

**Príznak.** Po pridelení jednej roly cez API má účet práve tú jednu rolu.
Systémová `default`, ktorú má mať každý prihlásený, je preč — a s ňou
všetko, čo na nej visí.

**Meranie.**

```
pred:  processRoles = [default]
POST /api/user/{id}/role/assign  ["<stringId roly agent>"]   → 200
po:    processRoles = [agent]
```

**Prečo to prekvapí.** Endpoint sa volá `assign` a knižnica ho popisuje ako
„Assign role to the user", takže sa od neho čaká pridanie. Je to zápis
celej množiny. Telo je navyše holé pole reťazcov — `{"roleIds": [...]}`
aj `{"roles": [...]}` vrátia **400**, čo pri hľadaní správneho tvaru vyzerá
ako chyba v dátach, nie v obale.

**Obídenie.** Posielať vždy celú cieľovú množinu vrátane `default`, alebo
role prideľovať cez `setProcessRole` v akcii, kde sa dopĺňa po jednej.

## E27. Titulky tlačidiel úlohy nesie len `/api/task/search`, nie `/api/task/case/{id}`

**Príznak.** Sieť má na prechode `<event type="finish"><title name="empty_button"></title></event>`,
teda prázdny titulok, ktorým sa tlačidlo skrýva (RUNBOOK 11). V appke to
funguje — tlačidlo tam nie je. Test, ktorý si úlohu vypýta cez
`/api/task/case/{caseId}`, dostane `finishTitle: null` a ohlási chybu, ktorá
neexistuje.

**Meranie.** Tá istá úloha, dva endpointy, ten istý účet aj jazyk:

```
GET  /api/task/case/{caseId}    → {"title": "Dokončený nástup", "finishTitle": null,
                                   "cancelTitle": null, "assignTitle": null}
POST /api/task/search           → {"title": "Dokončený nástup", "finishTitle": "",
                                   "cancelTitle": "", "assignTitle": ""}
```

Rozdiel nie je v jazyku (rovnaké pre `sk`, `en` aj neexistujúci `zz`) ani
v priradení úlohy.

**Prečo to prekvapí.** Oba endpointy vracajú „úlohu" a vyzerajú zameniteľne,
takže sa `/api/task/case/{id}` berie ako lacnejšia cesta k tomu istému. Nie je:
`null` a `""` znamenajú pri titulkoch **opak** (`canFinish()` je
`oprávnenie && title !== ''`), takže na tom endpointe sa skryté tlačidlo javí
ako zobrazené a zobrazené ako skryté.

**Dôsledok pre testy.** Čokoľvek o tlačidlách úlohy sa meria na
`/api/task/search` — je to aj ten endpoint, ktorý používa zoznam úloh vo
frontende, takže sa meria to, čo vidí človek.

## E28. Časovaný prechod v slučke do vlastného miesta vystrelí len raz

**Čo sa deje.** Systémový prechod s `<trigger type="time"><delay>PT5M</delay></trigger>`,
ktorý berie token z miesta a vracia ho späť do toho istého miesta, sa vykoná
presne raz — 5 minút po vzniku svojej úlohy. Potom už nikdy. Úloha pritom
ďalej existuje a prechod je spustiteľný.

**Prečo.** Po výstrele sa prechod ani na okamih nestane nespustiteľným, takže
engine úlohu nezmaže, ale **recykluje** (to isté `_id`). Časovač sa plánuje len
pri vzniku úlohy: recyklovaná úloha má po výstrele `triggers: []`. Nič to
nehlási. (Kolekcia `quartz_triggers` o tom nič nepovie — je prázdna aj pri
fungujúcich hodinách, plán drží Quartz v pamäti.)

**Overené** na 6.3.1 v `sd_ticket`: úloha `t_tick` vystrelila 12:16:53, 5 min
po podaní, a zostala s tým istým `_id` a prázdnymi `triggers`. S dvoma
striedajúcimi sa prechodmi hodiny bežali: `t_tick` → `t_tock` o 12:26 →
`t_tick` o 12:31.

**Obídenie.** Dva prechody, ktoré si token podávajú (`t_tick`: `p_clock →
p_clock_b`, `t_tock`: `p_clock_b → p_clock`), s telom v spoločnej funkcii.
Prechod po výstrele zanikne, jeho úloha pri ďalšom kole vznikne nanovo aj
s časovačom. Vzor je v `sd_ticket` (`sla_tick`) a v `sd_menu` (`clean_drafts`).

## Čo s tým

Najviac stojí **E1** — znemožňuje celú jednu operáciu — a **E2**, ktoré robí
z Task zobrazení druhotriedne. Ostatné sú jednotlivé ladenia. **E3 je
stiahnuté**: to sa ukázalo ako moja chyba merania, nie chyba enginu.

**E18** je z tej istej rodiny ako **E11** a **E8**: engine urobí správnu vec
a zamlčí dôvod. Opraviť sa dá jedným handlerom. **E19** je horšie: tam engine
ohlási úspech operácie, ktorá sa nestala. **E21** je tretí variant toho istého:
endpoint ponúka parameter, ktorý nemôže fungovať, a mlčí o tom.

**E22** a **E23** sú obe z frontendovej knižnice a obe sú lacné na opravu
(jeden `return []`, jeden prepustený argument), ale drahé na nájdenie: prvá sa
prejaví len pri prázdnom výsledku, druhá vyzerá ako chýbajúca funkcia, hoci je
hotová a len odpojená. **E23** stojí za zmienku aj preto, že kvôli nej sme si
mysleli, že tabuľkový režim v tejto verzii vôbec nie je — podrobne
v `ANALYZA_TABULKY.md`.

Čo v tejto kope **nie je**: správanie, ktoré je v poriadku a treba ho len
poznať — oprávnenia a `perform` ako skratka, `assignPolicy` a jeho dva okamihy,
prípad si drží verziu siete, `stringId` roly per verziu, `default_headers`
a `allowedNets`, znaky v kľúčoch možností, `_map` typy, `setData` telo,
odmietnutie ako HTTP 200. To je druhá kopa a je v `PETRIFLOW_LEARNINGS.md`,
`RUNBOOK.md` a `docs/reference/cheatsheet.md`.
