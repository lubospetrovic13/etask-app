# Tiché pasce

Spôsoby, ako Petriflow zlyhá bez chybovej správy. `pflint` ich hľadá, ale poznaj
ich aj tak. Plný zoznam s meraniami: `pfdoc learnings`, `pfdoc engine`.

* **`u?._id` zhodí celú akciu.** Groovy `?.` chráni pred null, **nie** pred
  chýbajúcou property. Na `UserFieldValue` vyhodí `MissingPropertyException`
  a akcia spadne v strede: časť zmien zapísaná, zvyšok nie, v odpovedi nič.
  Použi `userIdsOf()`, prípadne `u.hasProperty("id") ? u.id : null`.
* **`findCase { it.stringId.eq(id) }` vráti vždy null.** `Case` v Mongu pole
  `stringId` nemá. V logu je len INFO. Použi
  `it._id.eq(new org.bson.types.ObjectId(id))`, alebo choď cez `it.caseId` tasku.
* **`async.run { }` výnimku spolkne.** Prenos dát medzi casmi sa prejaví len tým,
  že cieľový case je prázdny. Rob to synchrónne v `try/catch`.
* **Button nevidí hodnotu textového poľa v tej istej požiadavke.** Blur a klik
  sú jedna požiadavka, takže akcia prečíta hodnotu spred písania. Buď
  `immediate="true"`, alebo `<property key="saveWhileTyping">true</property>`
  (`pfdoc runbook 6`). `pflint` to hlási ako `button-reads-text`.
* **`roleRef` a `userRef` sa zjednocujú, nie prienikajú.** „Rola X a zároveň
  pridelený Y" sa deklaratívne napísať nedá. Na to je primitív v delegáte:

  ```groovy
  def agents = usersWithRole(customer.dataSet["c_agents"]?.value, "agent")
  change tk_agents value { agents }
  ```

  Rola zostáva autoritatívna — koho niekto pridá do zoznamu omylom a rolu nemá,
  prístup nedostane. Vzor je v `sd_ticket` (`apply_customer`).
* **Read-only pohľad na read arcu z konzumovaného miesta zmizne natrvalo.**
  Keď na tom mieste niekto klikne DOKONČIŤ a dokončenie sa odmietne (prázdne
  `required` pole alebo výnimka z `phase="pre"`), engine tú read-only úlohu
  zmaže a už ju neobnoví — token sa nepohol, takže nie je čo ju znova povoliť.
  Veď ho z miesta, ktoré **nikto nekonzumuje** (`pfdoc learnings B8b` kam nie,
  `B25` kam áno).
* **Rola má stringId per verziu siete.** Po re-importe treba role prideliť znova.
  Oprávnenie cez `userRef` re-import prežije, cez `roleRef` nie.
* **Nové dátové pole sa nepropaguje do existujúcich casov.** Case drží verziu.
* **`Case.title` ani `text` pole sa neprekladajú** — obe sú `String`. Stav preto
  patrí do `enumeration_map` a nie do názvu prípadu (`pfdoc runbook 9`).
* **Výnimka z akcie v `assign` vráti holé HTTP 500** bez správy; to isté vo
  `finish` vráti 200 a dôvod v tele. Kontroly (napr. štvoro očí) patria do
  `finish` (`pfdoc engine E18`).
* **Task dokument v indexe nemá `processIdentifier`** — zobrazenie typu Task
  filtruj cez `transitionId` + `processId` (`pfdoc runbook 11`).

## Dialekt: tri zdroje pravdy, ktoré si odporujú

Nedôveruj schéme z hlavičky siete. Poradie podelementov `<data>`:

| zdroj | tvrdí |
|---|---|
| `docs/reference/petriflow.schema.v1.1.0.xsd` (oficiálna) | `init` pred `component` |
| NAE 6.3.1 za behu | prijme aj `component` pred `init` |
| `pfdoc learnings B5` | `desc` hneď za `title` |

Siete v tomto repozitári porušujú schému a importujú sa. `pflint` preto poradie
**vedome nekontroluje**. Keď potrebuješ istotu, `pfcheck` je jediná odpoveď.
