# Ako sa poznatok stane trvalým

Nález, ktorý skončí len v odpovedi v chate, sa o mesiac zopakuje. Preto má každý
tri možné domovy — a dobrý nález dostane všetky tri:

| kde | čo to spraví |
|---|---|
| **dokumentácia** | pri tom kroku, kde sa na to narazí (`pfdoc runbook 4`) |
| **nástroj** | lint pravidlo alebo kontrola, ktorá to nájde sama |
| **test** | akceptačný krok, aby sa to nevrátilo |

Príklady z tohto repozitára:

- Prekrytie v gride → pravidlo `grid-overlap` v `pflint` + fixture.
- Rovnaké názvy dvoch zobrazení → kontrola v `sccheck` + veta v RUNBOOK 4.
- Generátor učil vyvrátený vzor → `pftest` spustí `pfnew` a skontroluje, čo
  vygeneroval.
- `processes.json` chýbal v obraze → `test -f` v Dockerfile aj v CI.

Súvisí: [[Tiché chyby]] · [[Nástroje]]
