# Overovacia slučka

Lacné najprv, drahé potom:

```bash
python3 tools/pflint.py processes/     # 0,3 s   štruktúra, grid, mŕtve polia
python3 tools/pfgroovy.py processes/   # 3 s     syntax akcií
python3 tools/pfi18n.py processes/     #         každý viditeľný text má preklad
python3 tools/pfview.py                #         frontend vykreslí, čo sieť pýta
python3 tools/pfsync.py --sync         #         import do enginu + roly
python3 tools/<app>check.py            #         appka robí to, čo má
```

Akceptačné testy (`sccheck`, `dvcheck`, `pucheck`) klikajú celý priebeh cez API
ako skutoční používatelia — to je jediné miesto, kde sa dá overiť, že
*schvaľovateľ vidí faktúru a zadávateľ nie*.

**Keď si offline nástroj a engine odporujú, chyba je v nástroji.** Oprav nástroj
a spusti `tools/pftest.sh` — testy nástrojov proti fixtures.

Súvisí: [[Ground truth je engine]] · [[Ako sa poznatok stane trvalým]]
