# Manifest mlčí

Manifest má štyri sekcie v dvoch súboroch a **každá vie chýbať tak, že to nič
nepovie**:

| chýba | prejav |
|---|---|
| `import` | sieť sa nenaimportuje, karta vedie do prázdna |
| `bootstrapCase` | sieť je, ale zobrazenia nikto nepostaví |
| `uriNodes` | zobrazenia sú, kartu nie je vidno |
| `netScope` | `pfseed` nepridelí roly ani po dopísaní do `seed.json` |

Preto sa needituje ručne: `pfnew` (nová appka), `pfapp` (appka z iného repa).

Naposledy to stálo celý obraz: Dockerfile kopíroval `processes/`, ale nie
`processes.json`, Maven chýbajúci resource mlčky preskočil a v kontejneri bola
prázdna appka — v logu len „ziadne siete na import".

Súvisí: [[Tiché chyby]] · [[Šablóna vs nasadenie]]
