# Example: orders and invoices

Purchase orders and incoming invoices with approval by the approver of the cost centre, a four-eyes rule and posting by the accountant. The invoice is read from its attachment (e-invoice XML, PDF, OCR) by the `precitajFakturu` primitive, and people are notified by e-mail with `notifikuj`.

It was built on this platform with an AI assistant, before this repository existed. The
original written request was not kept, so unlike [onboarding](../onboarding/) there is no
`request.md` to replay.

## Install it into your running instance

```bash
cd ai-config
python3 tools/pfapp.py install ../examples/objednavky-faktury
```

Give the test users the roles of the app in `ai-config/seed.json`:

| user | roles |
|---|---|
| `super@netgrif.com` | `riaditel`, `schv_hotel`, `schv_marketing`, `schv_restauracia`, `schv_sprava`, `schv_udrzba`, `schv_wellness`, `schvalovatel`, `spravca`, `uctovnik`, `zadavatel` |
| `admin@test.local` | `riaditel`, `schv_restauracia`, `schv_wellness`, `schvalovatel`, `spravca`, `uctovnik` |
| `operator@test.local` | `schv_wellness`, `schvalovatel`, `uctovnik`, `zadavatel` |
| `druhy@test.local` | `zadavatel` |

Then rebuild and restart from the repository root. The menu card and the views come from the
manifest, which is packed into the backend image, so without the rebuild the process runs but
has no card in the portal.

```bash
docker compose up -d --build
```

Sign out and back in, because a running session keeps the old roles. Prove it works, from `ai-config/`:

```bash
python3 tools/sccheck.py
```

To remove it again: `python3 tools/pfapp.py remove objednavky-faktury`, then rebuild.

---

## Design notes (Slovak)


Petriflow appka pre eTask. Zije vo vlastnom repozitari; do konkretneho
nasadenia sa dostane nastrojom starteru:

```bash
cd ai-config
python3 tools/pfapp.py install ../examples/objednavky-faktury
python3 tools/pfsync.py --sync        # import do bezuceho enginu + role
```

Co je tu:

| subor | co to je |
|---|---|
| `processes/fa_faktura.xml` | siet |
| `processes/ob_objednavka.xml` | siet |
| `processes/sc_menu.xml` | siet |
| `processes/sc_nastavenia.xml` | siet |
| `tools/sccheck.py` | akceptacny test proti beziacemu enginu |
| `docs/PRIRUCKA.md` | dokumentacia appky |
| `app.json` | manifest appky - `import`, `bootstrapCase`, `uriNodes`, `netScope` |

**Role appka nikomu neprideluje.** Kto ktoru rolu dostane, je rozhodnutie
nasadenia a dopisuje sa do `seed.json` starteru (`netScope` doplni `install`).
