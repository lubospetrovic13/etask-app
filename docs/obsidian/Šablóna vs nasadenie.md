# Šablóna vs nasadenie

Repozitár `etask-app` je **šablóna**: framework, infraštruktúra, správa
používateľov a jedna príkladová appka (Service Desk).

Klientske appky žijú vo vlastných repách a do checkoutu sa dostanú nástrojom:

```bash
python3 tools/pfapp.py install ../etask-app-mojaapp
python3 tools/pfapp.py extract mojaapp ../etask-app-mojaapp --nets ... --nodes ...
```

Inštalácia mení `processes.json` a `seed.json` — to je **stav nasadenia**, nie
šablóny. Ručné zliepanie manifestu je zakázané, lebo [[Manifest mlčí]].

Súvisí: [[Ako agent pracuje]] · [[Nástroje]]
