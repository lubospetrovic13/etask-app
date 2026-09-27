# Example: asset register

A register of company equipment kept by the asset manager. The smallest example here: one data net, one menu net and one role.

It was built on this platform with an AI assistant, before this repository existed. The
original written request was not kept, so unlike [onboarding](../onboarding/) there is no
`request.md` to replay.

## Install it into your running instance

```bash
cd ai-config
python3 tools/pfapp.py install ../examples/majetok
```

Give the test users the roles of the app in `ai-config/seed.json`:

| user | roles |
|---|---|
| `super@netgrif.com` | `spravca_majetku` |
| `admin@test.local` | `spravca_majetku` |

Then rebuild and restart from the repository root. The menu card and the views come from the
manifest, which is packed into the backend image, so without the rebuild the process runs but
has no card in the portal.

```bash
docker compose up -d --build
```

Sign out and back in, because a running session keeps the old roles. Prove it works, from `ai-config/`:

```bash
python3 tools/majetokcheck.py
```

To remove it again: `python3 tools/pfapp.py remove majetok`, then rebuild.

---

## Design notes (Slovak)


Petriflow appka pre eTask. Zije vo vlastnom repozitari; do konkretneho
nasadenia sa dostane nastrojom starteru:

```bash
cd ai-config
python3 tools/pfapp.py install ../examples/majetok
python3 tools/pfsync.py --sync        # import do bezuceho enginu + role
```

Co je tu:

| subor | co to je |
|---|---|
| `processes/ma_zariadenie.xml` | siet |
| `processes/ma_menu.xml` | siet |
| `tools/majetokcheck.py` | akceptacny test proti beziacemu enginu |

| `app.json` | manifest appky - `import`, `bootstrapCase`, `uriNodes`, `netScope` |

**Role appka nikomu neprideluje.** Kto ktoru rolu dostane, je rozhodnutie
nasadenia a dopisuje sa do `seed.json` starteru (`netScope` doplni `install`).
