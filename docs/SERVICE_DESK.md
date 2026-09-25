# Service Desk

Štyri Petriflow siete. Tiket podáva **prihlásený zákazník**, rieši ho **agent**
priradený k jeho organizácii, organizácie a SLA plány spravuje **správca**.
Zákazníka ani agenta nikto nezakladá ručne: správca ho pridá do organizácie
a tým mu príde pozvánka. Overené za behu na Netgrif AE 6.3.1 —
`tools/sdcheck.py`, 88 kontrol na čistej databáze.

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
| `sd_agent` | naši zamestnanci, pridelí ju `sd_organization` (alebo `seed.json`) | Triage, Tickets in progress, All Tickets, My Organizations |
| `sd_admin` | správca Service Desku, `seed.json` | Triage, Tickets in progress, All Tickets, Organizations, SLA Plans |

---

## SLA plán

Predajný balíček: hodiny na prvú reakciu a na vyriešenie pre každú prioritu
(critical, high, medium, low), pracovný čas (Po–Pi, od–do) a limity, za
ktoré klient platí (počet účtov, počet agentov). Lehoty na automatické
zatvorenie a zmazanie konceptu sú tu tiež, zatiaľ ich nikto nevykonáva
(fáza 3, časovač).

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

Čo tu **nie je**: sviatky, upozornenie pred porušením a eskalácia (potrebujú
čas, ktorý plynie bez akcie človeka — fáza 3).

## Rozbeh a test

```bash
etask-configuration/tools/up.sh --docker     # mailpit je v stacku
python3 etask-configuration/tools/sdcheck.py
```

Pozvánky sú vidno na http://localhost:8025. `super@netgrif.com` je
`sd_admin`, `operator@test.local` je `sd_agent`, `druhy@test.local` je bežný
účet, ktorý test pridá do organizácie. Test po sebe organizácie upratuje
a dá sa púšťať opakovane.
