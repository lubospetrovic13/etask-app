# Service Desk

Tri Petriflow siete. Požiadavku podáva **prihlásený zákazník**, spracúva ju
**zamestnanec podpory**. Zákazníka nikto nezakladá ručne: zamestnanec ho pridá
do firmy a tým mu vznikne prístup. Overené za behu na Netgrif AE 6.3.1 —
`tools/sdcheck.py`, 58 kontrol na čistej databáze.

```
sd_firma                         sd_ticket                                 sd_menu
  t_firma (podpora)                t_podanie   (autor)        ──┐           zobrazenia
    pridať / odobrať človeka       t_moja      (ľudia firmy)    │ read arc  + zosúladenie
    obnoviť stav a prístupy        t_detail    (podpora)      ──┘ zo sinku    rolí zákazníkov
                                   t_prevzat → t_vyziadat ⇄ t_doplnit / t_pokracovat
                                             → t_vyriesit → t_znovu
```

| rola | kto | čo vidí v karte Service Desk |
|---|---|---|
| `zakaznik` | ľudia vo firmách, pridelí ju `sd_firma` | Podanie požiadavky, Moje požiadavky |
| `podpora` | zamestnanci, prideľuje admin / `seed.json` | Požiadavky na prevzatie, v riešení, všetky; Firmy zákazníkov |

---

## Firma a prístup

Pridanie človeka do firmy (`btn_pridat` v `sd_firma`) urobí tri veci:

1. **Účet.** Nový e-mail dostane pozvánku (`pozvi(email)` v delegáte): účet
   vznikne v stave `INVITED` a človek si z odkazu v maile nastaví meno
   a heslo sám. Existujúci aktívny účet pozvánku nedostane, len prístup.
2. **Rola `zakaznik`** na `sd_ticket`, všetky verzie. Dáva kartu, dve položky
   menu a právo založiť požiadavku.
3. **Členstvo** v `f_clenovia`. To je to, podľa čoho sa požiadavka priradí
   k firme — nie text vo formulári.

Človek patrí **najviac do jednej firmy**, inak by nebolo jasné, ktorej
požiadavka patrí. Zamestnanec podpory nemôže byť zákazníkom.

Odobratie človeka mu zoberie rolu a **kaskáduje** do existujúcich požiadaviek
firmy (`prepocitaj_tikety` → `setData("t_detail", …)`), takže odobraný
kolega prestane staré požiadavky firmy vidieť okamžite. Účet samotný zostane.

`pozvi` potrebuje SMTP (`MAIL_HOST`). Bez neho vráti vetu „e-mail is not
configured“ a človek sa do firmy nepridá — žiadny účet bez spôsobu, ako sa
prihlásiť.

## Kto čo vidí

`roleRef` a `userRef` sa zjednocujú (B14), a rola má `stringId` razené per
verziu siete (B16). Preto zákazníkova viditeľnosť na role **nestojí**:

| čo | ako |
|---|---|
| založiť požiadavku | `roleRef zakaznik` → `create` |
| vidieť svoj koncept | `userRef tk_zadavatel` (autor prípadu, zapísaný v `create`) |
| vidieť požiadavky firmy | `userRef tk_firma_ludia` (kópia `f_clenovia` pri podaní) |
| všetko | `roleRef podpora` → `view` |

Rola `zakaznik` sa po re-importe `sd_ticket` na novej verzii stratí — položky
menu zmiznú a „+“ vráti 403. Zosúlaďuje ju `sd_menu` pri každej svojej novej
verzii (pre všetky firmy naraz) a tlačidlo „Obnoviť stav účtov a prístupy“
vo firme. Karta (uzol URI) sa porovnáva podľa importId na ktorejkoľvek verzii,
takže tá re-import prežije sama.

## Požiadavka

„+“ v zobrazení *Podanie požiadavky* založí prípad a rovno ho otvorí. Firma je
predvyplnená podľa členstva. Pri podaní (`t_podanie`, finish `pre`) sa firma
overuje **znova** — medzi založením a podaním mohol byť človek z firmy
odobratý alebo zmluva ukončená — a v `pre` sa zapíše aj `tk_firma_ludia`, lebo
userRef úlohy `t_moja` sa vyhodnocuje pri jej vzniku.

| stav (`tk_stav`) | kto je na ťahu |
|---|---|
| `rozpisana` | zákazník — koncept vidí len autor |
| `nova` | podpora — *Prevziať* (priorita, druh) |
| `v_rieseni` | podpora — *Vyžiadať od zákazníka* alebo *Vyriešiť* |
| `caka` | zákazník — *Odpovedať podpore*; podpora môže *Pokračovať bez odpovede* |
| `vyriesena` | zákazník môže *Znovu otvoriť* |

`tk_komunikacia` je celá história (vidia ju obe strany), `tk_interna` len
podpora. Mail o zmene stavu ide cez `notifikuj` a nikdy nezhodí prechod.

`assignPolicy` je `manual` všade okrem podania: `auto` priradí úlohu tomu,
koho akcia ju vyrobila (B21) — úloha podpory vyrobená zákazníkovým podaním by
inak patrila zákazníkovi.

## SLA

Lehota odozvy (`sla_termin`) sa počíta pri podaní: pracovný čas Po–Pi
08:00–16:00, hodiny zo zmluvy firmy (`f_sla_a/b/c`), inak A 2 h, B 4 h, C 8 h.
Pri prevzatí sa zapíše `sla_prevzate` a `sla_dodrzane`. Priorita je
predvyplnená z toho, ako súrne to zákazník označil.

Čo tu **nie je**: sviatky, lehota na vyriešenie, odpočítanie čakania na
zákazníka. To patrí do kalendárovej služby v backende, nie do Groovy akcie.

## Rozbeh a test

```bash
docker run -d --name mailpit -p 1025:1025 -p 8025:8025 axllent/mailpit
MAIL_HOST=localhost MAIL_PORT=1025 MAIL_TLS_ENABLED=false MAIL_AUTH_ENABLED=false \
  ETASK_TEST_PASSWORD=test1234 etask-configuration/tools/up.sh
python3 etask-configuration/tools/sdcheck.py
```

Pozvánky sú vidno na http://localhost:8025. `operator@test.local` má rolu
`podpora`, `druhy@test.local` je bežný účet, ktorý test pridá do firmy.

## Čo zostalo z predošlej verzie

Verejný anonymný formulár (`sd_intake`), pracovné úlohy (`sd_work_item`)
a register zákazníkov párovaný podľa názvu organizácie (`sd_customer`) sú
preč. `sd_menu` zmaže ich položky menu v už bežiacej inštancii
(`zastarane`); prípady tých sietí a siete samotné v engine zostanú, kým ich
niekto nezmaže.
