# Testovacie príklady

Štyri ukážky klientskej komunikácie na overenie kategorizácie a vyťaženia.
Vlož obsah súboru do poľa **JSON s dátami komunikácie** v tasku Test volania
(režim **Vložiť JSON**) a klikni Spustiť test.

| súbor | očakávaná kategória | čo testuje |
|---|---|---|
| `01-objednavka.json` | `objednavka` | jednoznačná kategória, veľa údajov v prílohe, položky, sumy, IČO, termín |
| `02-upomienka.json` | `upomienka` | čísla faktúry a variabilného symbolu, suma, dátum splatnosti, vysoká urgencia |
| `03-reklamacia.json` | `reklamacia` | odkaz na objednávku aj faktúru, čiastočná dodávka, alternatívne riešenia |
| `04-viac-temat.json` | `otazka` alebo `zmena` | **tri témy v jednej správe** - nízka confidence je správna odpoveď |

## Na čo si pozerať vo výsledku

**01 - objednávka.** Sumy sú v prílohe, nie v tele mailu. Ak model vytiahne
`amount: 1792.80` a `order_number: "OD-2026-0451"`, prílohy sa naozaj dostali do
promptu. `items` by mali obsahovať tri položky s množstvami.

**02 - upomienka.** `variable_symbol` je `"20260117"` ako **text**, nie číslo -
prompt to explicitne žiada, aby sa nestratili úvodné nuly. `due_date` má byť
`2026-03-18` (termín z upomienky), nie `2026-02-14` (pôvodná splatnosť).
`urgency` by mala byť vysoká.

**03 - reklamácia.** Má `order_number` aj `invoice_number` naraz - dobrý test, či
model nezamení jedno za druhé. `amount` je 139,50 (dobropis), nie celá dodávka.

**04 - viac tém.** Zámerne nejednoznačné: otázka na dostupnosť, zmena adresy
a žiadosť o faktúru v jednej správe. Správna odpoveď je **jedna kategória s nižšou
confidence** (okolo 0,4 az 0,6) a `summary`, ktoré zmieni všetky tri veci. Ak model
vráti confidence 0,95, prompt je príliš dôverčivý a treba doladiť.
Číslo objednávky je uvedené neisto („myslím že") - model by ho mal buď vytiahnuť,
alebo dať null, ale nie si vymyslieť iné.

## Rýchly test bez JSON-u

Režim **Vyplniť formulár** má predvyplnenú reklamáciu, takže Spustiť test funguje
hneď bez akéhokoľvek vkladania.

## Test cez ZIP

Zabaľ ktorýkoľvek z týchto súborov pod názvom `mail.json` do ZIP-u a nahraj ho
v režime **Nahrať ZIP**. Do toho istého archívu môžeš pridať `.txt` súbory - budú
sa brať ako ďalšie prílohy a spoja sa s tými z `mail.json`.
