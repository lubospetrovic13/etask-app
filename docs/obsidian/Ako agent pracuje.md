# Ako agent pracuje

Slučka, ktorá sa opakuje pri každej úlohe na tomto repozitári:

1. **Zisti, čo už existuje** — [[Kontext a tokeny]]. Neexistujúce primitívum sa
   píše draho, existujúce sa zavolá menom ([[Inventár metód]]).
2. **Rozhodni vrstvu** — [[Tri vrstvy]]. Default je Petriflow sieť.
3. **Napíš najmenšiu zmenu**, ktorá to celé dokáže — sieť, potom delegát,
   frontend až keď sa dá napísať veta, ktoré primitívum chýba.
4. **Over** — [[Overovacia slučka]]. Offline nástroje sú lacné, engine je
   [[Ground truth je engine|pravda]].
5. **Zmeraj namiesto hádania** — keď sa niečo správa inak, než dokumentácia
   tvrdí, odpoveď dá bežiaci systém: log, `curl`, Mongo, prehliadač.
6. **Nález zafixuj**, nech sa nevráti — [[Ako sa poznatok stane trvalým]].

Čo túto prácu odlišuje od bežného programovania, je [[Tiché chyby|kategória chýb]],
ktoré tu prevládajú: nie výnimky, ale ticho.

Súvisí: [[Šablóna vs nasadenie]] · [[Vzory z reálnych appiek]] · [[Nástroje]]
