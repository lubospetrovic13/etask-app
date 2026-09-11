---
name: petriflow
description: Práca s Petriflow sieťami v tomto repozitári — tvorba a úprava procesov (.xml v etask-configuration/processes), akcie v Groovy, oprávnenia, dátové polia, formuláre, menu. Použi VŽDY pred písaním alebo úpravou Petriflow siete, a tiež keď sa rozhoduješ, či má funkcionalita ísť do Petriflow, do action delegate alebo do Java/Angular kódu. Trigger aj na: proces, sieť, transition, dataGroup, taskRef, dataRef, roleRef, userRef, action delegate, setData, createCase.
---

# Petriflow v tomto repozitári

Aplikačná logika je v Petriflow sieťach, nie v Jave a nie v Angulari. Framework
je ~5 500 riadkov, siete ~7 500 — ten pomer je zámer a má sa udržať.

Tento súbor je **rozcestník**: rozhodnutia a čo si pri nich pýtať. Podrobnosti sú
v súboroch vedľa a v dokumentácii, ktorá sa číta **po kapitolách**:

```bash
cd etask-configuration
python3 tools/pfdoc.py hladaj "menu"     # v ktorej kapitole to je
python3 tools/pfdoc.py runbook 4         # len tá kapitola
```

## Tri rozhodnutia, v tomto poradí

**1. Existuje to už?** Otvor `docs/reference/action-api.md` — generovaný inventár
metód enginu aj projektu, volateľných z `<action>` menom, bez importov. Delegát
je **dynamický**: preklep v názve metódy prejde parserom aj importom a spadne až
za behu. Ten zoznam je jediná obrana — a vznikol preto, že bez neho bola
postavená horšia verzia už existujúceho extension pointu.

**2. Ktorá vrstva?**

```
1. Petriflow XML          ← default. Stav, prechody, dáta, oprávnenia case-u.
2. Custom action delegate ← ROZŠIRUJE JAZYK. Nová metóda = nové primitívum
                            volateľné menom z každej siete.
3. Framework/runtime kód  ← len render, HTTP vrstva, a čo engine nedá.
```

Prechod nižšie musí byť odôvodnený vetou, ktorá povie, **ktoré primitívum na
vyššej vrstve chýba**. Tá veta je zároveň bug report pre framework. Keď sa
nedá napísať, problém patrí vyššie. Vrstva 2 nie je záchranná brzda — je to
mechanizmus, ktorým rastie slovník. Podrobne: [delegat.md](delegat.md).

**3. Ako to overíš?** Lacné pred drahým, a `pfsync` nie je voliteľný krok:

```bash
python3 tools/pflint.py processes/     # 0,3 s  štruktúra a tiché pasce
python3 tools/pfgroovy.py processes/   # 3 s    syntax akcií
python3 tools/pfi18n.py processes/     #        každý viditeľný text má preklad
python3 tools/pfview.py                #        vykreslí to frontend?
python3 tools/pfsync.py --sync         #        import do enginu + role
```

**Ground truth je engine.** Keď si offline nástroj a engine odporujú, chyba je
v nástroji, nie v sieti. Podrobne: [overovanie.md](overovanie.md).

## Čo mlčí

Typická chyba tu **nie je výnimka** — je to stav, keď všetko vráti 200 a niečo
jednoducho nie je. Tie, ktoré stoja najviac času:

| pasca | prejav |
|---|---|
| `u?._id` na `UserFieldValue` | `MissingPropertyException` v strede akcie: časť zmien zapísaná, zvyšok nie |
| `findCase { it.stringId.eq(id) }` | vždy `null`, v logu len INFO |
| read arc z **konzumovaného** miesta | read-only úloha zmizne po odmietnutom DOKONČIŤ a už sa nevráti |
| `roleRef` + `userRef` | **zjednocujú sa**, neprienikajú — „rola X a zároveň pridelený Y" sa deklaratívne napísať nedá |
| rola má `stringId` per verziu siete | po re-importe treba role prideliť znova, inak 403 |
| case drží verziu siete | nové polia a prechody do starého prípadu nepribudnú |
| `async.run { }` | výnimku spolkne, cieľový case je len prázdny |

Celý zoznam s obídeniami: [pasce.md](pasce.md), `pfdoc learnings`, `pfdoc engine`.

## Nová appka

```bash
cd etask-configuration
python3 tools/pfnew.py mojaapp ziadost "Žiadosť o niečo" --role pracovnik
```

Generátor už nesie vzory, ktoré sa inak vymyslia zle (preložiteľný stav, názov
prípadu bez stavu, `pripoj_do_uzla`, `allowedNets`). **Pridanie appky Javu
nevyžaduje** (rozšíriť platformu kvôli schopnosti, ktorú engine nemá, je iná vec
a je v poriadku — [delegat.md](delegat.md)). Manifest sa needituje ručne — `pfnew` alebo `pfapp`, lebo každá
z jeho štyroch sekcií vie chýbať tak, že to nič nepovie.
Podrobne: [nova-appka.md](nova-appka.md).

Funkčný príklad je pri Petriflow užitočnejší než špecifikácia: Service Desk
(`processes/sd_*.xml`, `pfdoc sd`) — verejný viackrokový eForm cez taskRef,
child casy, per-organizačné oprávnenia, SLA.
