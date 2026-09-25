# Service Desk

Štyri Petriflow siete. Tiket podáva **prihlásený zákazník**, rieši ho **agent**
priradený k jeho organizácii, organizácie a SLA plány spravuje **správca**.
Zákazníka ani agenta nikto nezakladá ručne: správca ho pridá do organizácie
a tým mu príde pozvánka. Overené za behu na Netgrif AE 6.3.1 —
`tools/sdcheck.py`, 104 kontrol na čistej databáze.

Appka je v angličtine, slovenčina je druhý jazyk (`<i18n locale="sk">`
v každej sieti, prepínač v portáli).

```
sd_sla_plan        sd_organization                 sd_ticket                                   sd_menu
  t_plan (admin)     t_org (admin)                   t_submit (autor)            ──┐             zobrazenia
                       plán, limity                  t_my     (autor, píše)        │ read arc     + zosúladenie
                       ľudia, agenti                 t_watch  (ľudia org., číta)   │ zo sinku       rolí
                     t_org_view (agenti org.)        t_detail (agenti org., admin) ┘
                                                     t_accept / t_reject → t_resolve → t_reopen / t_close
```

| rola | kto | zobrazenia |
|---|---|---|
| `sd_customer` | ľudia klienta, pridelí ju `sd_organization` | Create New Ticket, My Tickets, Company Tickets |
| `sd_agent` | naši zamestnanci, pridelí ju `sd_organization` (alebo `seed.json`) | Triage, SLA at risk, Tickets in progress, All Tickets, My Organizations |
| `sd_admin` | správca Service Desku, `seed.json` | Triage, SLA at risk, Tickets in progress, All Tickets, Organizations, SLA Plans |

---

## SLA plán

Predajný balíček: hodiny na prvú reakciu a na vyriešenie pre každú prioritu
(critical, high, medium, low), pracovný čas (Po–Pi, od–do) a limity, za
ktoré klient platí (počet účtov, počet agentov). Lehoty na automatické
zatvorenie a zmazanie konceptu sú tu tiež (hodnota 0 = hneď).

## Organizácia a prístup

Organizácia má plán (`org_plan`, možnosti sa plnia v `assign` a tlačidlom
Refresh — v `create` by sa neuchovali, B11) a môže mu prepísať limity.

Pridanie človeka (`btn_add`):

1. **Limit.** Členovia + pozvaní sa porovnajú s limitom účtov. Pozvánka sa
   počíta ako účet — klient platí za účty.
2. **Účet.** Nový e-mail dostane pozvánku (`pozvi`), účet vznikne ako
   `INVITED`. Opakované pridanie pozvaného pošle pozvánku znova.
3. **Rola `sd_customer`** na `sd_ticket` a **členstvo** v `org_members`.

Agent (`btn_add_agent`) rovnako, ale do `org_agents`, s rolou `sd_agent`
a s limitom agentov. Odobratý agent rolu nestratí — môže mať iné
organizácie.

Človek patrí **najviac do jednej organizácie** a nemôže byť zároveň agent.
Každá zmena ľudí alebo agentov sa **kaskáduje** do existujúcich tiketov
(`recompute_tickets` → `setData("t_detail", …)`).

## Kto čo vidí

Všetko cez `userRef`, lebo ten re-import siete prežije (B16):

| čo | ako |
|---|---|
| založiť tiket | `roleRef sd_customer` → `create` |
| vidieť a písať do svojho tiketu | `userRef tk_reporter` |
| sledovať tikety organizácie | `userRef tk_org_members` (bez autora), len `t_watch` |
| riešiť tikety organizácie | `userRef tk_agents` — len tí, čo rolu `sd_agent` naozaj majú (B14) |
| všetko | `roleRef sd_admin` |

„My Tickets" je **Task** zobrazenie na `t_my`: úlohu má len autor. Case dopyt
na prihláseného človeka sa napísať nedá, filter nemá `<<me>>`.

## Dashboard a formulár z karty

Položky menu Service Desku visia priamo v **koreni** (`sd_menu`, uri
`"root"` — tak sa koreňový uzol volá). Zákazník má po prihlásení v bočnom
menu rovno Create New Ticket, My Tickets a Company Tickets. Priečinky `it`
a `it/service_desk` vznikajú z identifikátorov sietí a manifest ich ukazuje
len `ROLE_ADMIN`.

Karty dashboardu sú položky menu, nie priečinky: `assets/custom_views.json`
určuje, ktoré (`dashboard`, v tomto poradí) a v ktorých ďalších uzloch ich
hľadať okrem koreňa (`dashboardNodes`). Kto aspoň jednu kartu má, priečinky na dashboarde nevidí —
zostávajú v bočnom menu. Počítadlo počíta prípady pri Case zobrazení a úlohy
pri Task zobrazení.

Položka v `forms` (Create New Ticket) neotvára zoznam, ale formulár, na
dashboarde aj v bočnom menu:

1. `portal/form/:view` založí prípad (`FormLaunchComponent`, `replaceUrl`,
   aby Späť nezaložilo ďalší),
2. `portal/form/:view/:caseId/:transitionId` ukáže jeho úlohu ako jeden
   formulár (`FormTaskViewComponent`, prihlásené dvojča verejného single
   task view),
3. Submit → položka `then` (My Tickets); Discard alebo odchod → úloha sa
   uvoľní (cancel) a sieť koncept zmaže.

Prečo nie menu položka: menu pozná len `Case` a `Task` zobrazenie. Task
zobrazenie zúžené na prechod je jednoriadkový zoznam, nie formulár, a na
prípad, ktorý ešte neexistuje, sa zúžiť nedá.

## Tiket

Formulár `t_submit`: typ (Bug report, Change request, Service request, Other)
ako zoznam, podkategória a polia podľa typu sa ukážu `make` akciou pri zmene
typu. Povinnosť sa overuje v `pre` podania, nie cez `required` — skryté
povinné pole by podanie zablokovalo. Priorita je zákazníkova a určuje SLA.

Uvoľnenie `t_submit` (cancel) koncept **zmaže** — formulár, ktorý zákazník
opustil bez odoslania, nemá kde žiť.

| stav (`tk_status`) | kto je na ťahu |
|---|---|
| `draft` | zákazník — vidí ho len autor |
| `new` | agent — *Accept* alebo *Reject* (dôvod vidí zákazník) |
| `in_progress` | agent — odpovedá, *Send and wait for the customer*, *Resolve* |
| `waiting` | zákazník — jeho správa vráti tiket do `in_progress` |
| `resolved` | zákazník — *Reopen* alebo *Confirm resolved* |
| `closed`, `rejected` | nikto |

**Konverzácia nie sú prechody**, ale tlačidlá v trvalých pohľadoch `t_my`
a `t_detail` (read arc zo sinku, B8b). Odpovedať sa dá v každom otvorenom
stave a „čaká na zákazníka" je len hodnota stavu. Interné poznámky vidí len
Service Desk.

## SLA

Pri podaní si tiket skopíruje čísla z plánu (hodiny, pracovný čas), takže
zmena plánu neprepíše bežiace termíny. Bez plánu platí 1/2/4/8 h na reakciu
a 8/16/40/80 h na vyriešenie, Po–Pi 8–16.

* **Prvá reakcia** — prvá verejná odpoveď, prijatie alebo zamietnutie.
  `sla_response_met`.
* **Vyriešenie** — `sla_resolution_met`. Kým tiket čaká na zákazníka alebo je
  vyriešený, lehota stojí: pracovné minúty pauzy sa pripočítajú
  (`sla_paused_minutes`) a termín sa prepočíta od podania.

**Hodiny.** `t_tick` a `t_tock` sú systémové prechody s časovačom
(`<trigger type="time">`, PT5M — engine 6.3.1 má Quartz, Java na to netreba),
ktoré si podávajú token medzi `p_clock` a `p_clock_b` variabilnou hranou
`tk_keep_ticking`, kým tiket nie je zatvorený. Oba volajú funkciu `sla_tick`.

Prečo dva: slučka jedného prechodu do vlastného miesta vystrelí **len raz**.
Engine úlohu recykluje (to isté id, po výstrele `triggers: []`) a časovač
jej znova nenaplánuje — nič to nehlási (ENGINE_ISSUES E28).
Pri striedaní prechod po výstrele zanikne a jeho úloha vznikne nanovo, aj
s časovačom. Pri každom ticku:

| čo | kedy | komu |
|---|---|---|
| upozornenie | 75 % lehoty reakcie / vyriešenia | agenti organizácie (riešiteľ) |
| eskalácia | termín prešiel | agenti + správcovia |
| `tk_sla_state` | vždy | `ok`, `at_risk`, `breached`, po vyriešení `met` — zobrazenie *SLA at risk* |
| auto-zatvorenie | vyriešený a `sla_autoclose_days` prac. dní bez reakcie | token do `p_close_due`, `t_auto_close` (trigger auto) |

Každé upozornenie a eskalácia ide len raz (`sla_*_warned`, `sla_*_breached`).

`sd_menu` má druhé hodiny, `t_janitor` / `t_janitor_b` (PT1H): zmaže koncepty staršie než
`sp_draft_hours` plánu organizácie autora. Poistka pre formulár zatvorený
oknom prehliadača, keď uvoľnenie úlohy nestihlo odísť.

Systémový `t_auto_close` štartuje `trigger type="auto"` a token, nie
`async.run { assignTask; finishTask }`: `async.run` chybu spolkne a z testu
by sa nedalo zistiť, prečo sa tiket nezatvoril.

Pasca z tejto fázy: `0 ?: 5` je v Groovy 5 — nula je „falsy". Hodnota, kde
0 znamená „hneď" (dni do zatvorenia, hodina začiatku pracovného času), sa
číta cez `== null`, nie `?:`. Tiket s nulovou lehotou sa kvôli tomu
nezatváral a nič nehlásilo chybu.

Čo tu **nie je**: sviatky.

## Rozbeh, demo a test

```bash
etask-configuration/tools/up.sh --docker     # mailpit je v stacku
python3 etask-configuration/tools/sddemo.py    # demo organizácie, ľudia, tikety
python3 etask-configuration/tools/sdcheck.py
```

`sddemo.py` založí tri plány (Basic, Standard, Premium), dve organizácie
(Acme s.r.o., Globex a.s.), dvoch agentov, päť zákazníkov (heslo `demo1234`,
účty vzniknú z pozvánok v mailpite) a deväť tiketov v stavoch nový, v riešení,
čaká na zákazníka, vyriešený, zatvorený a zamietnutý. Druhé spustenie nič
nezdvojí.

Pozvánky sú vidno na http://localhost:8025. `super@netgrif.com` je
`sd_admin`, `operator@test.local` je `sd_agent`, `druhy@test.local` je bežný
účet, ktorý test pridá do organizácie. Test po sebe organizácie upratuje
a dá sa púšťať opakovane.
