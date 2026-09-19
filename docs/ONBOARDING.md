# Nástup nového zamestnanca

Appka k zadaniu *Application request: Onboarding a new employee*. Jedna
žiadosť, jedno schválenie a jedno miesto, kde vidno, kde to viazne — namiesto
e-mailovej reťaze, o ktorej nikto nevie povedať, v akom je stave.

Dve Petriflow siete, žiadny zásah do Javy ani do Angularu:

```
onboarding/on_request                        onboarding/on_menu
  t_on_request   Žiadosť o nástup              päť zobrazení karty „Nástupy
  t_on_approval  Schváliť nástup               zamestnancov" (bootstrap case
  t_on_accounts  Založiť účty                  s rebuildOnNewVersion)
  t_on_overview  Dokončený nástup
```

```
p_draft --t_on_request--> p_awaiting_approval --t_on_approval--+--> p_accounts --t_on_accounts--> p_done
   ^                                                           |                                    |
   +------------- variable arc: vrátené na doplnenie ----------+              read arc --> t_on_overview
```

## Jazyk

**Zdroj je po anglicky, slovenčina je preklad.** Titulky, popisy, možnosti
a názvy zobrazení majú anglický `defaultValue` a slovenský `<i18n locale="sk">`;
identifikátory polí, prechodov a rolí sú anglické (`on_first_name`,
`t_on_approval`, `approver`). Portál prepnutý do slovenčiny je tak celý po
slovensky, portál v hocičom inom je celý po anglicky — a ani jedno nevzniká
náhodou.

Dve veci sa preložiť **nedajú** a sú preto po anglicky aj na slovenskom
portáli: **priebeh** (`on_history`) a **validačné hlášky**. Sú to obyčajné
`String`-y, ktoré zapisuje akcia — `Case.title` a hodnota `text` poľa
`I18nString` nie sú. Keby mali byť po slovensky, musia sa po slovensky
napísať v akcii a potom budú slovenské aj v anglickom portáli; tretia
možnosť neexistuje. `oncheck.py` obe strany prekladu kontroluje (krok 2 a 3b),
takže chýbajúci preklad nie je nález z prezerania, ale zlyhaný test.

Testovacie účty inštancie (`application.properties`) sa volajú **Test Admin,
Test Operator, Test Viewer, Second Tester** — ich mená vidno v appke ako
„Schvaľuje", „Žiadosť podal" a v priebehu, takže slovenské mená by boli
slovenčina, ktorú preklad nedosiahne. Mená sa priradia len účtom, ktoré
vznikajú na **čistej databáze**; existujúcej inštancii ich to nepremenuje.

---

## Model na plátne

Súradnice uzlov nie sú náhodné a nie sú kozmetika: model sa otvára v builderi
(RUNBOOK 14) a v jednom rade sa z neho nedá prečítať, že rozhodnutie má dve
vyústenia. Preto podanie ide po `y=280`, **schválené stúpa doprava hore**
(`y=140`), **vrátené sa vracia dolu späť** do `p_draft` (lomové body na
`y=460`, inak by spiatočná šípka viedla cez celý hlavný rad a prekryla tri
uzly) a read-only pohľad visí pod koncovým miestom. Na beh procesu to nemá
žiadny vplyv.

## Priebeh

1. **Personalista podá žiadosť.** Meno, priezvisko, pracovný e-mail, pozícia,
   stredisko, dátum nástupu — a **vyberie vedúceho**, ktorý ju má schváliť.
2. **Vybraný vedúci schváli alebo vráti na doplnenie.** Pri vrátení napíše
   dôvod. Vrátená žiadosť je ten istý prípad s tými istými dátami; personalista
   ju doplní a podá znova, koľkokrát treba.
3. **Po schválení zakladá účty IT správca** — Entra ID, Atlassian, Netgrif
   portál. Údaje zo žiadosti má na tom istom formulári, takže nemusí hľadať
   inde. Odškrtnuté sa ukladá priebežne; úloha zostáva otvorená, kým chýba čo
   i len jeden účet.
4. **Keď sú všetky tri, nástup je dokončený.** Personalista aj vedúci ho vidia
   vo svojom zozname, bez toho aby sa niekoho pýtali.

## Kto čo vidí

| kto | zobrazenie | ako je zúžené |
|---|---|---|
| personalista | Žiadosť o nástup | všetko, čo smie vidieť |
| personalista | Rozpísané a vrátené nástupy | `taskIds:"t_on_request"` |
| vedúci | Nástupy na schválenie | `taskIds:"t_on_approval"` |
| IT správca | Účty na založenie | `taskIds:"t_on_accounts"` |
| všetci zainteresovaní | Dokončené nástupy | `dataSet.on_status.keyValue:"done"` |

Stĺpce zoznamu sú meno nastupujúceho (nesie ho názov prípadu), dátum nástupu,
stav a kto schvaľuje — presne to, čo zadanie pýta.

Zobrazenia sú typu **Case**, nie Task: Task zobrazenie kreslí riadok na úlohu,
takže tá istá žiadosť by v zozname bola aj viackrát. Cena za to je, že Case
zoznam sa filtruje oprávnením `view` na prípade, nie právom prechod vykonať —
personalista má `view` na všetky žiadosti, takže by si ich videl aj v „Na
schválenie“. Preto majú tie položky `allowed_roles` nastavené na rolu, ktorej
patria. **Nie je to bezpečnostná hranica** (tou je `perform` na prechode), je to
poriadok v menu.

## Štyri pravidlá a to, čo ich drží

Žiadne z nich nie je vo frontende; všetky sú v modeli.

| pravidlo zo zadania | čo ho drží |
|---|---|
| schvaľuje **len ten jeden vybraný** vedúci | `userRef` na `on_approver` a **žiadny** `roleRef` na `t_on_approval` |
| pred schválením sa nezakladá **nič** | `t_on_accounts` je za miestom `p_accounts`, do ktorého vedie jedine schválenie |
| žiadateľ nesmie schvaľovať vlastnú žiadosť | kontrola pri podaní (tam sa vedúci vyberá) aj pri rozhodovaní |
| vrátená žiadosť pokračuje, nezahadzuje sa | variable arc späť do `p_draft` — ten istý prípad, `on_history` drží priebeh |

Prvé z nich je to, ktoré sa najľahšie pokazí: `roleRef` a `userRef` sa
**zjednocujú, nie pretínajú** (`PETRIFLOW_LEARNINGS` B14, RUNBOOK 11). Keby na
prechode `t_on_approval` bola aj rola `approver`, žiadosť by schválil
ktokoľvek s tou rolou a výber konkrétneho človeka by nebol na nič. Rola `approver`
sa preto používa len na dve veci: kontrolu pri výbere (koho sa dá vybrať) a
`allowed_roles` položky menu.

## Roly

| rola | čo môže |
|---|---|
| `hr` | zakladať a vidieť žiadosti, dopĺňať vrátené |
| `approver` | schvaľovať tie žiadosti, kde bol **vybraný** (rola sama o sebe nedáva `view`); v portáli sa volá „Manager" / „Vedúci" |
| `it_admin` | vidieť schválené žiadosti a zakladať účty |

Identifikátor je `approver`, nie `manager`, **zámerne**: rolu s importId
`manager` má Service Desk a `pfseed` prideľuje podľa importId cez celý
`netScope` — `manager` v `seed.json` by teda ticho pridelil aj rolu v Service
Desku. Zobrazený názov je pritom „Manager" / „Vedúci", takže na tom nikto nič
nepozná.

Prideľuje ich `tools/pfseed.py` zo `seed.json`; `netScope` pre túto appku je
`onboarding/*`. **Po pridelení sa treba odhlásiť a prihlásiť** — prihlásená
session drží staré `stringId` rolí a zakladanie prípadu vráti 403.

## Čo appka zatiaľ nerieši

Skutočnú integráciu na Entra ID a Atlassian. IT správca účty odškrtáva ručne,
tak ako to zadanie pripúšťa. Keď integrácia príde, vymení sa obsah `t_on_accounts`
(kto odškrtáva) — miesta, prechody ani oprávnenia sa meniť nemusia. Nový
primitív v `EtaskActionDelegate` (vrstva 2) je na to správne miesto:
`zalozUcetEntra(...)` volané z akcie, nie nový Angular komponent.

## Overenie

```bash
cd etask-configuration
python3 tools/pflint.py processes/        # struktura a tiche pasce
python3 tools/pfgroovy.py processes/      # syntax akcii
python3 tools/pfi18n.py processes/        # kazdy viditelny text ma preklad
python3 tools/pfview.py                   # vykresli to frontend?
python3 tools/pfsync.py --sync            # import + role
python3 tools/oncheck.py                  # akceptacny test proti beziacemu enginu
```

`oncheck.py` prejde celú cestu zo zadania — podať, dostať vrátenú, doplniť,
schváliť, odškrtnúť tri účty, vidieť dokončený nástup — a popri tom overí tie
štyri pravidlá. Účty, na ktorých to beží, a prečo práve ony, sú v hlavičke toho
súboru; podstatné je, že schvaľovateľ **nie je** admin: `ROLE_ADMIN` obchádza
všetky oprávnenia Petriflow, takže na admin účte sa hranica „schvaľuje len
vybraný vedúci“ overiť nedá.

Overenie na čistej databáze vedľa bežiaceho dev stacku (manifest a uzol URI sa
pri tejto appke menili, takže sa patrí):

```bash
cd deploy
docker compose -p etask-fresh -f docker-compose.dev.yml -f docker-compose.fresh.yml up -d --build
cd ../etask-configuration
PF_URL=http://127.0.0.1:18080 python3 tools/pfseed.py     # role na cistej DB
PF_URL=http://127.0.0.1:18080 python3 tools/oncheck.py
cd ../deploy
docker compose -p etask-fresh -f docker-compose.dev.yml -f docker-compose.fresh.yml down -v
```

Portál toho stacku beží na http://localhost:14200 (backend 18080). Jazyk sa
prepína vlajkou v bočnom paneli — pre video treba slovenskú.
