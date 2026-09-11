# Blur a klik sú jedna požiadavka

Dátové pole sa štandardne uloží až keď stratí fokus — nie je to rozhodnutie
ukladacej vrstvy, je to jeden riadok knižnice:

```
AbstractDataFieldComponent:  new FormControl('', {updateOn: 'blur'})
```

Keď človek píše do poľa a klikne na tlačidlo v tom istom formulári, prehliadač
to spracuje ako **jednu** požiadavku: akcia za tlačidlom prečíta hodnotu spred
písania. `pflint` to hlási pravidlom `button-reads-text`.

Pole si vie vypýtať ukladanie počas písania
(`<property key="saveWhileTyping">true</property>`). Je to voliteľné zámerne:
odpoveď servera sa zapisuje späť do inputu, takže na poli, ktoré akcia
prepisuje, by to prepísalo text pod rukami. `pfdoc runbook 6`

Súvisí: [[Tiché chyby]] · [[Ground truth je engine]]
