# Kontext a tokeny

Najdrahšia položka jednej appky nie je písanie kódu, ale **čítanie**.

| čo | ~tokenov | kedy sa načíta |
|---|---|---|
| `CLAUDE.md` | 1 800 | vždy |
| `cheatsheet.md` | 2 000 | na začiatku úlohy |
| skill `petriflow` | 3 200 | pri sieťach a akciách |
| `RUNBOOK.md` celý | 14 500 | **nikdy** — po kapitolách |
| `petriflow_reference.md` celý | 27 000 | **nikdy** — len hľadanie |
| všetka dokumentácia | ~86 000 | keby sa čítala celá |

Preto existuje `pfdoc`:

```bash
python3 tools/pfdoc.py hladaj "menu"   # v ktorej kapitole to je
python3 tools/pfdoc.py runbook 4       # ~2 700 namiesto ~14 500
```

Druhý spôsob, ako neminúť tokeny, je **nečítať vôbec** — nechať odpovedať
nástroj: `pflint` povie, čo je zle, `pfview` čo frontend nevykreslí, `pfapi`
aké metódy existujú. [[Nástroje]]

Tretí je **delegovať**: podúloha, ktorá prehľadáva veľa súborov, vráti záver,
nie obsah súborov.

Súvisí: [[Ako agent pracuje]] · [[Tiché chyby]]
