# Service Desk — prvá fáza

Dve Petriflow siete: verejný viackrokový formulár a spracovanie prihláseným
operátorom. Overené za behu na Netgrif AE 6.3.1 — podanie ako anonym, triáž,
vyžiadanie doplnenia, záznam postupu, vyriešenie.

```
sd_request  (anonymousRole=true)          sd_ticket  (back-office)
  t_step1  Čo potrebujete                   t_detail   Prehľad, vždy otvorený
  t_step2  Popis situácie                    t_triage   Triáž a prevzatie
  t_step3  Kontakt a odoslanie  ──────────►  t_work     Zaznamenať postup
  t_receipt  Podané, číslo ticketu           t_pending  Vyžiadať doplnenie
                                             t_resolve  Vyriešiť
```

Wizard je postavený na sekvencii transitions, nie na jednom formulári — každý
krok je samostatná požiadavka. Vedľajší efekt je dôležitý: pri odoslaní sú
všetky textové polia z predošlých krokov už dávno uložené, takže sa na akciu
nevzťahuje známa pasca s hodnotou textového poľa a klikom v tej istej
požiadavke.

---

## Rozbeh

### 1. JWT podpisový kľúč — bez neho verejný formulár nefunguje

`application.properties` má
`nae.security.jwt.private-key=file:src/main/resources/certificates/private.der`,
ale ten priečinok je v `.gitignore` a v repozitári teda nie je. Bez kľúča
backend pri starte vypíše `Error while resolving secret key` a **anonymný
prístup vracia 401** — engine nemá čím podpísať token anonymnej session.

```bash
cd etask-backend-starter
mkdir -p src/main/resources/certificates
openssl genrsa -out /tmp/jwt.pem 2048
openssl pkcs8 -topk8 -inform PEM -outform DER -in /tmp/jwt.pem \
  -out src/main/resources/certificates/private.der -nocrypt
```

V produkcii nastav vlastný kľúč cez `JWT_SIGN_CERT`. Kľúč sa nikdy
necommituje.

### 2. Nahranie sietí

```bash
TOKEN=$(curl -s -u user:pass http://localhost:8080/api/auth/login -D- -o /dev/null \
        | grep -i x-auth-token | tr -d '\r' | awk '{print $2}')
for f in sd_request.xml sd_ticket.xml; do
  curl -s -H "X-Auth-Token: $TOKEN" -F "file=@processes/$f" -F "releaseType=major" \
       http://localhost:8080/api/petrinet/import
done
```

Po každom uploade **over, že sa dá prihlásiť**. Zlyhaný import nie je atomický:
stihne vytvoriť procesné role a priradiť ich používateľovi, a osirelý odkaz
potom rozbije login na 500.

### 3. Procesné roly

Operátorovi priraď v Konzole role `agent`, `specialist` a `manager`. Pozor:
`POST /api/user/{id}/role/assign` roly **prepisuje, nie pridáva** — posielaj
vždy kompletný zoznam, inak user stratí systémovú rolu `default` a zmiznú mu
všetky zobrazenia.

---

## Odkaz na verejný formulár

Tu sa dá stratiť pol dňa. Frontend robí na parameter z URL `atob()` a výsledok
posiela ako **identifikátor procesu**, nie ako jeho stringId. Odkaz teda je:

```
https://<host>/process/<base64 identifikátora procesu>

printf 'sd_request' | base64      →  c2RfcmVxdWVzdA==
https://<host>/process/c2RfcmVxdWVzdA==
```

Keď tam dáš stringId siete alebo holý identifikátor, formulár skončí na
`TypeError: You provided 'undefined' where a stream was expected` — knižnica
sieť nenájde, vetva vráti `undefined` a `mergeMap` na tom padne.

---

## Čo sa v sieťach dá učiť

**`make ... visible` nie je `editable`.** Pole sa zobrazí, ale needituje sa a
hodnota sa neuloží. Ak je zároveň `required`, transition sa nedá dokončiť a
nikde nie je chybová správa. Toto stálo jedno kolo ladenia na poli „Prečo ste
prioritu zmenili".

**`textarea` nie je typ dát, ale komponent.** Správne je
`<data type="text">` s `<component><name>textarea</name></component>`. Typ
`textarea` zhodí import na `NullPointerException` v `FieldFactory`.

**Case založí anonym len s právom v `caseLogic`.** `createCase` v akcii beží
v kontexte prihláseného používateľa, takže pri podaní z verejného formulára to
je anonym. `sd_ticket` má preto na úrovni procesu
`<roleRef><id>anonymous</id><caseLogic><create>true</create></caseLogic>`.
Anonym nemá na `sd_ticket` žiadny `view` ani roleRef na transition, takže
s ticketom nič nespraví — ale **vie ich zakladať**, čo je spamovacia plocha.
Rate limiting na verejný formulár je nutnosť, nie vylepšenie.

**`phase="pre"` na finish evente je tu lepšia než `post`.** V `post` sa
potvrdenie vykreslí prázdne, lebo posledný task vznikne skôr, než akcia zapíše
číslo ticketu. A v `pre` sa formulár neposunie na „Podané", keď sa ticket
nepodarí založiť.

**Notifikácia nesmie zhodiť transition.** `sendEmail` bez nakonfigurovaného
SMTP vyhodí výnimku a zruší celú akciu. Volanie je preto v `try/catch`
a zlyhanie sa zapíše do `tk_worklog`, kde ho operátor uvidí. `log` sa v akcii
nepoužíva — jeho dostupnosť v Groovy bindingu nie je overená.

---

## SLA v tejto fáze

Lehota odozvy sa počíta v procesnej funkcii `business_deadline` — pracovný čas
Po-Pi 08:00-16:00, priorita A/B/C = 2/4/8 hodín. Overené na reálnom prípade:
podané štvrtok 15:10, priorita B, do 16:00 zostáva 49 minút, zvyšných 191 minút
padne na piatok od 08:00 → **21.08. 11:11**. Sedí.

Čo tu **nie je** a patrí do backendovej služby s kalendárom:

- sviatky
- lehoty v pracovných dňoch (neutralizácia, trvalá oprava)
- „do konca nasledujúceho pracovného dňa" — nie je trvanie, ale okamih
- odčítanie pauzových intervalov od lehôt (teraz sa pauza len sčítava do
  `sla_pause_minutes`, ale od termínu sa neodpočítava)
- matica lehôt ako dáta v sieti `sla_policy`, aby sa dala meniť bez nasadenia
  novej verzie siete

Polia na tickete sú zámerne **fakty, nie stopky**: `sla_created_at`,
`sla_accepted_at`, `sla_pause_from`, `sla_pause_minutes`. Termíny sa
dopočítavajú, takže zmena politiky ani priority nevyžaduje migráciu dát.

---

## Čo ešte nie je hotové

- **Katalóg požiadaviek** — typy sú zatiaľ `options` v sieti, nie casy.
- **Portál pre zákazníka** — zákazník svoj ticket po odoslaní nevidí. Číslo
  ticketu dostane v potvrdení, ďalej nemá kde pozerať stav.
- **Príloha z formulára** sa neprenáša do ticketu, iba text.
- **Rate limiting a captcha** na verejnom formulári. Anonym vie `sd_ticket`
  zakladať, takže je to spamovacia plocha.
- **Sviatky a kalendár** v SLA (viď vyššie).
- **Kaskáda `c_agents` do existujúcich ticketov** — keď sa u zákazníka zmení
  tím, staré tickety si nesú pôvodné `tk_agents`. Prepnutie zabezpečí až
  `tk_org_override` alebo nová verzia s prepočtom.

---

## sd_intake — jeden task, vnorené formuláre, stepper

Novšia verzia vstupu. Rieši výčitku, že v `sd_request` musel užívateľ klikať
DOKONČIŤ, aby sa dostal na ďalší krok — tam bol totiž každý krok samostatná
transition, takže posun vpred bol dokončenie tasku.

```
p_alive (tokens=1)
  ──read──► t_form         plášť: stepper, taskRef, Späť / Pokračovať / Odoslať
  ──read──► t_s_category   karty kategórií
  ──read──► t_s_detail     popis
  ──read──► t_s_contact    kontakt
  ──read──► t_s_summary    súhrn, read-only
  ──read──► t_s_receipt    potvrdenie s číslom ticketu
```

**Užívateľ vidí jediný task.** Podformuláre majú `system` roleRef, takže
sa v zozname taskov anonymovi nezobrazia — ale cez `taskRef` sa vykreslia
a **sú editovateľné**. To bolo hlavné neznáme miesto návrhu a je overené:
anonym do vnoreného poľa napíše a hodnota sa uloží.

**Prepínanie krokov je zmena hodnoty `taskRef`**, nie pohyb tokenu. Akcia
tlačidla nájde task ďalšieho kroku, priradí ho a zapíše jeho id do `inner`.
Žiadne DOKONČIŤ, a Späť funguje rovnako v druhom smere.

Prečo to nepotrebuje kopírovanie dát: **všetky tasky jedného casu zdieľajú
dataSet**, takže podformuláre sú len rôzne pohľady na tie isté polia. Preto
sa pri kroku späť nič nestratí.

### Čo si to vynútilo

**Validácia musí byť v akcii.** Keď zmizne DOKONČIŤ, engine prestane
vynucovať `required` — nič ho nespúšťa. Kontrola je preto v akcii tlačidla
Pokračovať a pri chybe zapíše text do `wiz_error` a krok nezvýši.

**Textové polia potrebujú `immediate="true"`.** Inak posielajú hodnotu až pri
strate fokusu, čo je ten istý okamih ako klik na Pokračovať, a validácia by
čítala prázdno. S `immediate` je hodnota na serveri už počas písania. Je to
tá istá pasca ako B2 v `PETRIFLOW_LEARNINGS`, len z druhej strany.

**Viditeľnosť navigácie treba prepínať pri každom kroku.** Bez toho svieti
Späť na prvom kroku a Odoslať na každom:

```groovy
make btn_back, hidden on transitions when { return target <= 1 }
make btn_next, hidden on transitions when { return target >= 4 }
make btn_submit, editable on transitions when { return target == 4 }
```

**`system` sa musí deklarovať ako `<role>`**, na rozdiel od `anonymous`
a `default`, ktoré sú vstavané. Bez deklarácie padne import na
`IllegalArgumentException: Role system not found`.

**Karty sú buttony.** `stroked` s `stretch=true`, názov karty v `<title>`
a text tlačidla v `<placeholder>`. Typ `icon` sa nedá použiť — vtedy
knižnica text tlačidla skryje a nechá len glyf.

### Známy nedostatok

Knižničný footer panelu stále ukazuje **ZRUŠIŤ a DOKONČIŤ**. Kliknutie na
DOKONČIŤ je neškodné — `t_form` visí na read arcu, takže sa token nekonzumuje
a task sa hneď znovu otvorí — ale je to zmätočné. Odstránenie je zmena vo
frontende (footer panelu), nie v sieti.

Verejný odkaz je `printf 'sd_intake' | base64` → `/process/c2RfaW50YWtl`.

---

## Druhá fáza — úlohy pre zamestnancov a viditeľnosť

```
sd_customer                sd_ticket                     sd_work_item
  t_customer   (manager)     t_triage  (tk_agents)          t_define   (agent/manager)
  t_customer_read            t_plan    (tk_agents)  ──────►  t_wi_work  (wi_assignee)
    (agent/specialist)       t_detail  (tk_*)         ◄────── hlásenie do wi_report
                             t_work / t_pending / t_resolve
sd_menu                        (tk_agents + tk_specialists + manager)
  postaví zobrazenia nad uzlom URI `service_desk`
```

### Rola AND organizácia

`roleRef` a `userRef` sa v Petriflow **zjednocujú, nie prienikajú** — „agent
a zároveň pridelený tomuto zákazníkovi" sa deklaratívne napísať nedá. Model to
obchádza tak, že rolu presunie do dát:

* zákazník má dva zoznamy ľudí — `c_agents` a `c_specialists`,
* tiket si ich pri príchode `src_org` z eformu skopíruje ako `tk_agents`
  a `tk_specialists`,
* case-level `view` a všetky transition-y odkazujú **len na tieto zoznamy**;
  rola sama už právo vidieť tiket nedáva.

Rola tak hovorí, *v ktorom* zo dvoch zoznamov človek u zákazníka je, zákazník
*ktorý* zoznam to je. `roleRef manager` zostal jediná globálna rola — vedúci
vidí všetko, inak by tiket od neznámej organizácie nemal komu patriť.

Overená matica (tri tikety dvoch zákazníkov, päť užívateľov):

| užívateľ | rola | Netgrif | Alfa | bez zmluvy |
|---|---|:-:|:-:|:-:|
| super | manager | ✓ | ✓ | ✓ |
| admin | agent oboch zákazníkov | ✓ | ✓ | — |
| operator | specialist Netgrifu | ✓ | — | — |
| druhy | specialist Alfy | — | ✓ | — |
| viewer | bez SD roly | — | — | — |

Nespárovaná organizácia nie je tichá chyba: `tk_org_match` napíše prečo, tiket
vidí iba vedúci, a `tk_org_override` ho dá priradiť ručne.

### Pracovná úloha

`t_wi_work` má **len `userRef wi_assignee`**, žiadnu rolu — práve to robí zo
zoznamu „Moje úlohy" moje. Rola `specialist` by dala prístup ku všetkému.

Cross-case prenos ide cez `setData`, a **poradie v mape nie je kozmetika**: set
eventy sa spúšťajú postupne, takže kontext tiketu musí byť zapísaný skôr, než
`wi_title` prepíše názov casu, a `wi_assignee_id` (ktoré naplní userList) až
nakoniec. Prečo cez text a nie priamo userList: `setData` z iného casu čaká
zoznam id, ale hodnota userList poľa je `UserListFieldValue`.

Po dokončení úloha hlási späť do tiketu (`report_to_ticket`): zníži `wi_open`
a pripíše výsledok do `wi_report`. Bez toho by `t_resolve` navždy odmietal
uzavrieť požiadavku, aj keby bola všetka práca hotová.

### SLA zo zmluvy

`contract_sla_hours(tk_customer_id, priorita)` prečíta `c_sla_a/b/c`
zo záznamu zákazníka a padá na štandardnú maticu, keď tam nič nie je. Overené:
Netgrif má pre prioritu B dohodnutých 6 h, tiket podaný 07:36 dostal termín
14:00 — nie 12:00, čo by dalo štandardné 4 h.

### Menu

Karta v bočnom menu je len priečinok; zobrazenia sú casy procesov `filter`
a `preference_filter_item`. Kým nevzniknú, karta nevedie nikam — a po sprísnení
oprávnení bol *General → All cases* jediný zoznam v aplikácii, takže operátor
ani riešiteľ nemali k svojim tiketom v UI cestu vôbec.

Stavia ich sieť `sd_menu` (Tikety, Moje úlohy, Zákazníci, Podania z formulára),
lebo `createFilterInMenu` žije na action delegate a z runnera sa nedá zavolať.
`SdMenuRunner` len zabezpečí, že jeden case tej siete existuje. Idempotentné
dvakrát: runner preskočí existujúci case, sieť preskočí zobrazenie so zhodným
dopytom — a keď sa dopyt zmenil, položku zahodí a postaví znova. Výsledok je
v **názve casu** (`Menu Service Desku – 4/4`), nie v dátovom poli: po
`createFilterInMenu` sa zápis do vlastného casu neuchová.

Detaily API a pasce sú v `PETRIFLOW_LEARNINGS` B15 (poradie argumentov, rozbitá
update cesta, uzly URI v Elasticsearch) a B16 (rola vs. userRef pri re-importe).

### Rozbeh druhej fázy

Siete sú registrované v `NetRunner.PetriNetEnum` a berú sa priamo
z `etask-configuration/processes` (viď `<resources>` v `pom.xml`), takže čisté
prostredie ich naimportuje samo a `SdMenuRunner` postaví menu. Ručne treba len
priradiť roly a založiť zákazníkov.

Pozor pri vývoji: `NetRunner` sieť importuje **len keď chýba**. Po zmene siete
ju treba nahrať znova (Nahrať proces / `POST /api/petrinet/import`), inak beží
stará verzia. A po re-importe treba znova priradiť procesné roly — role majú
stringId razené per verzia.
