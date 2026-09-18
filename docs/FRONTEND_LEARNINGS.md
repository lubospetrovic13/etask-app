# Čo treba vedieť o `@netgrif/components` na frontende

Zistené počas úprav UI/UX na Netgrif Platform 6.3.1 / Angular 13.3.1. Sesterský dokument
k `PETRIFLOW_LEARNINGS.md`. Rovnaké rozlíšenie zdrojov:

- **Za behu** — odmerané v bežiacej prihlásenej aplikácii
- **Zo zdrojov** — prečítané v knižnici alebo v engine, nie potvrdené za behu
- **Odvodené** — najlepšie vysvetlenie faktov, nedokázané

---

## A. Ako sú knižnice zapojené

`@netgrif/components` a `@netgrif/components-core` sú **npm závislosti z verejného registry**,
presne pinnuté na `6.3.1` (bez `~`/`^`). Žiadne monorepo, žiadny submodule, `projects/`
neexistuje. Sú to Angular Package Format balíky — šablóny sú skompilované do `.mjs`.

**Priamo sa meniť nedajú.** Zmena v `node_modules` prežije do prvého `npm ci`.

### A1. Zdroj knižnice sa dá prečítať zo sourcemapov

Oba balíky majú v `esm2020/**/*.mjs` **inline sourcemapy s kompletným `sourcesContent`** —
teda originálne `.ts` aj `.html`. To je jediný spôsob, ako čítať šablóny, a šetrí to hodiny
hádania.

```bash
node tools/extract.js <fe>/node_modules/@netgrif/components/esm2020 \
                      <fe>/node_modules/@netgrif/components-core/esm2020  out/
```

Vytiahne ~1094 súborov. SCSS tam **nie je** (styly sú skompilované do CSS v `.mjs`) — na to
je `tools/css-of.js`, ktorý vyparsuje `styles: [...]` z APF balíka.

### A2. Téma je jediný update-safe seam

`@netgrif/components` **posiela SCSS ako zdroj**: `nae-theme.scss`, `nae-typography.scss` a
19 partialov v `src/lib/`. Appka ich už používa:

```scss
@import 'node_modules/@netgrif/components/nae-theme';
@include nae-lib-theme($theme, $typography);
```

Všetko, čo ten mixin generuje, sú **globálne** pravidlá, takže sa dajú prepísať zvonku.
Toto je vrstva, ktorá prežije update knižnice — na rozdiel od zmien v šablónach.

Pozor: `side-menu.theme.scss` **nie je** importovaný v `nae-theme.scss`, ale
`nae-typography.scss:1` ho importuje, takže `side-menu-theme` mixin existuje. `dialog.theme.scss`
a `snack-bar.theme.scss` sa neincludujú vôbec — dialógy a snackbary majú len Material default.

*Za behu.*

---

### A3. Dátové pole sa ukladá na blur kvôli jednému riadku

`AbstractDataFieldComponent` vytvára `new FormControl('', {updateOn: 'blur'})`.
Celá ukladacia reťaz pod tým je na zmenu pripravená — `field.valueChanges()` →
`updateTaskDataFields()` → `POST /task/{id}/data` beží okamžite. Hodnota len do
blur neopustí input.

Prakticky to znamená dve veci:

* **Nedá sa to prepnúť konfiguráciou.** `_formControl` je privátne pole
  knižničnej triedy, injection token (na rozdiel od
  `NAE_INFORM_ABOUT_INVALID_DATA`) preň neexistuje.
* **Dá sa to obísť bez kopírovania šablón**: `input` udalosť z knižničného
  `<input>` bubbluje, takže náš resolver ju odchytí a hodnotu zapíše do
  `DataField.value` sám. Zvyšok cesty zostáva knižničný.

Prečo to knižnica robí na blur, je vidieť v `registerFormControl`: odpoveď
servera sa cez `_value` → `formControl.setValue()` zapisuje **späť do inputu**.
Pri ukladaní počas písania to pri poli, ktoré akcia normalizuje, preloží kurzor.
Recept aj zoznam kompromisov je v RUNBOOK 6.

### A4. `instanceof` proti knižničnej triede v produkčnom builde neplatí

Kontrola typu poľa cez `field instanceof TextField` sa skompiluje, prejde revíziou
a v produkčnom builde **ticho odpovie `false`** — funkcia potom nerobí nič a nikde
nie je chyba. Namerané v prehliadači na bežiacej appke:

```js
field.constructor.name     // "E4e"   - minifikované
'type' in field            // false   - DataField `type` za behu nemá
```

Zdroj pravdy o type poľa je **`getElementType()`** na resolveri — to isté, na čom
stojí `ngSwitch` v jeho šablóne. Preto `TYPABLE.includes(this.getElementType())`
a nie `instanceof`.

Stálo to jeden cyklus rebuildu obrazu: kód sa skompiloval, nasadil, a pole
s `saveWhileTyping` sa jednoducho neukladalo. Odhalila to až kontrola hodnoty
v Mongu (`req_description = undefined`) po písaní bez odkliknutia.

## B. Kaskádové pasti — najdrahšia časť

### B1. Dark scope re-emituje knižničné pravidlá s vyššou špecificitou

Runtime prepínanie témy sa robí emitovaním témy dvakrát: light nescopeovane, dark pod
`.app-dark`. To znamená, že **každé knižničné pravidlo má v dark režime `.app-dark` dvojča
so špecificitou +1 trieda**.

Override so špecificitou 0,2,0 preto v light vyhrá a v dark **prehrá** proti 0,3,0.

Riešenie: override-y, ktoré bojujú s témou, dať do mixinu a emitovať ich dvakrát — raz
nescopeovane, raz pod `.app-dark`. Viď `app-theme-overrides` v `src/styles/_overrides.scss`.

*Za behu — prvá verzia opravy `<desc>` fungovala v light a nie v dark, presne z tohto dôvodu.*

### B2. Knižničné `background` shorthandy s `!important` resetujú `background-image`

`panel.theme.scss` má:

```scss
.panel-color:hover { background: <primary> !important; color: white !important; }
```

`background` je **shorthand**, takže nastavuje aj `background-image: none !important`. Ak sa
farba casu tlmí prekryvom cez `background-image`, hover ten prekryv **strhne** — a keďže
`background-color` sa medzitým ešte preleva, na jeden frame presvitne plná sýta farba.
Prejav: riadky pri hoveri „preblikávajú", a len v dark režime (kde má knižničné pravidlo
vyššiu špecificitu).

Riešenie: zopakovať prekryv **aj v hover pravidle**, aby ho nemohlo nič odstrániť.

*Za behu.*

### B3. Materialove component štýly sa vkladajú za globálny stylesheet

Material 13 komponenty majú `ViewEncapsulation.None`, ale ich CSS sa vkladá do `<head>`
ako `<style>` **až pri načítaní komponentu**, teda za globálny `styles.css`. Pri rovnakej
špecificite teda **Material vyhrá poradím**.

Prakticky: na prebitie Materialovho `.mat-tab-label` (0,1,0) treba `.mat-tab-group .mat-tab-label`
(0,2,0), nie rovnakú špecificitu.

Naopak pravidlá z `nae-lib-theme` sú v našom globálnom stylesheete, takže tam stačí rovnaká
špecificita a neskoršia pozícia.

### B4. Iba dva knižničné komponenty sú neenkapsulované

`i18n-text-field` a `search`. Zvyšok má emulovanú enkapsuláciu, takže ich natvrdo napísané
farby neuniknú mimo komponent — override zvonku ale potrebuje `!important`, lebo atribútový
selektor komponentu má rovnakú špecificitu a vkladá sa neskôr.

*Zo zdrojov — grep `ViewEncapsulation` v `esm2020/lib`.*

### B5. V `fxLayout="column"` nestačí `height: 100%`, treba `fxFlex`

Zabalenie `nc-header` + `nc-case-list` do wrappera (kvôli vodorovnému posunu
v tabuľkovom režime — E23) skončilo **prázdnym zoznamom**: hlavička sa vykreslila,
dáta z API prišli, riadkov nula. `cdk-virtual-scroll-viewport` mal nameranú
**výšku 0**.

Wrapper bol skopírovaný z knižničnej šablóny, teda s `class="full-height"`
(`height: 100%`). Lenže vo flex **stĺpci** je výška hlavná os: dieťa dostane
zvyšok priestoru iba cez `flex-grow`, nie cez percentuálnu výšku, a
`fxLayoutAlign="start stretch"` na rodičovi natiahne **šírku**, nie výšku. Wrapper
sa preto zmrštil na výšku svojho obsahu (61,6 px = hlavička) a `fxFlex` na
`nc-case-list` už nemal do čoho rásť.

```html
<!-- zle: vo flex stĺpci sa zmrští na obsah -->
<div class="full-height transform-div" fxLayout="column" fxLayoutAlign="start stretch">

<!-- dobre -->
<div class="transform-div" fxFlex fxLayout="column" fxLayoutAlign="start stretch">
```

**Prečo to v knižnici funguje a u nás nie:** jej `nc-filter-field-tabbed-case-view`
má na kontajneri `min-height-custom` s **natvrdo 400 px**, takže percentá majú
sa o čo oprieť. Náš kontajner výšku dedí cez flex reťaz — a v tom momente je
`height: 100%` bez `fxFlex` ticho neúčinné. Kopírovanie knižničnej šablóny bez
jej štýlov je teda samo osebe pasca.

Diagnostika, ktorá to ukázala za pár sekúnd — nie hádanie v DevTools, ale zmeranie:

```js
document.querySelector('cdk-virtual-scroll-viewport').getBoundingClientRect().height  // 0
```

### B6. Chýbajúci endpoint v `nae.json` sa prejaví ako večne točiaci spinner

`SignUpService` si adresy skladá v konštruktore z `providers.auth.endpoints`
a pri chýbajúcom kľúči uloží `undefined`. Metóda potom **vyhodí výnimku
synchrónne**, ešte pred vytvorením Observable:

```js
resetPassword(email) {
    if (!this._resetUrl) {
        throw new Error('Reset URL is not set in authentication provider endpoints!');
    }
    return this._http.post(this._resetUrl, email).pipe(...);
}
```

Volajúci komponent zapne spinner, zavolá metódu a spinner vypína až
v `subscribe`. Ten ale nikdy nevznikne, takže:

* v sieťovej záložke prehliadača **nie je žiadny request**,
* v logu backendu **nie je žiadny záznam**,
* v Mailpite **nie je žiadny mail**,
* a obrazovka sa točí donekonečna.

Všetky štyri príznaky ukazujú na backend, pričom chyba je v jednom riadku
konfigurácie frontendu. `nae-default` dopĺňa `login`, `logout` a `signup`,
nie `reset`, `recover` ani `verify` — kto obnovu hesla zapína, musí ich
dopísať sám:

```json
"endpoints": {
  "login": "/auth/login",
  "logout": "/auth/logout",
  "signup": "/auth/signup",
  "reset": "/auth/reset",
  "recover": "/auth/recover",
  "verify": "/auth/token/verify"
}
```

Diagnostika, ktorá to odlíši od chyby backendu: zavolať endpoint priamo.
Keď `curl` mail pošle a appka nie, problém je pred requestom, nie za ním.

```bash
curl -s -X POST "http://localhost:8080/api/auth/reset"      -H "Content-Type: text/plain" -d 'niekto@example.com'
```

`Content-Type` je `text/plain`: knižnica posiela holý reťazec, nie JSON objekt.
S `application/json` vráti endpoint **415** a to je len vlastnosť sondy, nie
príčina problému.

*Za behu — hľadal som chybu v odosielaní mailov, SMTP bolo pritom v poriadku
celý čas.*

### B7. `fxLayoutGap` pridá inline `max-width: 100%` a prebije šírku zo štýlu

`fxLayoutGap` nastavuje na element **inline** `max-width: 100%` (chráni sa tým
pred pretečením o veľkosť medzery). Inline štýl vyhrá nad pravidlom zo
stylesheetu bez ohľadu na špecificitu, takže:

```scss
.auth-card {
  width: 100%;
  max-width: 420px;   // NIKDY sa neuplatní
}
```

Prejav: karta sa roztiahne na celú šírku okna. Na úzkom displeji vyzerá
správne, takže sa to nájde až na širokom monitore. V DevTools to nie je vidieť
ako prebité pravidlo — obe hodnoty sú `max-width` a tá v stylesheete sa
zobrazuje normálne.

Diagnostika, ktorá to ukáže hneď: v konzole porovnať vypočítanú hodnotu
s pravidlami, ktoré na element sedia.

```js
const el = document.querySelector('.auth-card');
getComputedStyle(el).maxWidth      // "100%"
el.getAttribute('style')           // ... max-width: 100%;
```

Riešenie bez `!important`: dať šírku na `width` a `max-width` nechať na `100%`.
Inline štýl potom nemá čo prebiť a na úzkom displeji sa karta stále zmenší.

```scss
.auth-card {
  width: 420px;
  max-width: 100%;
}
```

*Za behu — obrazovka obnovy hesla.*

---

## C. Material 13 je pre-MDC

Téma sa kompiluje do statického CSS a **nemá CSS custom properties**. Runtime prepínanie
farieb cez `var(--x)` nie je možné — preto tie dva emitované bloky (B1).

### C1. `define-dark-theme` vracia plochy dvakrát

Mapa témy má `background`/`foreground` na najvyššej úrovni **aj** pod kľúčom `color`, a
`all-component-colors` číta tú pod `color`. Sass mapy sú immutable, takže pri prepisovaní
Materialových šedých plôch na vlastné treba **patchnúť obe kópie**. Viď `app-surfaces()` v
`custom-themes.scss`.

*Za behu — overené sondou, ktorá vypísala kľúče mapy.*

### C2. `mat.core()` sa emitoval dvakrát

Appka mala legacy `mat-core()` v `styles.scss` **a** `mat.core($typography)` v téme. Overené
počtom výskytov `.mat-ripple` v skompilovanom CSS (2). Zbytočných ~14 kB.

### C3. `nae.json` `theme.pallets` je mŕtva konfigurácia

Schéma deklaruje `theme.pallets.light` aj `.dark`, ale **nič to nečíta** — grep v
`components-core` nenašiel žiadneho konzumenta okrem typov. Farby sú v
`src/styles/themes/`.

---

## D. Polia a resolver

### D1. Resolver polí je hardcoded `ngSwitch` bez registry

`FieldComponentResolverComponent` dispatchuje typy polí cez `ngSwitch`. **Žiadny registry,
žiadny injection token.** Vlastný komponent pre jediný typ poľa preto znamená vlastniť
šablónu resolvera **aj** task-contentu.

Reťaz, ktorá to umožní bez zásahu do `node_modules`:

```
EtaskTaskPanelComponent (panelContentComponent)
  → EtaskTaskContentComponent
    → EtaskFieldComponentResolverComponent
      → vlastné field komponenty
```

`panelContentComponent` je existujúci `@Input` na `AbstractTaskPanelComponent`, čítaný v
`ngOnInit`, takže default sa dá nastaviť v konstruktore.

**Cena:** nové typy polí z budúcej verzie knižnice sa v skopírovanej šablóne neobjavia.
Pole takého typu zmizne — bez chyby, bez warningu, bez stopy v konzole. `tools/pfview.py`
preto originál vytiahne z balíka v `node_modules` a porovná vetvy `ngSwitch`; kópiu nájde
podľa vety `Copy of @netgrif/components ...` v hlavičke súboru, takže tá veta nie je
komentár, ale zápis do registra.

### D2. `nc-task-list` obchádza celú tú reťaz

Najdrahšia chyba tohto vlákna. Knižničné `<nc-task-list>` renderuje `<nc-task-panel>`, a teda
knižničný task-content a knižničný resolver — **vlastné field komponenty sa nezobrazia vôbec**.

Prejav: `app-etask-boolean-field: 0`, `nc-boolean-field: 1`, hoci bolo všetko správne
zapojené. Žiadny build to neodhalí — a v čase, keď sa to stalo, ani žiadna statická
kontrola. Dnes je to `pfview` kontrola B: pravidlo je „ak projekt vlastní
`app-etask-X`, žiadna iná šablóna nesmie použiť `nc-X`", s jedinou výnimkou pre
vlastný komponent, ktorý knižničný obaľuje vo svojej vlastnej šablóne.

Komentáre sa pred kontrolou odstraňujú. Bez toho by nástroj hlásil práve ten súbor,
ktorý opravu **vysvetľuje** — a falošný poplach na dokumentácii opravy je najkratšia
cesta k tomu, aby sa výstup prestal čítať.

Miesta, ktoré na to treba skontrolovať (obe boli chybné):
- `etask-tabbed-task-view.component.html` (task view v otvorenom case)
- `side-nav-tasks-task-view.component.html`

Správne je `<app-etask-task-list>`, ktorý dedí z rovnakého `TaskListComponent`, berie tie isté
vstupy, ale renderuje `app-etask-task-panel`.

*Za behu — odhalené až prekliknutím prihlásenej appky.*

### D3. `nc-required-label` je deklarovaný, ale neexportovaný

`DataFieldsComponentModule` ho deklaruje a **neexportuje**, takže z `AppModule` sa použiť
nedá. Vo vlastných field komponentoch treba jeho markup inlinovať:

```html
<span *ngIf="dataField.behavior.required" class="required-label-color"> * </span>
```

plus `.required-label-color { color: red }`, ktorý je tiež component-scoped.

### D4. `<component>` je dostupný na každom type poľa, aj keď ho knižnica ignoruje

`field-converter.service.ts:41` posiela `item.component` do `BooleanField`, hoci knižničný
boolean komponent ho vôbec nečíta (nemá `ngSwitch` ani nesiaha na properties). To isté platí
na úrovni enginu: `FieldFactory.buildField` nastavuje `<component>` **typovo agnosticky** a
`ComponentFactory` len skopíruje názov a properties **bez whitelistu**.

Takže vlastný komponent môže varianty čítať z Petriflow:

```xml
<component>
    <name>toggle</name>
    <properties><property key="variant">section</property></properties>
</component>
```

*Zo zdrojov engine + za behu na FE.*

### D5. `DataField.component` je getter bez settera

Backing field je `_component`. Pri testovaní variantov v konzole priradenie
`df.component = {...}` **tichodržky spadne** a vyzerá to ako chyba v komponente. Zapisovať
treba do `_component`.

*Za behu — skoro som nahlásil dve neexistujúce chyby.*

### D6. Kompletný inventár `<properties>` kľúčov

| kľúč | pole |
|---|---|
| `fontSize`, `textColor`, `plainText` | i18n text |
| `dividerColor`, `dividerLGBTQ`, `fontSize` | i18n divider |
| `borderWidth/Style/Color/Enabled/LGBTQ` | file preview |
| `arrow`, `divider` | enumeration `icon` |
| `arrowStepper` | enumeration `stepper` |
| `filter` | autocomplete |
| `dialogTitle`, `dialogText` | **button — otvorí potvrdzovací dialóg** |
| `align`, `stretch` | button (na `ButtonFieldComponent`, nie na abstraktnej) |
| `code`, `fractionSize`, `locale` | number |

`align` a `stretch` sú v `netgrif-components`, nie v `-core` — grep len v core ich nenájde.

---

## E. Popisy polí (`<desc>`)

### E1. Zrezanie na jeden riadok má dve príčiny

1. `data-field.theme.scss:108` — `.netgrif-input .mat-hint { white-space: nowrap;
   text-overflow: ellipsis; overflow: hidden }`
2. Material parkuje subscript v `position: absolute` s `overflow: hidden`, v slote
   rezervovanom cez `.mat-form-field-wrapper { padding-bottom: 1.34375em }`

Obe treba prepísať, inak sa popis nezobrazí ani po oprave prvej.

### E2. `position: fixed` je vnútri poľa rozbité

Tri predkovia vytvárajú containing block:

| predok | čím |
|---|---|
| `cdk-virtual-scroll-content-wrapper` | `transform`, `contain: content` |
| `cdk-virtual-scroll-viewport` | `contain: strict` |
| `mat-tab-body-content` | `transform: translate(...)` — offset tabu |

Odmerané: fixed sonda vnútri poľa pristála na `-584,270` namiesto `100,100`. `contain: strict`
navyše orezáva.

**Dôsledok:** overlay nad formulárom (tooltip popisu) sa **musí** renderovať do
`document.body`. Riadi ho `EtaskTaskContentComponent` delegovaným hoverom, takže sa chová
rovnako pre všetky typy polí — čo v CSS nešlo, lebo popisy sedia v troch rôznych obaloch.

### E3. Čo o CSS platí a čo nie

- `-webkit-line-clamp` **funguje** — autoprefixer `display: -webkit-box` nezmazal (podozrieval
  som ho, mýlil som sa; overené v buildnutom CSS)
- Chrome reportuje `-webkit-box` s `overflow: hidden` ako `display: flow-root` — clamp pritom
  funguje. Neplašiť sa z computed hodnoty, merať výšku
- `:has()` **je podporované** a `:empty` **matchuje** aj Angularov prázdny text node
  z `{{undefined}}` (`childNodes.length === 1`, ale `:empty` platí)
- Hover na elemente, ktorý sa pri hoveri **posunie**, osciluje. Trigger musí byť element,
  ktorý sa nehýbe; `:hover` na predkovi drží, aj keď je potomok nakreslený mimo jeho boxu

---

## F. Kde knižnica používa paletu ako výplň

Toto je systémová príčina väčšiny vizuálnych problémov v dark režime:

| pravidlo | čo plní |
|---|---|
| `header.theme.scss` `.header-color` | `background: primary-500` — hlavička zoznamu |
| `panel.theme.scss` `.footer` | `background: primary-500` |
| `panel.theme.scss` `.panel-color:hover` | `background: primary !important` — celý riadok |
| `panel.theme.scss` `.line-datagroup` | `background: primary !important` — 1px linka |
| `tabs.theme.scss` `.mat-tab-label-container` | **`background: white`** natvrdo |
| `navigation.theme.scss` `.rail-color` | `primary` tón **50** — teda tón ako plocha |
| `navigation.theme.scss` `.active-rail` | `background: white` natvrdo |

`navigation-theme` používa tóny 50 a 100 ako **plochy**, nie ako odtiene. Dá sa to využiť:
dark ramp môže mať na 50/100 tmavé plochy, kým `define-palette(..., 500, 300, 700)` drží
Materialu skutočné modré.

*Zo zdrojov + za behu.*

---

## G. Merateľné hodnoty, ktoré stoja za zapamätanie

| | pred | po |
|---|---|---|
| rám editovateľného poľa | `1.05 : 1` | `3.19` dark / `3.30` light |
| rozdiel editable vs read-only | 1.05 vs 1.21 | box vs žiadny box |
| hodnota read-only poľa | `10.43 : 1` | `13.96 : 1` |
| footer panelu | 68 px | 44.8 px |
| tab | 48 px, min-width 160 | 40 px, min-width 0 |
| chrome nad prvým riadkom | ~90 px | ~20 px |

WCAG žiada **3:1 na okraje ovládacích prvkov**, nie 4.5:1 — a to je práve to, čo Materialov
outline nesplňoval o celý poriadok.

---

## H. Nástroje v `tools/`

Postavené počas vlákna, prežijú ho. Všetky sú čisté Node, bez závislostí.

| nástroj | na čo |
|---|---|
| `sassc.js` | skompiluje SCSS tak ako Angular CLI (loadPaths + `~` importer). Rýchla smyčka namiesto 60s `ng build`. Root cez `FE_ROOT=` |
| `cascade.js` | pre danú vlastnosť a selektor vypíše všetkých kandidátov so špecificitou a poradím a **povie víťaza**. Toto je jediný spôsob, ako neveriť kaskáde naslepo |
| `contrast.js` | WCAG audit `--app-*` tokenov v oboch režimoch, vrátane alfa kompozície |
| `css-of.js` | vytiahne skompilované component CSS z APF `.mjs` |
| `extract.js` | vytiahne originálne `.ts` a `.html` zo sourcemapov knižnice |

Príklady:

```bash
node tools/sassc.js <fe>/src/styles.scss out.css
node tools/cascade.js out.css white-space ".netgrif-input .mat-hint"
node tools/contrast.js out.css
```
