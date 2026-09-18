# Požiadavka na aplikáciu: Nástup nového zamestnanca

> Toto je zadanie od zákazníka, nie technický návrh. Je napísané tak, ako sa
> o procese hovorí na porade. Ako sa to postaví, je vec platformy.

## Prečo to chceme

Keď k nám nastúpi nový človek, treba mu založiť účty v troch systémoch:
**Entra ID**, **Atlassian** a **portál Netgrif**. Dnes to ide mailami. Nikto
nevie povedať, v akom je to stave, kto to už spravil a kto ešte nie, a stáva
sa, že človek príde v pondelok a nemá sa kam prihlásiť.

Chceme jednu žiadosť, jedno schválenie a prehľad, kde to viazne.

## Ako to má fungovať

1. **Personalistka založí žiadosť o nástup.** Vyplní meno a priezvisko, pracovný
   e-mail, pozíciu, stredisko a dátum nástupu. Zároveň **vyberie nadriadeného**,
   ktorý má nástup schváliť.

2. **Vybraný nadriadený žiadosť schváli alebo vráti** na doplnenie. Keď ju
   vracia, napíše dôvod, aby personalistka vedela, čo doplniť. Vrátená žiadosť
   sa dá upraviť a poslať znova.

3. **Po schválení sa zakladajú účty.** IT správca odškrtáva, čo je hotové:
   Entra ID, Atlassian, portál Netgrif. Vidí pri tom údaje zo žiadosti, aby
   nemusel nikde inde hľadať.

4. **Keď sú hotové všetky tri, nástup je vybavený.** Personalistka aj nadriadený
   to vidia na svojom zozname bez toho, aby sa museli pýtať.

## Čo musí byť vidieť v portáli

| kto | čo potrebuje vidieť |
|---|---|
| personalistka | moje žiadosti a v akom sú stave |
| nadriadený | čo čaká na moje schválenie |
| IT správca | komu mám založiť účty |
| všetci zúčastnení | vybavené nástupy |

V zozname nech je vidno meno nastupujúceho, dátum nástupu, stav a kto schvaľuje.

## Pravidlá, na ktorých záleží

* Schvaľuje **len ten jeden vybraný nadriadený**, nie ktokoľvek s tou rolou.
* **Nič sa nezakladá pred schválením.** Ani jeden účet.
* **Žiadateľ nesmie schvaľovať sám seba.**
* Vrátená žiadosť sa nezahadzuje, pokračuje sa v tej istej.

## Čo teraz neriešime

Skutočné napojenie na Entra ID a Atlassian. Zatiaľ stačí, že IT správca
zakladanie odškrtne ručne. Integrácia príde neskôr a proces sa pre ňu nemá
meniť, len sa doplní, kto to odškrtnutie spraví.

## Ako to budeme skúšať

Na testovacom účte prejdeme celú cestu: založiť žiadosť, nechať ju vrátiť,
doplniť, schváliť, odškrtnúť tri účty a vidieť, že nástup je vybavený.
Chceme vedieť, že sa to takto dá prejsť, nie len že sa to dá naklikať.
