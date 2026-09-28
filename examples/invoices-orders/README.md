# Objednávky a faktúry

**Referent (kontrola faktúry):** nástrel podľa zadania kolegov - referent, ktorý kontroluje,
páruje a zapisuje dodanie, vstupné kontroly, pravidlo "schvaľovanie netreba", vrátenie na
ktorúkoľvek predošlú úroveň, XML export, doklad vedľa formulára. Čo je hotové a čo chýba, je
v [BRIEF.md](BRIEF.md); overenie `python3 tools/fakcheck.py`. Odhad eventov a nákladov
na AWS je v [docs/NAKLADY.md](docs/NAKLADY.md).

Petriflow appka pre eTask. Zije vo vlastnom repozitari; do konkretneho
nasadenia sa dostane nastrojom starteru:

```bash
cd etask-configuration
python3 tools/pfapp.py install ../examples/invoices-orders
python3 tools/pfsync.py --sync        # import do bezuceho enginu + role
```

Co je tu:

| subor | co to je |
|---|---|
| `processes/fa_faktura.xml` | siet |
| `processes/ob_objednavka.xml` | siet |
| `processes/sc_menu.xml` | siet |
| `processes/sc_nastavenia.xml` | siet |
| `tools/sccheck.py` | akceptacny test proti beziacemu enginu |
| `docs/PRIRUCKA.md` | dokumentacia appky |
| `app.json` | manifest appky - `import`, `bootstrapCase`, `uriNodes`, `netScope` |

**Role appka nikomu neprideluje.** Kto ktoru rolu dostane, je rozhodnutie
nasadenia a dopisuje sa do `seed.json` starteru (`netScope` doplni `install`).
