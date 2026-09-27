# pfview-src / pfview-nets — fixtures pre pfview

Toto nie sú ukážky. Sú to **rozbité** vstupy, na ktorých `pfview` MUSÍ zlyhať.
Nástroj, ktorý hlási len OK, nikto neoverí a nikto mu neverí; `pftest.sh` ho
preto púšťa aj sem a čaká nenulový exit.

Každý súbor obsahuje práve jednu z tých troch tichých chýb:

| súbor | chyba | ako by sa prejavila v appke |
|---|---|---|
| `stale-resolver.component.html` | kópia knižničného resolvera bez vetiev pre `FILTER`, `I18N`, `TASK_REF` | pole takého typu sa vykreslí ako prázdne miesto |
| `bypass.component.html` | `<nc-task-list>` namiesto vlastného `<app-etask-task-list>` | vlastné field komponenty sa nezobrazia vôbec |
| `../pfview-nets/bad_component.xml` | `<name>` mimo inventára a preklep v `<property key>` | knižnica ticho vykreslí default |

`owner.component.ts` je tu len preto, aby `bypass.component.html` mal čo
obchádzať — deklaruje `app-etask-task-list` v inom priečinku, takže výnimka
„vlastný komponent smie knižničný obaliť vo svojej vlastnej šablóne" sa
neuplatní.
