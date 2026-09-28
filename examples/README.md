# Examples

Finished apps built on this platform. Each one is a folder with its Petriflow nets
(`processes/`), a manifest (`app.json`) and usually an acceptance test (`tools/`) that runs
against the live engine.

None of them is installed on `main`: a fresh `main` starts with user management only.
Each example has a branch where it is installed and ready after `docker compose up`:

| example | what it shows | branch |
|---|---|---|
| [onboarding](onboarding/) | the app from the demo video, with the request it was built from | `onboarding`, `apps` |
| [service-desk](service-desk/) | tickets for signed-in customers, organisations, SLA plans, SLA contract signing | `service-desk` |
| [invoices-orders](invoices-orders/) | orders and invoices: invoice officer check, cost-centre approval, reading invoice attachments, e-mail | `invoices-orders`, `apps` |
| [vacations](vacations/) | leave requests: approval, return for completion, remaining balance | `apps` |
| [work-travel](work-travel/) | business trips: vehicle profile, trip log, expense report filled into an xlsx form | `apps` |

To install one into your own checkout:

```bash
cd etask-configuration
python3 tools/pfapp.py install ../examples/<name>
tools/up.sh
```

`pfapp` writes the app into `processes.json` and `seed.json`. Two things it leaves to you:
the category above the app's folder (`it`, `hr`, `financie`) in `uriNodes`, and which users
get the app's roles in `seed.json`. The branches show both filled in.

Service Desk and work travel need code outside the nets (DocuSeal signing, the xlsx
filler); that code is on their branches, not on `main`.

The examples are also good prompts: point your AI assistant at one and ask for something
similar for your own process.
