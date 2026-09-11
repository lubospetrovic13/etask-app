# Čo `petriflow_reference.md` nepokrýva alebo pokrýva nesprávne

Zistené počas jedného POC na Netgrif Platform 6.3.1, single-tenant, lokálne nasadenie.

**Toto je druhá z dvoch kôp.** Sú tu veci, ktoré platia — engine sa správa
korektne, len to nikde nestojí, alebo to príručka tvrdí inak. Znalosť z tejto
kopy je trvalá a patrí do dokumentácie. Prvá kopa — **defekty**, kde sa engine
alebo knižnica odlišuje od vlastného modelu — je v `ENGINE_ISSUES.md`; každý
riadok tam prestane platiť v momente, keď sa to opraví, a to je aj cieľ.

Záznamy, ktoré patria do oboch, sú označené `→ ENGINE_ISSUES E*`: tu je napísané,
ako sa tomu vyhnúť dnes, tam ako to opraviť.

Zdroje sú tri a je dobré ich odlíšiť:

- **Za behu** — chyba alebo správanie, ktoré sme videli v aplikácii
- **Z klientovho procesu** — prevzaté z `ticket_vacation.xml`, teda z kódu, ktorý beží
  v produkcii, ale my sme to sami nepotvrdili
- **Odvodené** — vysvetlenie, ktoré najlepšie zapadá do faktov, ale nie je dokázané

---

## A. Príručka to tvrdí nesprávne

### A1. `workspace` neexistuje na single-tenant nasadení

**Príručka, gotcha 34 a 21:** *„ALWAYS use `workspace + "process_id"` in `findCases`,
`findTasks`, and `createCase`. Omitting it causes silent lookup failures."*

**Realita:** na single-tenant Netgrif Platform premenná `workspace` neexistuje a
`processIdentifier` je holý (`ai_config`, nie `ws/ai_config`). Dodržanie tejto rady
spôsobí presne to, pred čím varuje — `findCases` nenájde nič, bez chyby.

**Náhrada, ktorá funguje v oboch nasadeniach** — odvodenie z vlastného casu:

```groovy
{ def caseObj ->
    def pid = caseObj.processIdentifier
    return pid.contains("/") ? pid.substring(0, pid.lastIndexOf("/") + 1) : ""
}
```

Single-tenant dá `""`, multi-tenant `"ws/"`. Príručka podobný trik uvádza v gotcha 39,
ale len ako výnimku pre anonymný kontext — v skutočnosti je to lepší default vždy.

*Zistené za behu: prázdna ponuka modelov, ktorá sa opravila po tejto zmene.*

### A2. `button` nepotrebuje `<init>1</init>`

**Príručka, gotcha 29 a 19:** *„`button` field: `<init>1</init>` required"*.

**Realita:** v klientovom procese majú buttony `show`, `hide` a `share_btn` `<init>`
úplne bez neho a fungujú.

*Z klientovho procesu.*

### A3. `<action>` bez atribútu `id` je platný

**Príručka, CHECKLIST:** *„Action IDs globally unique sequential"*.

**Realita:** `ticket_vacation.xml` riadok 558 má `<action>` bez `id` a proces beží.
Unikátnosť je pravdepodobne požiadavka len keď id existuje; sekvenčnosť je štýl,
nie pravidlo.

*Z klientovho procesu.*

### A4. `case.getFieldValue(id)` nie je bezpečná alternatíva

**Príručka, gotcha 33:** *„`case.getFieldValue("id")` — alternative to
`case.dataSet["id"]?.value`"*, prezentované ako rovnocenné.

**Realita:** na poli, ktoré v danej verzii siete neexistuje, `getFieldValue` padá.
`dataSet[id]?.value` vráti `null`. Nie sú rovnocenné, druhé je bezpečné.

*Odvodené z pádu pri čítaní novopridaného poľa; `dataSet["x"].value` je zároveň idióm
použitý v `EtaskActionDelegate` samotného projektu.*

### A5. Process funkcie neberú len dátové polia

**Príručka, Pattern 21:** *„Signature: `{ param1, param2 -> body }` — params are data
field objects, same as `f.field_id` imports."*

**Realita:** berú obyčajné `def` aj typované parametre, vracajú hodnoty, volajú sa
navzájom a **dajú sa preťažovať podľa počtu argumentov** — `ticket_vacation.xml` má dve
funkcie `addWorkflowEventToHistory` s rôznou aritou. Tiež funguje
`change X options { }` vnútri funkcie, čo príručka neuvádza (ukazuje len `change ... value`).

*Z klientovho procesu + overené za behu na `render_codebook`, `net_prefix`, `model_slug`.*

---

## B. Príručka to nepokrýva vôbec

### B1. Mongo nepovoluje bodku ani dolár v kľúči mapy

Options selektov a multichoice sa ukladajú ako dokument. Kľúč s bodkou zhodí uloženie:

```
Map key llama3.1:70b contains dots but no replacement was configured!
```

Týka sa to väčšiny lokálnych tagov (`llama3.1:70b`, `Qwen/Qwen2.5-32B`) aj niektorých
externých ID (`gpt-4.1`). **Tichá mína pre každý dynamicky plnený číselník.**

Riešenie: v options je slug (`.` → `__D__`, `$` → `__S__`), reálna hodnota zostáva
v zdrojovom JSON-e a dohľadá sa cez slug. Vybraná hodnota enumu je potom slug, takže
reálny kľúč treba držať v samostatnom poli.

Vedľajšie zistenie: **bodka zmizne aj zo zobrazovaného textu** option (`Llama 3.1 70B`
→ `Llama 31 70B`). Kozmetické, ale zavádzajúce.

*Zistené za behu.*

### B2. Button nevidí hodnotu textového poľa v tej istej požiadavke

Najdrahšia lekcia vlákna. Textové polia a textarea posielajú hodnotu na server
**až pri strate fokusu**, čo nastane v tom istom okamihu ako klik na tlačidlo. Obe
zmeny idú v jednej `setData` požiadavke a **event tlačidla sa spracuje skôr**, než sa
hodnota poľa aplikuje.

Prejav: akcia vidí prázdne pole, a to isté kliknutie druhýkrát už funguje.

`phase="post"` to **nerieši** — „post" je relatívne k vlastnému poľu tlačidla, nie
k celej dávke.

Ktoré typy sú bezpečné: **select, checkbox, boolean** posielajú hodnotu okamžite pri
zmene, takže sú uložené ešte pred klikom. Nebezpečné sú len `text` a textarea.

Dve funkčné riešenia:
1. Spracovanie dať do `set` eventu **toho textového poľa**, nie tlačidla.
2. Formulár usporiadať tak, aby **posledný vstup pred tlačidlom bol select** — kým naň
   klikneš, textové polia už dávno stratili fokus.

*Zistené za behu, potvrdené dvoma nezávislými prejavmi.*

### B3. Pridanie dátového poľa sa nepropaguje do existujúcich casov

Case si drží svoju verziu siete. Po uploade siete s novým poľom vráti `f.new_field`
v existujúcom case `null` a akcia padne na:

```
Cannot set property 'value' on null object
```

Táto správa vždy znamená `change <null> value`, teda pole z import hlavičky, ktoré
v tom case neexistuje. **Riešenie je nový case**, nie oprava kódu. Kód sa dá ošetriť
`if (field != null)`, ale to len zamaskuje nekompletný case.

*Odvodené — najlepšie vysvetlenie pádu, ktorý zmizol po založení nového casu. Priamo
potvrdené nebolo.*

### B4. `immediate="true"` na `<data>`

Atribút na elemente `data`, v príručke nikde. V klientovom procese je na `date`
a `enumeration_map`, teda na poliach, ktorých `set` event má reagovať promptne.

Predpoklad: posiela hodnotu okamžite namiesto čakania na blur. Ak áno, je to
**bezpečné na selektoch a na textových poliach bez `set` eventu**, ale **nebezpečné
na textovom poli so `set` eventom** — akcia by sa spustila uprostred písania.

*Z klientovho procesu, semantika neoverená.*

### B5. `<desc>` na dátovom poli

Popis pod poľom vo formulári. Príručka ho zmieňuje len v zákaze znakov (C6), ale
neuvádza v poriadku elementov ani ako featuru.

Pozícia: **hneď za `<title>`**. Poradie teda je
`<id>` → `<title>` → `<desc>` → `<placeholder>` → `<component>` → `<init>` → `<options>`.

Pozor: podľa konfigurácie frontendu sa `desc` môže zobraziť skrátené na jeden riadok,
takže sa naň nedá spoliehať pri dlhšom vysvetlení.

*Z klientovho procesu, zobrazenie overené za behu.*

### B6. `make ... on transitions` — množné číslo

Príručka ukazuje len `make <field>, <behaviour> on <transition_id>` s importom
konkrétneho `t.t1`. Kľúčové slovo **`transitions`** (množné) platí na všetky tasky
naraz a **netreba importovať žiadny task**:

```groovy
make help_models, visible on transitions when { showIt }
```

Zjednodušuje to prepínanie viditeľnosti v procesoch s viacerými taskami.

*Z klientovho procesu, použité a funkčné.*

### B7. Ikonu tlačidla sa z akcie zmeniť nedá

`make` mení chovanie (`visible`, `hidden`, `editable`), nie `placeholder`. Rozbaľovacia
sekcia s jedným tlačidlom preto nikdy neprepne strelku.

Tri možnosti:

| riešenie | polí na sekciu | stav vidno |
|---|---|---|
| dva buttony `show`/`hide` + dva dividery, prepínajú si viditeľnosť | 4 | áno, strelka sa mení |
| jeden button + parita `value % 2` | 2 | **nie**, ikona zostáva |
| **boolean pole** so `set` eventom | 1 | áno, prepínač je stav sám |

Prvý variant je klientov. Tretí je najúspornejší a má vlastný popis, takže sa hodí
tam, kde nejde o vzhľad strelky.

Súvisiace: **hodnota buttonu sa pri každom kliku zvyšuje**, takže `value % 2 == 1` je
funkčný prepínač — len bez vizuálnej zmeny.

*Zistené za behu (ikona sa nemenila) + parita z klientovho procesu.*

### B8. Jedno miesto `tokens=1` môže obsluhovať N trvale otvorených taskov

Pattern 16b v príručke ukazuje jedno miesto → jeden task. Kontrolný zoznam zároveň
žiada *„exactly one `tokens=1`"*.

Obe sa dajú splniť naraz: jedno miesto s tokenom a **N read arcov do N transition**.
Všetky tasky sú trvale otvorené, žiadny nemá výstupný arc.

```
[p_alive : tokens=1] ──read──► [t_codebook]
                     ──read──► [t_config]
                     ──read──► [t_test]
```

Varovanie o viacerých read arcoch (Pattern 16) sa týka **viacerých arcov do jednej
transition**, nie jedného miesta do viacerých transition.

*Overené za behu — tri tasky v jednom case.*

### B8b. Read arc na KONZUMOVANOM miesta nepreži odmietnuté `finish`

→ `ENGINE_ISSUES.md` **E8**. Návrat tokenu by mal zmazané úlohy obnoviť.

Trvale otvorený read-only pohľad sa dá zavesiť na read arc z ktoréhokoľvek miesta.
Kým to miesto nikto nekonzumuje (`p_alive` v `sd_ticket`), je to bezpečné. Keď ho
konzumuje iný prechod, je to **mína**:

```
[p_na_schvalenie] ──read──► [t_pohlad]        (read-only, žiadateľ)
                  ──regular──► [t_rozhodnutie]  (konzumuje token)
```

Keď na `t_rozhodnutie` niekto klikne DOKONČIŤ a dokončenie sa **odmietne** — či už
enginom (`required` pole je prázdne), alebo výnimkou z vlastnej akcie
v `phase="pre"` — engine `t_pohlad` **zmaže a už nikdy neobnoví**. Token sa nepohol,
takže neexistuje udalosť, ktorá by ho znova povolila. Case zostane s tokenom
v `p_na_schvalenie`, `t_rozhodnutie` prežije, ale `t_pohlad` je navždy preč.

Ako sa to prejaví: používateľ, ktorý mal len ten pohľad, po jednom nepodarenom
kliknutí kolegy stratí prístup k vlastnému casu. Bez chybovej správy, bez záznamu
v logu. A `pflint` to nevie chytiť — štruktúra je platná.

```
overené za behu, NAE 6.3.1:
  pred odmietnutým finish:  ['t_pohlad', 't_rozhodnutie']
  po odmietnutom finish:    ['t_rozhodnutie']
```

**Pravidlo:** read arc pre read-only pohľad veď len z miesta, ktoré žiadny prechod
nekonzumuje — z vlastného `p_alive`, alebo z koncového miesta (`p_vybavena`), ktoré
je sink. Ak pohľad naozaj musí existovať v strede toku, jediná bezpečná cesta je
vlastné miesto, do ktorého predchádzajúci prechod uloží druhý token, a ktoré sa
vyprázdňuje systémovým prechodom — nie tým, ktorý môže odmietnuť dokončenie.

### B9. `<properties>` v `<component>`

Štýlovanie komponentu, v príručke nikde:

```xml
<component>
    <name>divider</name>
    <properties>
        <property key="fontSize">20</property>
    </properties>
</component>
```

*Z klientovho procesu, vizuálny efekt neoverený.*

### B10. Backendová logika patrí do metódy na `ActionDelegate`

Príručka nerieši, ako z akcie zavolať vlastný Java/Groovy kód. Spoľahlivá cesta: metóda
na vlastnej triede rozširujúcej `ActionDelegate` (v tomto projekte
`EtaskActionDelegate`). Je z akcie volateľná **priamo menom, bez prefixu**:

```groovy
def res = callAIToolByConfig(params)
```

Odpadá tým otázka, či engine sprístupňuje Spring beany do Groovy bindingu podľa mena —
čo sme neoverili a čo bolo jediné riziko pôvodného návrhu s `@Service("aiToolService")`.
Delegát si službu autowiruje a zostane tenký.

V metóde sú navyše rovno dostupné `workflowService`, `userService` a `log` z rodiča.

*Odvodené zo štruktúry projektu; kompilácia a volanie overené, `MissingPropertyException`
sme nikdy nevideli.*

### B11. `u?._id` na `UserFieldValue` vyhodí výnimku a zhodí celú akciu

Groovy `?.` chráni pred `null`, **nie** pred chýbajúcou property. `UserFieldValue` má
`id`, nemá `_id`, takže `u?._id` skončí `MissingPropertyException` — a tá zhodí celú
akciu, nielen ten jeden výraz.

Prejaví sa to zákerne: ak výnimka padne v strede akcie, časť zmien už je zapísaná a
zvyšok nie. Nás to stálo hodiny s diagnózou „`setData` aplikuje len prvé dva záznamy
mapy" — pritom `setData` bol nevinný, akcia sa nikdy nedostala až k nemu. Ak sa dáta
záhadne „stratia od N-tého poľa", nehľadajte chybu v `setData`, ale výnimku pred ním.

```groovy
// PADNE
assigneeIds = users.collect { u -> u instanceof String ? u : (u?._id ?: u?.id) }

// FUNGUJE
assigneeIds = users.collect { u ->
    if (u == null) return null
    if (u instanceof String) return u
    if (u instanceof Map) return (u["_id"] ?: u["id"])   // z mongo mapy
    return u.hasProperty("id") ? u.id : null             // z UserFieldValue
}.findAll { it != null }.collect { it as String }
```

`hasProperty` je jediný bezpečný test — `?.` ho nenahradí.

### B12. `async.run { }` výnimku spolkne

Čokoľvek v `async.run` beží mimo request thread, takže výnimka sa nedostane ani do
odpovede, ani do `wiz_error`. Kým sme `setData` v `sd_intake` presunuli do
synchrónneho `try/catch`, zlé pole sa prejavovalo len tak, že tiket vznikol prázdny.

Pravidlo: `async.run` používajte len na to, čoho zlyhanie *smie* zostať nepovšimnuté.
Prenos dát medzi casmi to nie je.

### B13. `findCase { it.stringId.eq(id) }` vráti `null`, aj keď case existuje

`Case` **v mongo dokumente nemá pole `stringId`** — je to len Java getter nad `_id`.
Query sa preloží na neexistujúce pole a mlčky nenájde nič. V logu je to vidieť len ako
INFO, nie ako chybu:

```
QueryMapper : Could not map 'Case.stringId'. Maybe a fragment in 'String' is
              considered a simple type. Mapper continues with stringId.
```

Dve funkčné cesty:

```groovy
def c = findCase { it._id.eq(new org.bson.types.ObjectId(id)) }        // priamo
def t = findTask { it.caseId.eq(id).and(it.transitionId.eq("t_plan")) } // Task caseId je String a existuje
```

Druhá je často lepšia: `setData(task, map)` aj tak potrebuje task, nie case.

`processIdentifier` a `visualId` na case sú naopak reálne polia a v `findCases` fungujú.

### B14. `roleRef` a `userRef` sa **zjednocujú**, nie prienikajú

Ak transition má `roleRef agent` aj `userRef tk_agents`, môže ju vykonať každý agent
**alebo** každý z `tk_agents`. Prienik („agent a zároveň pridelený tomuto zákazníkovi")
sa deklaratívne vyjadriť nedá.

Riešenie je dostať rolu do dát: zákazník má dva zoznamy (`c_agents`, `c_specialists`),
tiket si ich skopíruje ako `tk_agents` / `tk_specialists` a transition-y odkazujú len na
ne. Rola potom hovorí, *v ktorom* zozname človek je, zákazník *ktorý* zoznam to je — a
tým sú rola aj organizácia v jednom modeli. Rola v `roleRef` zostane len tam, kde
naozaj platí globálne (u nás `manager`).

### B15. Uzol URI sám žiadne zobrazenia nemá

Karta v bočnom menu (uzol URI) je len priečinok. Čo sa v ňom dá otvoriť, sú **casy
dvoch procesov enginu**: `filter` (dopyt) a `preference_filter_item` (položka menu,
ktorá na filter odkazuje). Kým nevzniknú, karta existuje a nevedie nikam.

Vyrobiť ich ide z akcie cez `createFilterInMenu`. Poradie argumentov nie je
intuitívne a **prvý je URI cesta, nie identifikátor**:

```groovy
createFilterInMenu(
        "service_desk",                                  // 1. URI cesta uzla
        "sd_tickets",                                    // 2. menu_item_identifier
        "Tikety",                                        // 3. názov (menu aj filter)
        "processIdentifier:\"service_desk/sd_ticket\"",   // 4. dopyt
        "Case",                                          // 5. "Case" alebo "Task"
        [], [:], [:], [],                                // allowed/banned roles atď.
        "confirmation_number",                           // 10. ikona
        "public")                                        // 11. viditeľnosť
```

Ak sa prvé dva zamenia, `uriService.findByUri` vráti `null` a akcia padne na
`NullPointerException` v `doCreateMenuItem` — bez zmienky o URI.

Tri pasce navyše:

* **`createOrUpdateCaseMenuItem` má iné poradie** (identifikátor je prvý, URI druhé)
  a ak URI neexistuje, **vytvorí ho** — takže omylom pribudnú uzly ako `sd_tickets`
  na úrovni rootu. Uzly žijú v Elasticsearch (`etask_uri`), nie v Mongu, takže sa
  potom musí zmazať aj dokument uzla aj `childrenId` v rodičovi — a REST na to
  neexistuje (→ `ENGINE_ISSUES.md` **E7**, recept v `RUNBOOK.md` časť 2).
* **Update cesta je v 6.3.1 rozbitá**: `createOrUpdate*MenuItem` na existujúcej
  položke volá neexistujúce `updateFilter(Case, Map)` a spadne. Idempotenciu si preto
  treba spraviť ručne: `if (findMenuItem(id) != null) return`.
  (→ `ENGINE_ISSUES.md` **E6**; tam je aj to, že `deleteMenuItem` nechá osirelý filter,
  takže poradie zahodenia je `deleteMenuItem` → `deleteFilter`.)
* **`allowed_nets` sa cez `createFilterInMenu` nastaviť nedá** — ani identifikátormi
  sietí, ani ich stringId. Ovplyvňuje to len tlačidlo „nový prípad" v zobrazení.

Dopyt píšte cez `processIdentifier`, nie cez id siete: identifikátor prežije
re-import, id nie.

### B16. Oprávnenie z `roleRef` re-import siete neprežije, z `userRef` áno

Rola má stringId razené **per verzia siete**. Po re-importe má užívateľ rolu starej
verzie, takže na casoch novej verzie stráca prístup — a naopak. Prístup cez
`userRef` (zoznam ľudí v dátovom poli casu) je na verzii nezávislý a drží.

V praxi to znamená, že „vedúci vidí všetko" cez `roleRef manager` je po každom
re-importe potrebné znova prideliť, kým viditeľnosť tímu zákazníka cez
`userRef tk_agents` funguje ďalej. Pri vývoji to vyzerá ako chyba modelu (vedúci
vidí menej než operátor), v produkcii, kde sa sieť importuje raz, to problém nie je.

### B17. Preklep v názve metódy delegáta prejde importom a vráti HTTP 200

Delegát je **dynamický**, takže volanie neexistujúcej metódy nie je pre Groovy
chyba — rozhoduje sa až pri behu. Overená reťaz na `userWithRole()` namiesto
`usersWithRole()`:

| krok | výsledok |
|---|---|
| `pfgroovy` (parse Groovy) | ticho — syntax je platná |
| import do enginu | **OK**, sieť sa naimportuje ako v1.0.0 |
| spustenie akcie | `MissingMethodException` |
| HTTP odpoveď na ten zápis | **200** |

To posledné je to zradné: volajúci dostane 200, pole sa nezapíše a v odpovedi
nie je nič. Rovnaká trieda tichosti ako B11 a B12.

Jediná statická obrana je kontrola proti inventáru metód —
`tools/pflint.py` (pravidlo `unknown-call-typo`) porovnáva nahé volania
s `docs/reference/action-api.md`. Od enginu sa to čakať nedá.

Dôsledok pre rozširovanie delegáta: každá nová metóda zväčšuje plochu, kde
preklep spadne až za behu. To nie je argument proti rozširovaniu — je to
argument za to, aby bol inventár aktuálny (`pfapi --check` v `pftest.sh`).


### B18. `removeRole` z ActionDelegate procesnú rolu NEODOBERIE (engine 6.3.1)

→ `ENGINE_ISSUES.md` **E1**. `findByImportId` tam, kde má byť `findById`.

Pridelenie funguje, odobranie nie — a mlčí. Príčina je v engine:

```java
// AbstractUserService
public IUser addRole(IUser user, String roleStringId) {
    ProcessRole role = processRoleService.findById(roleStringId);      // správne
    ...
}

@Deprecated(since = "6.2.0")
public IUser removeRole(IUser user, String roleStringId) {
    return removeRole(user, processRoleService.findByImportId(roleStringId));
    //                                        ^^^^^^^^^^^^^^ podľa importId,
    //                      hoci parameter je stringId
}
```

Podľa `stringId` teda `findByImportId` nenájde **nič**,
`user.removeProcessRole(null)` neodoberie nič a `save` uloží nezmenený dokument.
Bez výnimky, bez logu, `finish` vráti `success`. Do tejto metódy pritom vedú
**všetky** varianty `ActionDelegate.removeRole(...)`, takže z Petriflow akcie sa
rola v 6.3.1 odobrať nedá vôbec.

(A keby jej niekto dal `importId`, `findByImportId` vracia *prvú* rolu s tým
`importId` spomedzi všetkých sietí a verzií — čiže náhodnú. Tak či tak zle.)

**Obídenie:** rolu odober priamo, objekt `ProcessRole` máš zo siete.

```groovy
IUser fresh = userService.findById(userId, false)
fresh.removeProcessRole(role)      // role = net.roles.values().find { it.importId == ... }
userService.save(fresh)
```

Cena obídenia: enginová (chránená) varianta popri uložení obnovuje aj security
context. Bez toho si prihlásená session odobranú rolu podrží až do odhlásenia —
čo je to isté pravidlo, ktoré už platí pre prideľovanie.

*Nájdené tak, že akcia nahlásila „odobraná rola" a rola tam po nej stále bola.
Regresia je v `tools/pucheck.py`.*

### B19. Účet sa nesmie držať ako objekt cez viac zmien

Každá zmena používateľa je `read – mutuj – save` **celého** dokumentu. Kto si
`IUser` podrží a spraví cez neho dve zmeny za sebou, druhou prepíše výsledok
prvej — posledný `save` zapíše svoju už neaktuálnu kópiu.

Prejav: heslo sa zmenilo, ale meno, authorities aj odobraná rola sa **ticho
vrátili** do pôvodného stavu. `finish` vrátil `success`, v logu nič.

Platí to aj vnútri jedného cyklu: `assignRole`/`removeRole` vracajú
aktualizovaného používateľa a je potrebné použiť **ten vrátený**, nie ten, ktorý
sa im podal.

Pravidlo: primitíva na zmenu účtu berú `userId` a účet si načítajú samy.

### B20. `change <pole> options { }` v `create` udalosti prípadu sa neuchová

→ `ENGINE_ISSUES.md` **E4**. Zmena z `create` udalosti sa zahodí bez slova.

Na čerstvo založenom prípade sú `options` toho poľa **prázdne**. Overené:
prípad založený cez `POST /api/workflow/case` má po `create` akcii, ktorá
options nastavuje, `options: {}`.

Prečo to väčšinou nevidno: rovnaká akcia býva aj v `assign` udalosti prechodu,
a hocikto, kto úlohu otvorí, si ju priradí — takže options sa doplnia a vyzerá
to, že to funguje. Praskne to až vtedy, keď hodnotu do poľa zapíše **niekto
zvonka** cez `setData(transition, case, map)` z akcie inej siete: to úlohu
nepriraďuje, `assign` udalosť nebeží a hodnota ide do poľa bez možností.

Engine ju potom odmietne a request skončí na **500**:

```
Could not parse value of field [pu_authority], value [[ROLE_ADMIN, ROLE_USER]]
```

Pravidlo: **možnosti nastavuj tam, kde zapisuješ hodnotu**, nie v `create`.

### B21. `assignPolicy=auto` na zdieľanej úlohe priradí úlohu tomu, kto ju vyrobil

A pri `bootstrapCase` je to `engine@netgrif.com`. Všetci ostatní potom na
`finish` dostanú:

```
User that is not assigned tried to finish task
```

Auto-priradenie je pre **osobné** úlohy jedného aktéra. Na pult, prepážku alebo
frontu, ktorú obsluhuje každý s príslušnou rolou, patrí `manual`: úloha čaká
nepriradená, kto ju otvorí, ten ju má, a po `finish` slučka vyrobí novú —
zase nepriradenú.

**A `cancel` sa v takom prípade nesmie zakázať.** `cancelTask` vracia tokeny
a úlohu **uvoľní** — nezruší ju ani nezmaže. Zákaz `cancel` znamená, že raz
priradenú úlohu nemá kto pustiť. Zrušiť ju smie len jej držiteľ, alebo
`ROLE_ADMIN`, ktorého `canCallCancel` prepustí cez `isAdmin()`.

### B22. `immediate` na `multichoice_map` s runtime možnosťami zhodí indexáciu

→ `ENGINE_ISSUES.md` **E5**. NPE v `collectTranslations` na možnosti bez prekladu.

```
ERROR WorkflowService : Indexing failed [<caseId>]
java.lang.NullPointerException
  at ElasticCaseMappingService.collectTranslations(ElasticCaseMappingService.java:182)
  at ElasticCaseMappingService.transformMultichoiceMapField(...)
```

Mapper očakáva na možnostiach preklady, ktoré možnosti nastavené za behu
(`change ... options`) nemajú. Prípad sa uloží, ale **neindexuje** — takže
z Elasticu zmizne a v zoznamoch ho nevidno.

`immediate` má na poli zmysel len vtedy, keď ho naozaj potrebuješ ako stĺpec
alebo na vyhľadávanie (RUNBOOK 4). Na `multichoice_map` s dynamickými
možnosťami ho nedávaj.

---

### B23. Tlačidlo úlohy sa dá premenovať a prázdnym titulkom skryť

Titulok udalosti sa **posiela klientovi a prekladá sa**. (V tomto katalógu
najprv stálo, že sa neposiela; bolo to zmerané na sieti, ktorá žiadny titulok
nedefinovala — `ENGINE_ISSUES.md` E3.)

```xml
<event type="finish">
    <id>zd_podat</id>
    <title name="zd_podat_title">Podať žiadosť</title>
</event>
```

V payloade tasku sú štyri kľúče — `assignTitle`, `cancelTitle`,
`delegateTitle`, `finishTitle` — a knižnica pri chýbajúcom titulku spadne na
globálny i18n kľúč (`tasks.view.finish` atď.). Kľúč v payloade **chýba**, keď
titulok nie je nastavený; to nie je dôkaz, že ho server neposiela nikdy.

Druhá polovica, ktorá nie je nikde napísaná: **prázdny titulok tlačidlo skryje.**

```xml
<event type="delegate">
    <id>zd_bez_delegovania</id>
    <title name="zd_delegate_title"></title>
</event>
```

`canFinish()` a spol. sú `hasPermission(...) && getXTitle() !== ''`, takže je to
spôsob, ako z panela odobrať `delegate` alebo `cancel` bez zásahu do oprávnení —
a hlavne bez toho, aby sa tým zmenilo, čo používateľ smie. Jediná výnimka je
`canReassign()`, ktorý titulok nekontroluje.

Ako to zapadá do dvojjazyčnosti: `<title name="…">` je preložiteľný ako každý
iný, takže „Podať" / „Submit" je jeden riadok v bloku `<i18n>`. Prázdny titulok
potrebuje prázdny preklad v každom jazyku, inak sa tlačidlo v druhom jazyku
vráti.

### B24. Bez `Accept-Language` odpovedá engine v jazyku JVM, nie default hodnotou

Intuícia hovorí, že bez hlavičky sa vráti to, čo je v XML. Nevráti.

```java
public String getTranslation(Locale locale) {
    if (locale == null) return defaultValue;
    return getTranslation(locale.getLanguage());      // translations.getOrDefault(...)
}
```

Spring `Locale` z požiadavky bez hlavičky **nie je `null`** — je to locale JVM.
Na tomto stroji `en`, takže engine vráti anglický preklad. Namerané na
`/api/petrinet/{id}/roles`:

| `Accept-Language` | `name` |
|---|---|
| (žiadna) | `User administrator` |
| `sk` | `Správca používateľov` |
| `en` | `User administrator` |
| `zz`, `und`, `qq-QQ`, `x-default` | `Správca používateľov` |

**Dôsledok pre nástroje a testy:** čokoľvek, čo porovnáva reťazec z modelu
s lokálnym XML, musí locale **pripnúť** — a nie na `sk`, lebo to predpokladá,
že default hodnota je slovenská. Pripnúť treba **neznámy jazyk**: `getOrDefault`
potom spadne na `defaultValue`, teda presne na to, čo je v XML, bez ohľadu na
to, akým jazykom je napísané.

```python
req.add_header("Accept-Language", "zz")     # => defaultValue
```

Ako sa to prejavilo: `pfseed` páruje procesné role podľa názvu. Po doplnení
prekladov prestalo párovanie sedieť, `pfseed` ohlásil „cieľový stav platí"
a rolu z najnovšej verzie siete nikomu nepridelil. Prihlásenie fungovalo, karta
appky bola vidno, len zoznam úloh bol prázdny. Zachytil to `pucheck.py`.

Platí to aj naopak: appka, ktorá vyzerá anglicky bez toho, aby si to niekto
zapol, nie je pokazená — len klient neposiela hlavičku. V portáli ju posiela
`TranslateInterceptor` knižnice.

### B25. Read-only pohľad na celý život prípadu: miesto, ktoré nikto nekonzumuje

B8b hovorí, kam read arc **nevešať**. Toto je, kam ho vešať.

Zadávateľ po podaní typicky nemá čo robiť — pri štvorech očiach ho appka
zo schvaľovateľov priamo vylučuje. Nemá teda **žiadnu** úlohu, a tým ani kde
prečítať, v akom stave jeho prípad je. Vyzerá to, že sa podanie nepodarilo.

Riešenie je jedno miesto navyše:

```xml
<place>
    <id>p_info</id>
    <tokens>1</tokens>          <!-- žetón od založenia prípadu -->
</place>
<arc>
    <type>read</type>           <!-- číta, nekonzumuje -->
    <sourceId>p_info</sourceId>
    <destinationId>t_stav</destinationId>
</arc>
```

`p_info` **nie je vstupom žiadneho prechodu**, takže:

* úloha `t_stav` je povolená od založenia po uzavretie prípadu,
* odmietnuté `finish` na inom prechode ju nezmaže (to je celé B8b),
* `assignPolicy=auto` + prázdne titulky udalostí z nej spravia obrazovku bez
  tlačidiel — číta sa, neklikáte.

Do formulára patrí stav (`enumeration_map`, teda preložiteľný), priebeh
(história) a pole „u koho to leží". To posledné nesie **mená ľudí**, nie rolu:
`text` pole je `String`, ktorý sa neprekladá, takže „riaditeľ" by v anglickom
portáli bolo jediné slovenské slovo v zozname. Mená sú jazykovo neutrálne
a použiteľnejšie — dá sa zavolať.

Overené na schvaľovaní faktúr; `sccheck` to drží krokom 16b.


### B26. Opakované položky (riadky objednávky): JSON je zdroj pravdy

Petriflow nemá opakovanú skupinu polí. „Tri položky objednávky" sa teda
nemodelujú ako tri polia, ale takto:

| pole | typ | úloha |
|---|---|---|
| `_polozky_json` | `text` (skryté) | **zdroj pravdy** — serializovaný zoznam |
| `_polozky` | `text`, `textarea` | vyrenderovaný, čitateľný výpis |
| `_polozky_vyber` | `multichoice_map` | výber na odobranie, možnosti sa stavajú za behu |
| `btn_pridat` / `btn_odobrat` | `button` | akcie nad JSON-om |

Prečo nie iba renderovaný text: parsovať späť to, čo ste práve naformátovali pre
človeka, je zdroj tichých chýb (čiarka v názve položky). Prečo nie iba JSON: ten
zas človek v zozname neprečíta. Obe polia sú lacné, rozchodiť sa nemôžu, lebo
render beží vždy po zmene JSON-u.

Dve veci, ktoré sa inak vymyslia zle:

* **Id položky** je počítadlo (`p1`, `p2`, …) uložené v JSON-e, nie index v poli.
  Po odobraní prostrednej položky by sa indexy posunuli a `multichoice` by
  odobral inú položku, než človek vybral.
* **Súčet** sa prepočítava aj v `finish` (phase `pre`), nielen pri pridaní.
  Inak stačí, aby posledná zmena prišla bez re-renderu, a suma prípadu je iná
  než súčet položiek — bez chyby.

Kľúče `multichoice_map` nesmú obsahovať `.` ani `$` (Mongo, C17).


### B27. Konfiguračná appka: `bootstrapCase` na verziu + jednoúlohové zobrazenie

Limity, schvaľovatelia stredísk a podobné veci nepatria do XML natvrdo — mení
ich zákazník, nie nasadenie. Vzor, ktorý funguje:

1. Sieť `nastavenia/xx_nastavenia` s **jedným** prechodom, ktorý má `read` arc
   z miesta so žetónom (B8) — trvale otvorený „pult".
2. `{"net": "...", "rebuildOnNewVersion": true}` v manifeste: jeden prípad na
   verziu siete, takže nová verzia konfigurácie sa naozaj prejaví.
3. Hodnoty číta ktorákoľvek iná sieť cez `najnovsiCase("nastavenia/xx_nastavenia")`
   a `?.dataSet?.get("...")?.value`, s rozumným defaultom keď konfigurácia
   ešte neexistuje.
4. Karta v menu je zobrazenie typu **Task**, nie Case — otvorí rovno formulár.
   Jeho dopyt **nesmie** stáť na `processIdentifier` (task dokument ho nemá):
   `transitionId:"t_xx" AND processId:"<stringId tej verzie>"`.

Prečo `najnovsiCase` a nie `findCase`: verziu siete určuje engine
(`getNewestVersionByIdentifier`). Vlastné porovnávanie verzií padlo na tom, že
`versionKey` vracia `List` a Groovy dva `ArrayList`y porovnať odmietne — akcia
spadla a konfiguračný prípad sa prestal zakladať. Chyba bola vidno až tak, že
obrazovka nastavení bola prázdna.

## C. Mimo Petriflow, ale stálo to čas

### C1. Groovy nekontroluje volania metód pri kompilácii

`mvn compile` overí len importy a staticky typované deklarácie. Chybný názov metódy
na cudzej knižnici prejde a padne za behu. Pri externých závislostiach sa vyplatí
overiť podpisy cez `javap` proti stiahnutému jaru — trvá sekundy.

Takto sa odhalilo, že `RefusalStopDetails.category()` vracia `Optional`, takže by sa
do reportu vypísalo `Optional[cyber]`.

### C2. Anthropic Java SDK je nekompatibilné s NAE 6.3.1

SDK 2.34.0 je skompilované proti Kotlin stdlib 1.8+, Netgrif so Spring Bootom 2.x
pinuje 1.6.21. Kompilácia prejde, request odíde, **deserializácia odpovede padne** na
`NoClassDefFoundError kotlin/jvm/optionals/OptionalsKt`.

Voľby: zdvihnúť `<kotlin.version>` na 1.9.x (stdlib je binárne spätne kompatibilný,
ale mení sa pod celou platformou), alebo volať Messages API priamo cez HTTP. Zvolili
sme druhé — jeden POST, žiadna nová závislosť.

### C3. Maven si cachuje zlyhané stiahnutie

Pri prerušovaných TLS chybách vytvorí `.lastUpdated` značky a pokus **neopakuje**, ani
pri ďalšom builde. Vyzerá to ako trvalá chyba. Samotné `-U` nemusí stačiť:

```bash
find ~/.m2/repository -name "*.lastUpdated" -delete && mvn -U -DskipTests install
```

Pozor aj na scope: `runtime` závislosti `mvn compile` nepotrebuje, takže úspešná
kompilácia nezaručí úspešný `install`.

### C4. Telo `POST /api/task/{id}/data` je zanorené pod id tasku

Nie `{"pole": {...}}`, ale `{"<taskId>": {"pole": {...}}}`. Ploché telo vráti
`Could not find task with id [pole]` — endpoint prvý kľúč zoberie ako id tasku.

Import siete berie `releaseType` ako **form field**, nie ako JSON `meta`:

```bash
curl -X POST .../api/petrinet/import -H "X-Auth-Token: $T" \
  -F "file=@net.xml" -F 'releaseType=major'
```

`-F 'meta={"releaseType":"major"};type=application/json'` skončí na
`No enum constant VersionType.{"RELEASETYPE":"MAJOR"}`.

`POST /api/user/{id}/role/assign` berie **čisté pole** id (`["a","b"]`), nie
`{"roleIds":[...]}` — a **prepisuje** celý zoznam, nepridáva. Pri re-importe siete sa
razia nové id rolí, takže po každom importe treba role prideliť znova; v produkcii to
problém nie je, tam sa sieť neimportuje 11-krát za hodinu.

---

## D. Doplnené do príručky — HOTOVO

Týchto päť zistení už je v `petriflow_reference.md`:

| zistenie | kde v príručke | forma |
|---|---|---|
| **B2** button nevidí textové pole | nové **C16** | nové kritické pravidlo s XML aj Groovy ukázkou |
| **B1** bodka v kľúči mapy | nové **C17** | nové kritické pravidlo so slug riešením |
| **B3** nové polia sa nepropagujú | nové **C18** | nové kritické pravidlo + výklad chybovej správy |
| **A1** `workspace` na single-tenante | prepísaná **gotcha 34**, **gotcha 21** v druhej tabuľke, **gotcha 39**, riadok CHECKLIST/IPC | oprava nesprávneho tvrdenia |
| **A4** `getFieldValue` padá | prepísaná **gotcha 33** | oprava nesprávneho tvrdenia |

Prečo práve tieto: prvé tri sa **nedajú uhádnuť z kódu ani z chybovej správy** a každé
stálo aspoň jedno kolo ladenia. Druhé dve príručka tvrdila nesprávne, takže jej dodržanie
viedlo k chybe — to je horšie než chýbajúca informácia.

Pri oprave gotcha 34 som zladil aj **gotcha 39**: pôvodne uvádzala odvodenie prefixu len
ako výnimku pre anonymný kontext a používala odčítanie
(`pid - pid.split("/").last()`), ktoré sa rozbije, ak sa id procesu v ceste vyskytne
dvakrát. Teraz odkazuje na `lastIndexOf("/")` z gotcha 34.

### Nedoplnené a prečo

Zvyšné zistenia z častí A a B v príručke **nie sú** — dajú sa vyčítať z
`ticket_vacation.xml` (`immediate`, `<desc>`, `<properties>`, `make ... on transitions`,
preťažovanie funkcií) alebo sú len odvodené a neoverené. Doplniť ich do referenčnej
príručky by znamenalo vydávať domnienky za pravidlá.

Výnimka, ktorá by si doplnenie zaslúžila, keď sa overí: **B7** (ikonu buttonu sa z akcie
zmeniť nedá, takže jednotlačidlový prepínač neprepne strelku) — to je reálne obmedzenie,
len sme netestovali všetky tri varianty riešenia.

---

## E. Kde skončila ktorá kopa

Rozdelenie nie je poriadkumilovnosť. Tieto dve kopy majú **iného adresáta a inú
životnosť**, a kým boli v jednom súbore, čítalo sa to ako jeden dlhý zoznam
dôvodov, prečo si dávať pozor — takže sa podľa toho nedalo nič urobiť.

| | druhá kopa (tu) | prvá kopa (`ENGINE_ISSUES.md`) |
|---|---|---|
| čo to je | správanie, ktoré platí | defekt oproti vlastnému modelu |
| adresát | kto na platforme stavia | kto platformu vyvíja |
| životnosť | trvalá | zanikne opravou |
| čo s tým | naučiť sa, dať do príručky, dať do `pflint` | nahlásiť s reprodukciou |

**V prvej kope je 14 záznamov** (E1–E14). Štyri z nich sú aj tu, lebo dokým
oprava nie je, treba ich obchádzať: E1 (`removeRole`, tu B18), E4 (`change
options` v `create`, tu B20), E5 (`immediate` na `multichoice_map`, tu B22),
E8 (read arc na konzumovanom miesta, tu B8b) a dve podčasti E6/E7 v B15.

Zvyšok prvej kopy sa tu nikdy neobjavil, lebo to nie sú pasce Petriflow —
sú to chyby vrstiev pod ním a nájdete ich v `FRONTEND_LEARNINGS.md`,
`RUNBOOK.md` alebo len v tomto commite: Task zobrazenia obchádzajú vlastné
komponenty appky, titulky udalostí sa nedostanú ku klientovi, `password`
komponent posiela base64 bez serverového protikusu, `GET /api/task/case/{id}`
neoveruje `view`, import vracia holé `{"status":500}`, `GET /api/auth/login`
vracia 405, sieť s diakritikou pri JVM bez UTF-8 nemá uložené XML, `PdfRunner`
asserts na relatívne cesty.

**Čo z toho vzniklo v nástrojoch.** Každý záznam z ktorejkoľvek kopy, ktorý sa
dá skontrolovať staticky, má byť pravidlo, nie odsek — inak sa naň spolieha
pamäť. Zatiaľ takto skončili B1 (`option-key-mongo`), B18 (`engine-remove-role`),
B15 (`menu-uri-unknown`) a B5 (poradie `desc`). To je stále menšina; ostatné
sa staticky skontrolovať nedajú a jediná obrana je import do bežiaceho enginu.
