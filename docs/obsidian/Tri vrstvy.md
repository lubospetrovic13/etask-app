# Tri vrstvy

```
1. Petriflow XML          ← default. Stav, prechody, dáta, oprávnenia.
2. Custom action delegate ← I/O, cudzie API, výpočet nevyjadriteľný v akcii.
3. Framework / Angular    ← len render, HTTP vrstva, a čo engine nedá.
```

Pravidlo, ktoré to drží: **prechod o vrstvu nižšie musí byť odôvodnený vetou,
ktorá povie, ktoré primitívum na vyššej vrstve chýba.** Keď sa tá veta nedá
napísať, problém patrí vyššie.

Príklady odôvodnení, ktoré prešli:

- `usersWithRoleAll(rola)` — `roleRef` sa v prechode uvádza staticky, dynamicky
  sa vybrať nedá, takže rola sa musí premietnuť do `userList` poľa.
- `notifikuj(...)` — akcia nevie otvoriť SMTP spojenie, a hlavne nesmie zhodiť
  transakciu, keď SMTP nebeží.
- `saveWhileTyping` (vrstva 3) — `FormControl` vzniká v privátnom poli knižnice
  s `updateOn: 'blur'` a injection token preň neexistuje.

Vrstva 2 nie je záchranná brzda, je to **miesto, kde rastie jazyk**: metóda
v delegáte je nové Petriflow primitívum volateľné z každej siete.

Súvisí: [[Inventár metód]] · [[Ako agent pracuje]]
