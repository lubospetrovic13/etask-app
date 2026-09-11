# Vzory z reálnych appiek

Čo vyšlo zo schvaľovania faktúr a objednávok a platí všeobecne:

- **Stav ako `enumeration_map`**, nie `text` — inak sa neprekladá.
  Do názvu prípadu stav nepatrí ([[Case.title sa neprekladá]]). `pfdoc runbook 9`
- **Read-only pohľad na celý život prípadu** — miesto so žetónom, ktoré nikto
  nekonzumuje. `pfdoc learnings B25`
- **Opakované položky** (riadky objednávky) — JSON je zdroj pravdy, renderovaný
  text je pre človeka. `pfdoc learnings B26`
- **Konfiguračná appka** — jeden prípad na verziu siete, hodnoty číta
  `najnovsiCase`. `pfdoc learnings B27`
- **Schvaľovanie podľa strediska** — rola → `userList` → `userRef`, s kaskádou
  keď stredisko schvaľovateľa nemá. `pfdoc runbook 11`
- **Štvoro očí patrí do `finish`**, nie do `assign` — výnimka z `assign` vráti
  holé HTTP 500 bez správy. `pfdoc engine E18`

Súvisí: [[Ako sa poznatok stane trvalým]] · [[Tiché chyby]]
