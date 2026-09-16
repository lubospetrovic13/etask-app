# Tabuľkový view, úprava dát v riadku a hromadné akcie — analýza

Tri požiadavky, ktoré spolu tvoria jednu obrazovku: **tabuľka**, v ktorej sa dá
**editovať priamo v bunke** a **označiť viac riadkov naraz** a spraviť nad nimi
spoločnú akciu (typicky schválenie).

Všetko nižšie je **namerané** na NAE 6.3.1 v tomto repozitári, nie odvodené
z dokumentácie. Čísla HTTP kódov a správania sú z bežiaceho enginu.

**Krátka odpoveď: áno, všetky tri sa dajú.** Jedna z nich je skoro zadarmo,
jedna je bežná frontendová práca a jedna má jednu nepríjemnú vlastnosť enginu,
o ktorej treba vedieť skôr, než sa to začne stavať.

---

## 1. Čo z toho už existuje

### Stĺpce a ich výber — hotové

Zoznamy prípadov už dnes **sú tabuľka**, len vykreslená ako akordeón. Celá
stĺpcová mašinéria je v knižnici:

| čo | kde |
|---|---|
| definícia stĺpca vrátane typu poľa | `HeaderColumn { type, fieldIdentifier, title, fieldType, petriNetIdentifier, sortDirection, searchInput }` |
| výber stĺpcov používateľom | `HeaderMode.EDIT` (`abstract-edit-mode.component`) |
| triedenie a hľadanie v stĺpci | `HeaderMode.SORT`, `HeaderMode.SEARCH` |
| predvolené stĺpce | `default_headers` na zobrazení (nastavuje menu sieť) |
| hodnota bunky pre konkrétny prípad | `AbstractCasePanelComponent.getFeaturedMetaValue()` / `getFeaturedImmediateValue()` → `FeaturedValue` |

Stĺpec z dátového poľa funguje len ak má pole `immediate="true"` a jeho sieť je
v `allowedNets` toho zobrazenia — to je známa tichá pasca (cheatsheet).

**Čo teda chýba pre tabuľkový view:** nie dáta, ale **vykreslenie**. Nahradiť
`mat-accordion` + `app-case-panel` za `mat-table` (alebo `cdk-table`) nad tými
istými `selectedHeaders$` a `FeaturedValue`. Virtuálny scroll a stránkovanie už
v `CaseViewService` sú.

### Doplnené neskôr: „Table mode" v knižnici už JE — len je odpojený

Táto analýza pôvodne tvrdila, že vykreslenie treba napísať celé. **To nie je
presné** a zistilo sa to až na cudzej inštancii (`etask.netgrif.cloud`), kde ten
režim beží — v tej istej verzii knižnice, akú máme my.

V hlavičke je v editačnom móde prepínač **Table mode** (interne
`OverflowService.overflowMode`) plus **šírka stĺpca** a **počet stĺpcov**. Po
zapnutí sa hlavička aj zoznam rozšíria na `počet × šírka` a idú do vodorovného
posunu, takže naraz je vidno podstatne viac stĺpcov, než sa zmestí na obrazovku.
Vykreslenie ostáva akordeónové — **nie je to `mat-table`** — ale väčšinu z toho,
kvôli čomu sa tabuľka pýta (veľa stĺpcov vedľa seba, riadok ako riadok), to
pokrýva bez jediného nového komponentu.

Prečo to nikto nevidel: komponent je odpojený hneď dvakrát (`ENGINE_ISSUES.md`,
**E23**) — `OverflowService` nie je `providedIn: 'root'` a knižničné case view
komponenty si ho navyše v konštruktore prepíšu na `undefined`. V tomto repe je to
zapojené cez `EtaskTabbedCaseViewComponent`.

**Dôsledok pre plán nižšie:** krok „postaviť tabuľkové vykreslenie" prestáva byť
prvý a stáva sa nepovinný. Otázka už nie je „ako spraviť tabuľku", ale „stačí
nám široký akordeón, alebo naozaj chceme `mat-table` s bunkami?" — a na to sa dá
odpovedať až po tom, čo si Table mode niekto vyskúša na reálnych dátach.

### Hromadné akcie v Petriflow — hotové, len sa o tom nevie

Toto je najdôležitejší nález celej analýzy. `EtaskActionDelegate` (resp. engine
pod ním) má **množné varianty už dnes**:

```
assignTasks(List<Task>, IUser)
finishTasks(List<Task>, IUser)
cancelTasks(List<Task>, IUser)
executeTasks(Map, String, Closure<Predicate>)
findTasks(Closure<Predicate>, Pageable)
```

Schválenie dvadsiatich faktúr naraz je teda **jedna akcia v sieti**, nie nový
endpoint a nie Java:

```groovy
def tasks = findTasks({ it.transitionId.eq("t_schvalenie")
        .and(it.caseId.in(vybrane_id)) }, pageable)
finishTasks(tasks, loggedUser())
```

Čo znamená, že požiadavka „bulk check a multitask aktivity" je **vrstva 1**,
presne tak, ako to tento repozitár chce. Nový endpoint by bol chyba.

---

## 2. Čo chýba a čo to stojí

| požiadavka | vrstva | čo treba postaviť | odhad |
|---|---|---|---|
| **tabuľkový view** | 3 (render) | komponent nad `mat-table`, napojený na existujúce `selectedHeaders$` a `CaseViewService` | stredný — dni, nie týždne |
| **úprava v bunke** | 3 (render) + 1 | editovateľná bunka, ktorá volá `setData`; v sieti nič nové | malý, ale **pozri kapitolu 3** |
| **hromadné akcie** | 1 (+ trocha 3) | sieť s výberom a akciou; vo frontende len zaškrtávacie políčka a odovzdanie id | malý |

Žiadna z nich nevyžaduje zásah do enginu.

---

## 3. Jediná nepríjemná vec: zápis do úlohy ju priradí

Toto je vec, ktorá rozhodne o dizajne editovateľnej tabuľky, a nie je nikde
napísaná. Namerané:

```
uloha t_on_it, assignPolicy=manual, NEPRIRADENA (user = None)

POST /api/task/{id}/data  { on_it_email: "..." }   -> HTTP 200, hodnota zapisana
GET  /api/task/{id}                                 -> user JE NASTAVENY
```

**Zápis dát úlohu potichu priradí volajúcemu.** Nie je to chyba — engine
potrebuje riešiteľa na to, aby vedel, kto zmenu urobil — ale pre tabuľku to má
priamy dôsledok: **používateľ, ktorý v tabuľke prepíše dvadsať buniek v dvadsiatich
riadkoch, si tým priradí dvadsať úloh.** Na zdieľanej fronte (pult, schvaľovanie,
`assignPolicy=manual`) to znamená, že ich ostatným zobral.

Oprávnenia sa pritom vynucujú správne — účet bez roly na ten prechod dostal:

```
POST /api/task/{id}/data        -> HTTP 403 Forbidden
GET  /api/task/finish/{id}      -> HTTP 405 "cannot be finished, because it is not assigned"
```

Z toho plynú tri možné návrhy editovateľnej tabuľky a treba si vybrať vedome:

1. **Editovať sa dá len to, čo už mám priradené.** Najbezpečnejšie; tabuľka je
   potom „moje úlohy", nie „všetko".
2. **Editovanie priradí a nechá priradené.** Zodpovedá tomu, čo engine robí sám.
   Musí to byť v UI vidno — inak si človek nevšimne, že si zobral dvadsať úloh.
3. **Editovanie priradí, a po zápise sa úloha uvoľní** (`cancel`). Zachová
   zdieľanú frontu, ale `cancel` je ďalšie volanie a pri zlyhaní v strede
   zostane úloha visieť na tom, kto editoval.

Odporúčam **1 pre zdieľané fronty a 2 pre osobné zoznamy**, s tým, že stĺpec
„riešiteľ" je v takej tabuľke povinný — inak je zmena vlastníctva neviditeľná.

---

## 4. Prečo hromadné akcie nerobiť z prehliadača

Engine **nemá žiadny hromadný endpoint**. Všetko je per-task:

```
GET  /api/task/assign/{id}
GET  /api/task/finish/{id}
GET  /api/task/cancel/{id}
POST /api/task/delegate/{id}
POST /api/task/{id}/data
```

Hromadné schválenie z frontendu by teda znamenalo **2N HTTP volaní** (priradiť +
dokončiť) a tri problémy, ktoré sa nedajú obísť na klientovi:

* **Nie je to atomické.** Keď zlyhá 7. z 20, prvých 6 je dokončených a zvyšok
  nie. Používateľ vidí polovičný výsledok a nemá čo spraviť.
* **Odmietnutie neprichádza ako chyba.** Blokovaný `finish` vráti **HTTP 200**
  a dôvod v tele ako `error` — klient, ktorý pozerá na stavový kód, ohlási
  úspech pri každom odmietnutom schválení.
* **Poradie a súbeh.** Dvadsať paralelných volaní nad tým istým prípadom vie
  skončiť v stave, ktorý sieť nepredpokladá.

Serverová akcia (`finishTasks`) tieto tri veci rieši tým, že beží v jednom
kontexte. **Pozor ale:** výnimka z akcie v strede cyklu nechá časť zmien
zapísaných a zvyšok nie (to je ten istý mechanizmus ako pri `u?._id`). Bulk
akcia preto musí:

* zbierať výsledky do zoznamu a **nepadnúť na prvej chybe**,
* výsledok napísať do poľa, ktoré používateľ uvidí („18 schválených, 2 odmietnuté
  a prečo"),
* byť idempotentná — druhé spustenie nad tou istou množinou nesmie nič pokaziť.

To je presne vzor, ktorý už v repozitári je: menu siete (`sd_menu`, `on_menu`)
zbierajú `created` / `unchanged` / `failed` a výsledok dávajú do názvu prípadu.

---

## 5. Ako by som to postavil

**Hromadné schvaľovanie ako prípad, nie ako tlačidlo.** Vlastná sieť
(napr. `financie/hromadne/hr_schvalenie`) s jedným formulárom:

* `filter` alebo `caseRef` pole s výberom prípadov (ponuka sa dá naplniť
  `findCases` v akcii podľa roly prihláseného),
* `enumeration_map` s rozhodnutím (schváliť / vrátiť),
* `text` na dôvod,
* `button`, ktorého akcia zavolá `findTasks` + `finishTasks` a zapíše protokol.

Výhody oproti tlačidlu v tabuľke: je to **prípad**, takže má autora, čas,
protokol a dá sa naň pozrieť spätne — kto schválil dvadsať faktúr naraz a prečo.
Pri hromadnom schvaľovaní je to väčšinou požiadavka auditu, nie luxus.

**Tabuľka a výber riadkov** je potom len vstup do tohto prípadu: zaškrtnuté
riadky sa odovzdajú ako zoznam id. Frontend nerobí dvadsať volaní, robí jedno.

**Úprava v bunke** je samostatná vec a dá sa spraviť nezávisle — `setData` per
bunku pri opustení poľa, s tým, čo hovorí kapitola 3.

---

## 6. Čo treba overiť skôr, než sa to začne stavať

Toto som **neoveril** a každé z toho vie zmeniť odhad:

1. **Správanie `finishTasks` pri chybe v strede zoznamu.** Či prebehne zvyšok,
   alebo sa celé zastaví. Meria sa jednou sieťou s úmyselne padajúcim guardom.
2. **Či `finishTasks` spúšťa `finish` udalosti** každej úlohy (teda aj guardy
   a akcie), alebo len posúva žetóny. Od toho závisí, či sú hromadné schválenia
   bezpečné.
3. **Výkon nad reálnym počtom.** Tabuľka nad 5 000 prípadmi s deviatimi stĺpcami
   je iná úloha než nad 50; `CaseViewService` stránkuje po 25.
4. **Či `mat-table` uživí virtuálny scroll** s tými istými dátami — knižnica dnes
   používa `cdk-virtual-scroll-viewport` nad akordeónom.

Body 1 a 2 sú lacné (jedna sieť, jeden beh) a **odporúčam ich odmerať ako prvé** —
rozhodujú o tom, či je hromadné schvaľovanie jednoduchá akcia alebo projekt.
