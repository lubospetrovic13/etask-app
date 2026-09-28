# Ako vznikol krok referenta: zadanie a priebeh

Rozšírenie appky Objednávky a faktúry o kontrolu referentom vzniklo z jedného promptu
a Word dokumentu od kolegov, v Claude Code nad týmto repozitárom. Tu je vstup a čo z neho
postupne vzniklo.

## Vstup

**Dokument** *Faktúry a objednávky* (od kolegov): opis procesov bez technických detailov.
Faktúry prichádzajú tromi kanálmi (e-mail s OCR, sieťový disk, ručne), tím referentov ich
kontroluje, dopĺňa a páruje na objednávku vrátane dodania po položkách, schvaľujú sa podľa
konfigurovateľnej matice vo viacerých kolách s možnosťou vrátenia, na konci export do
účtovníctva a archív. Objednávky sa schvaľujú cez konfigurovateľné úrovne a evidujú sa
dodávky. Integrácie: IMAP, dodávateľ podľa IČO, archív cez SOAP, XML pre účtovný systém.

**Prompt** (27. 9. 2026, 14:54), doslova:

```
@"Faktury a objednavky.docx"
takyto popis appky mam od kolegov, sprav inu branchu a daj nastrel appky co by sa
v netgrife dala spravit teda ten dokument
```

K promptu bol vložený text dokumentu. Nič iné (stavy, roly, polia) zadané nebolo.

## Priebeh

| kedy | prompt | výsledok |
|---|---|---|
| 27. 9. 14:54 → 15:27 | dokument + prompt vyššie | krok referenta, vstupné kontroly, pravidlo „schválenie netreba“, vrátenie na predošlé úrovne, XML pre účtovníctvo, [BRIEF.md](../BRIEF.md); na čistej databáze pôvodný test 234/0, nový `fakcheck` 35/0 |
| 27. 9. 16:38 | kto kontroluje, má vidieť faktúru na pol obrazovky | doklad vedľa formulára vo všetkých piatich krokoch faktúry |
| 27. 9. 18:19 | „sprav všetkých 7“ (návrhy AI na vzhľad) | sekcie, nápoveda v ikonke, farebné štítky kontrol, pripnutá lišta s tlačidlami |
| 28. 9. 07:54 | všade kompaktne a over v builderi | kompaktný vzhľad na každom formulári, oprava rozloženia v builderi |
| 28. 9. 08:58 | vyťaženie nech začne pri nahratí | faktúra sa prečíta hneď po nahratí prílohy (XML, PDF, OCR) |

## Čo AI sama označila

- **Domyslené:** pravidlo, kedy schvaľovanie netreba (faktúra krytá schválenou objednávkou,
  dodaná kompletne a nie drahšia). Dokument hovorí len „podľa naprogramovaných pravidiel“.
- **Otázky na kolegov:** päť, sú v [BRIEF.md](../BRIEF.md).
- **Nepostavené:** IMAP, sieťový priečinok, dodávateľ podľa IČO, archív, PDF sprievodný list,
  reporty. Pri každej je v BRIEF-e veta, aké primitívum platformy by bolo treba.

## Kde to pozrieť

- appka: vetva `invoices-orders` (samostatne) alebo `apps` (spolu s ďalšími appkami)
- overenie: `python3 tools/sccheck.py` a `python3 tools/fakcheck.py` proti bežiacemu enginu
