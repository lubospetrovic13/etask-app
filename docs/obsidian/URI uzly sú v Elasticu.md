# URI uzly sú v Elasticu

Položky menu (`preference_filter_item`) žijú v **Mongu**, URI uzly (priečinky
bočného menu) v **Elasticsearchi**. Frontend hľadá obsah priečinka dopytom
`uriNodeId: <id uzla>`.

Keď sa index Elasticu vymení — `--fresh`, iný stroj, čistý volume v Dockeri —
uzly vzniknú **znova a s novými id**, kým položky v Mongu držia staré. Priečinok
sa dá otvoriť a je prázdny. Žiadna chyba, cez API sa všetko nájde.

Opravuje to primitívum `pripoj_do_uzla(existing, uri)`, ktoré menu siete volajú
**aj vo vetve „položka je nezmenená"** — inak sa tam `createOrUpdateMenuItem`
nikdy nedostane.

Súvisí: [[Tiché chyby]] · [[Nástroje]]
