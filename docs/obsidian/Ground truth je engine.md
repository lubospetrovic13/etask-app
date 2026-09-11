# Ground truth je engine

Tri zdroje pravdy si na tomto stacku odporujú: schéma Petriflow, príručka
a runtime. **Platí runtime.**

- Import siete pri chybe vracia holé `{"status":500}` — dôvod je len v logu
  servera.
- Sieť sa naimportuje aj s komponentom, ktorý frontend nevie vykresliť; Angular
  nenahlási nič a vykreslí prázdno.
- Engine odmietnutie akcie **nehlási HTTP kódom**: `finish` blokovaný akciou
  vráti 200 a dôvod je v tele ako `error`.

Preto sa meria, nie háda: log servera, `curl` s `Accept-Language`, hodnota
v Mongu, sieťová záložka prehliadača. Posledný prípad z praxe:
[[Blur a klik sú jedna požiadavka|ukladanie počas písania]] vyzeralo hotovo,
kód sa skompiloval a nasadil — a `req_description` v Mongu bolo `undefined`.

Súvisí: [[Overovacia slučka]] · [[Tiché chyby]]
