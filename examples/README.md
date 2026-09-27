# Examples

Finished apps built on this platform. Each one is a folder with its Petriflow nets
(`processes/`), a manifest (`app.json`) and usually an acceptance test (`tools/`) that runs
against the live engine.

| example | what it shows | active |
|---|---|---|
| [onboarding](onboarding/) | the app from the demo video, with the request it was built from | **yes** |
| [dovolenky](dovolenky/) | leave requests: approval, return for completion, remaining balance | no |
| [objednavky-faktury](objednavky-faktury/) | orders and invoices: cost-centre approval, four eyes, reading invoice attachments, e-mail; on this branch extended by an invoice officer step ([BRIEF](objednavky-faktury/BRIEF.md)) | **yes, on this branch** |
| [majetok](majetok/) | asset register: the smallest complete app | no |
| [service-desk](service-desk/) | tickets from a public form without sign-in, triage, work items | no |

**Active** means installed in `ai-config/` and visible in the portal after
`docker compose up`. Only onboarding is, so a fresh start shows one clear example rather than
five. Every other example is installed with one command, described in its README:

```bash
cd ai-config
python3 tools/pfapp.py install ../examples/<name>
```

They are also good prompts: point your AI assistant at one and ask for something similar for
your own process.
