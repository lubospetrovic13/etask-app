# Chyby enginu a knižnice — kopa na opravu upstream

Toto je **prvá z dvoch kôp**. Sú tu veci, ktoré nie sú „takto to funguje, treba
to vedieť", ale **defekty**: engine alebo `@netgrif/components` sa správa inak,
než sľubuje vlastný model, a skoro vždy o tom mlčí. Druhá kopa — správanie,
ktoré je v poriadku a treba ho len poznať — je v `PETRIFLOW_LEARNINGS.md`,
`RUNBOOK.md` a `reference/cheatsheet.md`.

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

## Čo s tým

Najviac stojí **E1** — znemožňuje celú jednu operáciu — a **E2**, ktoré robí
z Task zobrazení druhotriedne. Ostatné sú jednotlivé ladenia. **E3 je
stiahnuté**: to sa ukázalo ako moja chyba merania, nie chyba enginu.

Čo v tejto kope **nie je**: správanie, ktoré je v poriadku a treba ho len
poznať — oprávnenia a `perform` ako skratka, `assignPolicy` a jeho dva okamihy,
prípad si drží verziu siete, `stringId` roly per verziu, `default_headers`
a `allowedNets`, znaky v kľúčoch možností, `_map` typy, `setData` telo,
odmietnutie ako HTTP 200. To je druhá kopa a je v `PETRIFLOW_LEARNINGS.md`,
`RUNBOOK.md` a `reference/cheatsheet.md`.
