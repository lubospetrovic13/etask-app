# Onboarding / provisioning zamestnanca — prototyp

Appka `onboarding` (`etask-configuration/processes/on_nastup.xml`,
`on_menu.xml`). **Prototyp bez integrácií:** schvaľovanie a vytvorenie účtu
v Netgrife sú skutočné, Entra ID a Atlassian sú zatiaľ simulované.

## Priebeh

```
        ┌──────── vrátiť na doplnenie ────────┐
        │                                     │
Rozpísané ─► Na schválenie ─► Zakladajú sa účty ─► Hotovo
   ▲              │
   │              └── zamietnuť ──────────────────► Zamietnuté
   │
Personalista zakladá
```

| krok | kto | čo tam vypĺňa |
|---|---|---|
| Žiadosť o nástup | `personalista` | človek, pozícia, oddelenie, úväzok, dátum nástupu, firemný e-mail, **ktoré účty** a **kto to schváli** |
| Schválenie nadriadeným | **jeden vybraný vedúci** | schváliť / vrátiť / zamietnuť, môže upraviť zoznam účtov |
| Vytvorenie účtov | `it_spravca` | skupiny v Entre, Atlassian tím, profil v Netgrife, počiatočné heslo, tlačidlo *Vytvoriť účty* |

**Jedno schválenie, a schvaľuje ho konkrétny človek**, nie ktokoľvek s rolou.
Zadávateľ ho vyberie zo zoznamu vedúcich pri podaní; seba si vybrať nevie
a guard vo `finish` to drží aj proti API. Technicky: `roleRef` sa v prechode
uvádza staticky, takže „schváli to **tento** človek“ ide cez `userList` pole
a `userRef` na ňom (RUNBOOK 11) — a rola `veduci` na tom prechode **byť
nesmie**, lebo `roleRef` a `userRef` sa zjednocujú, neprienikajú.

Vrátenie aj zamietnutie vyžadujú komentár. Vrátenie pošle prípad späť
zadávateľovi so zachovanými hodnotami a komentárom pri formulári; cyklus môže
prebehnúť koľkokrát treba a každý krok je v poli *Priebeh*.

**Stav nie je v pracovných formulároch.** Kto má pred sebou úlohu, vie z nej,
kde prípad stojí; `on_stav_label` existuje kvôli stĺpcu a dopytu zobrazení
a zobrazuje sa len v read-only prehľade. Ten je dostupný celý život prípadu
(read arc z miesta, ktoré nikto nekonzumuje — B25), takže zadávateľ vidí, kde
to stojí, aj keď úloha leží u schvaľovateľa.

## Tri účty a čo je z nich skutočné

| systém | teraz | čo dorobiť |
|---|---|---|
| **Netgrif (táto appka)** | **skutočne** — `createNewUser` + `setProcessRole`, človek sa vie prihlásiť | nič |
| Entra ID | riadok v protokole s fiktívnym `objectId` | `entraCreateUser(...)` v delegáte (Graph API) |
| Atlassian | riadok v protokole s fiktívnym `accountId` | Atlassian Admin API |

Miesto, kam konektory prídu, je označené v akcii `btn_on_provision_set`
v `on_nastup.xml`. Patria do `EtaskActionDelegate` (vrstva 2), nie do siete:
je to I/O na cudzie API. Sieť si ponechá zoznam účtov a protokol.

Poradie, v ktorom to má zmysel robiť: **Entra ID prvé** — je zdroj identity
a Atlassian sa naň dá napojiť cez SSO, takže druhá integrácia bude lacnejšia
než prvá.

## Predpoklady, ktoré treba potvrdiť

1. **Firemný e-mail** sa navrhne ako `meno.priezvisko@ditec.sk` a je zároveň
   prihlasovacím menom všetkých účtov. Ak má Ditec inú konvenciu (osobné
   číslo, iniciály), mení sa jeden riadok v `t_on_ziadost_finish`.
2. **Zoznam vedúcich** je „každý s rolou `veduci`". Ak sa má schvaľovať podľa
   oddelenia, zúži sa `nadriadeni(...)` o filter na oddelenie — je to jedna
   funkcia v sieti, nie prestavba.
3. **Počiatočné heslo zadáva IT** a odovzdáva sa osobne; z prípadu sa maže
   hneď po vytvorení účtu. S Entrou ako zdrojom identity toto pole zmizne —
   prihlasovať sa bude cez SSO.
4. **Notifikácie sa neposielajú.** Primitívum `notifikuj(...)` v delegáte
   existuje a beží cez SMTP z Dockeru (RUNBOOK 12); je to jeden riadok
   v každom kroku, ale bez dohody o tom, kto má čo dostať, by to bol šum.
5. **Offboarding nie je.** Je to zrkadlový proces (odobrať prístupy, vrátiť
   HW) a patrí do tej istej appky ako druhá sieť — nie do tejto.

## Roly a prístup

| rola | čo smie |
|---|---|
| `personalista` | zakladá žiadosti |
| `veduci` | schvaľuje — ale len tie žiadosti, kde ho zadávateľ vybral |
| `it_spravca` | zakladá účty |

Kartu v bočnom menu vidia len tieto tri roly (`uriNodes` v `processes.json`).
Novo vytvorený účet dostane `ROLE_USER` a procesnú rolu podľa poľa *Profil
v Netgrife*; pri `zamestnanec` žiadnu — prihlási sa a appku nevidí, čo je pre
bežného nastupujúceho správne.

**Po pridelení rolí sa treba odhlásiť a prihlásiť.** Prihlásená session drží
staré `stringId` rolí a zakladanie prípadu by vrátilo 403.

## Rozbehanie a overenie

```bash
cd etask-configuration
python3 tools/pflint.py processes/        # struktura a tiche pasce
python3 tools/pfgroovy.py processes/      # syntax akcii
python3 tools/pfi18n.py processes/        # preklady
python3 tools/pfview.py                   # vykresli to frontend
python3 tools/pfsync.py --sync            # import do enginu + role
python3 tools/pfseed.py                   # pridelenie roli podla seed.json
python3 tools/onboardingcheck.py          # akceptacny test proti enginu
```

`onboardingcheck.py` prejde celý proces tromi účtami (HR, vybraný vedúci, IT),
overí, že schvaľovaciu úlohu vidí **len ten vybraný** (IT správca ju nevidí),
že vrátenie na doplnenie nesie komentár späť k zadávateľovi, že pracovný
formulár stav neobsahuje, a nakoniec **prihlásenie vytvoreným účtom**. Účet,
ktorý zakladá, je stále ten istý (`test.nastup@ditec.local`), takže po sebe
nenecháva nové.

Demo účty a ich roly sú v `seed.json`: `admin@test.local` je personalista,
`operator@test.local` a `super@netgrif.com` sú vedúci, `druhy@test.local` IT.

**Heslo sa do poľa posiela ako base64** — `formPassword` v delegáte ho dekóduje,
lebo tak ho posiela frontend. Plain text prejde ako platný base64, dekóduje sa
na smeti a inštancia ho odmietne ako príliš slabé heslo; hláška o tom nepovie
nič a minimálnu dĺžku pritom spĺňa.

**Hodnota `userList` poľa nie je zoznam**, ale `UserListFieldValue`
s `userValues`. `.collect { it.id }` priamo na nej vyhodí
`No such property: id` uprostred akcie — teda po tom, čo časť zmien prebehla.
V sieti je na to funkcia `id_z_userlistu`.

## Stav nasadenia (17. 9. 2026)

Naimportované do bežiacej inštancie na `localhost:8080`, bootstrap case menu
prestavaný, roly pridelené. `onboardingcheck.py`: **54 kontrol prešlo,
2 zlyhali** — obe na tom istom:

> Kartu `onboarding` vidí každý prihlásený, aj účet bez rolí.

Nie je to chyba siete. Viditeľnosť karty riadi `uriNodes` v `processes.json`
a ten sa **pakuje do jaru**; bežiaci engine je postavený zo staršieho stromu,
ktorý položku pre `onboarding` nemá, a uzol bez položky je viditeľný pre
každého. Platí to až po `tools/up.sh --build` (prestavba jaru a reštart).

Staršia onboarding appka `hr/onboarding/on_nastup` („Nástup nového
zamestnanca", NZM) je **zmazaná** — položky menu aj s filtrami, prípady, obe
siete, uzol URI v Elasticsearchi aj zvyšné XML v `target/classes`, ktoré by ju
po reštarte naimportovalo späť.

Karta tejto appky je `onboarding` na koreňovej úrovni, nie `hr/onboarding` —
tak to má identifikátor siete v tomto repozitári. Keby mala byť pod `hr`,
je to premenovanie `<id>` na `hr/onboarding/on_nastup` plus uzly `hr`
a `hr/onboarding` v `processes.json`; premenovanie je ale **nová sieť**, takže
staré prípady treba zmazať (RUNBOOK 2).

Testovacie prípady po behu testu sa zmažú `python3 tools/onboardingcheck.py --wipe`.
