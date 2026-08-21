# pflint — statická kontrola Petriflow sietí

```bash
python3 tools/pflint.py processes/            # celý priečinok
python3 tools/pflint.py processes/sd_ticket.xml
python3 tools/pflint.py --strict processes/   # aj upozornenia končia nenulovo
```

Bez závislostí, len štandardná knižnica Pythonu 3.

## Čo kontroluje a prečo práve to

Petriflow akcie sú Groovy v CDATA vnútri XML. Nič ich pred behom neskontroluje —
ani XSD, ani kompilátor. Chyba sa preto prejaví až za behu a **často ticho**:
akcia spadne v strede, časť zmien je zapísaná, zvyšok nie, a v odpovedi nie je nič.

Linter hľadá presne tie tichosti. Každé pravidlo stálo aspoň jedno kolo ladenia
a je zdokumentované v `docs/PETRIFLOW_LEARNINGS.md`.

| pravidlo | čo sa stane bez toho |
|---|---|
| `unsafe-nav-property` | `?._id` vyhodí `MissingPropertyException` a **zhodí celú akciu v strede** |
| `findcase-stringid` | `findCase { it.stringId… }` vráti vždy null, v logu len INFO |
| `async-swallows` | `async.run` výnimku spolkne — cieľový case zostane prázdny bez stopy |
| `button-reads-text` | button číta editovateľné textové pole bez `immediate` → prečíta prázdno |
| `make-singular` | `on transition` namiesto `on transitions` — ticho nič nespraví |
| `dataref-undeclared` | import spadne, alebo pole ticho zmizne z formulára |
| `role-undeclared` | import spadne na `IllegalArgumentException: Role X not found` |
| `type-textarea` | `type="textarea"` neexistuje, import spadne na NPE |
| `setdata-unknown-transition` | preklep v id transition sa prejaví až za behu |
| `action-unknown-field` | akcia berie `f.x`, ktoré neexistuje |

## Čo NEkontroluje a prečo

**Poradie podelementov `<data>`.** Existujú tri zdroje pravdy a odporujú si:

1. oficiálna XSD v1.1.0 (`reference/petriflow.schema.v1.1.0.xsd`):
   `placeholder` → `desc` → … → `init` → … → `component`
2. NAE 6.3.1 za behu: prijme aj `component` pred `init` — všetky siete v tomto
   repozitári to tak majú a importujú sa
3. `PETRIFLOW_LEARNINGS` B5: `desc` hneď za `title`

Linter, ktorý označkuje funkčný kód, naučí agenta linter ignorovať. Poradie preto
patrí do reference knowledge, nie do kontroly.

Rovnako nekontroluje nič, čo závisí od stavu bežiacej instancie — na to je
ground truth import do enginu.

## Úrovne

- `ERROR` — sieť sa nenaimportuje, alebo sa naimportuje rozbitá. Exit 1.
- `WARNING` — naimportuje sa a bude sa chovať inak, než autor čaká.
- `INFO` — možno v poriadku, treba sa pozrieť. Nemá vplyv na exit kód.

## Pridanie pravidla

Pravidlo pridávaj len keď máš **overený** prípad, kedy to za behu zlyhá, a napíš
do hlásenia aj opravu. Hlásenie bez opravy je pre agenta nepoužiteľné.
