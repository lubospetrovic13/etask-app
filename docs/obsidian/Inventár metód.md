# Inventár metód

`docs/reference/action-api.md` je **generovaný** zoznam metód volateľných z Petriflow
akcie — engine (~169) plus vlastné primitíva projektu.

Prečo je to dôležitejšie, než sa zdá: delegát je dynamický, takže preklep
v názve metódy prejde parserom aj importom a spadne **až za behu**. Ten zoznam
je jediná obrana — a vznikol preto, že bez neho bola postavená horšia verzia
už existujúceho extension pointu.

```bash
python3 tools/pfapi.py > docs/reference/action-api.md   # po pridaní metódy
```

Vlastné primitíva, ktoré vznikli z reálnych appiek: `usersWithRoleAll`,
`najnovsiCase`, `precitajFakturu`, `ocrDostupne`, `notifikuj`, `menaUzivatelov`,
`pripoj_do_uzla`, `createOrUpdateMenuItem`.

Súvisí: [[Tri vrstvy]] · [[Nástroje]]
