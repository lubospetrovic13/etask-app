# Tiché chyby

Typická chyba na tomto stacku **nie je výnimka**. Je to stav, keď všetko vráti
200 a niečo jednoducho nie je.

Zoznam nie je úplný — je to kategória, ktorú treba mať v hlave:

- [[Manifest mlčí]] — appka bez `uriNodes` sa naimportuje a karta nie je vidno.
- [[Case drží verziu siete]] — testuješ starý model a nevieš o tom.
- [[URI uzly sú v Elasticu]] — priečinok je, položky sú, a je prázdny.
- [[Case.title sa neprekladá]] — appka je dvojjazyčná okrem toho, čo sa číta
  najčastejšie.
- [[Read arc z konzumovaného miesta]] — read-only pohľad zmizne po prvom
  odmietnutom DOKONČIŤ a už sa nevráti.
- [[Blur a klik sú jedna požiadavka]] — akcia za tlačidlom číta hodnotu spred
  písania.
- `instanceof` v produkčnom builde — trieda je minifikovaná, podmienka je vždy
  `false` a funkcia ticho nerobí nič.

Obrana je vždy rovnaká: **nech to praskne skoro a nahlas** — lint pravidlo,
kontrola v teste, alebo aspoň veta v dokumentácii pri tom kroku.

Súvisí: [[Ako sa poznatok stane trvalým]] · [[Ground truth je engine]]
