# Nová aplikácia a kde je čo

```bash
cd etask-configuration
python3 tools/pfnew.py mojaapp ziadost "Žiadosť o niečo" --role pracovnik
```

Vygeneruje sieť, menu sieť so zobrazeniami a stĺpcami, doplní manifest a napíše
akceptačný test. Ručne je to `cp examples/skeleton.xml processes/mojaapp.xml`
plus zápis do manifestu — a to je celý postup. **Pridanie appky Javu
nevyžaduje:** `pom.xml` kopíruje `processes/*.xml` hromadne a `NetRunner` si
identifikátor prečíta z `<id>` v XML, takže sa nedá rozísť so sieťou.

Rozšírenie platformy je iná vec: keď appka potrebuje schopnosť, ktorú engine
nemá, pribudne primitívum v delegáte, prípadne servis a závislosť v `pom.xml`.
To je legitímne — podmienkou je veta, ktoré primitívum na vyššej vrstve chýba.

## Manifest má štyri sekcie a každá vie chýbať ticho

| kľúč | na čo | keď chýba |
|---|---|---|
| `import` (processes.json) | súbory sietí a poradie importu | sieť sa nenaimportuje, karta vedie do prázdna |
| `bootstrapCase` | siete, ktorých má existovať práve jeden case (typicky tá, čo stavia menu) | sieť je, zobrazenia nikto nepostaví |
| `uriNodes` | ikona a viditeľnosť karty (`requiredAuthorities`, `requiredProcessRoles` — importId) | zobrazenia sú, kartu nie je vidno |
| `netScope` (seed.json) | rozsah pre prideľovanie rolí | `pfseed` roly nepridelí |

`bootstrapCase` má dva tvary a nie je to kozmetika: obyčajný identifikátor = **jeden
case navždy** (pracujúci singleton), `{"net": ..., "rebuildOnNewVersion": true}`
= **jeden case na verziu siete** (pre siete stavajúce menu — ich akcia je
v `create`, teda beží raz za case).

Na poradí v `import` záleží: uzol URI vzniká až importom prvej siete, ktorej
identifikátor tú cestu nesie, takže sieť odkazujúca na uzol patrí za ňu.

**Appka z iného repa** sa inštaluje nástrojom, nie ručne:
`python3 tools/pfapp.py install ../etask-app-mojaapp` (`pfdoc runbook 2`).

## Kde je čo

```
etask-configuration/          PRÍKAZOVÝ priečinok — nič na čítanie
  processes/                  aplikačná logika, siete (toto upravuješ)
  processes.json, seed.json   manifest a cieľový stav rolí
  examples/skeleton.xml       najmenšia funkčná sieť
  tools/                      up.sh, pfnew, pflint, pfgroovy, pfi18n, pfview,
                              pfsync, pfseed, pfapi, pfapp, pfdoc, pftest
docs/                         dokumentácia (číta sa cez pfdoc, po kapitolách)
  reference/action-api.md     generovaný inventár primitív ← ČÍTAJ PRVÉ
  reference/cheatsheet.md     jedna strana pred prvým riadkom kódu
  RUNBOOK.md                  recepty 1–12
  PETRIFLOW_LEARNINGS.md      čo referencia nepokrýva alebo tvrdí zle
  ENGINE_ISSUES.md            defekty enginu — obídenie + návrh opravy
  obsidian/                   ako agent na tomto repozitári pracuje (graf)
etask-backend-starter/
  src/main/groovy/com/netgrif/etask/EtaskActionDelegate.groovy   ← vrstva 2
  src/main/groovy/com/netgrif/etask/startup/NetRunner.groovy     import sietí
```
