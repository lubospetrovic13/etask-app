# Case drží verziu siete

Prípad si nesie verziu siete, v ktorej vznikol — vrátane **rozloženia
formulára**. Nové polia a prechody doň nepribudnú.

Dôsledky:

- Kto po zmene testuje na starom prípade, testuje starý model. A vyzerá to ako
  chyba appky: kedysi to bol nekonečný spinner na formulári, ktorý bol medzitým
  opravený.
- Siete stavajúce menu majú akciu v udalosti `create`, teda bežia **raz za
  prípad** — bez `{"rebuildOnNewVersion": true}` sa zmena zobrazení nikdy
  neprejaví.
- `NetRunner` importuje sieť len keď v databáze chýba → po zmene XML sa pri
  štarte nestane nič. To rieši `pfsync --sync`.

Kontrolu, že žiadny prípad nebeží na starej verzii, robí `sccheck` (porovnáva
`petriNetId`, lebo `version` z vyhľadávania je vždy `None`).

Súvisí: [[Tiché chyby]] · [[Overovacia slučka]]
