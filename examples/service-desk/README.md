# Example: Service Desk

Tickets for signed-in customers: organisations with their SLA plans, a new ticket from the
menu card, one task per phase for the agent (Triage, Work, Follow-up, Archive), SLA hours,
a dashboard, and an SLA contract signed electronically through DocuSeal.

Installed on the `service-desk` branch. That branch also carries the code the nets need
outside Petriflow: the `SignService` delegate primitive, the DocuSeal container in the
Docker stack, and the form views and dashboard in the frontend. Installing this folder on
`main` works except for the signing step.

```bash
cd etask-configuration
python3 tools/sdcheck.py     # acceptance test against the running engine
python3 tools/sddemo.py      # demo organisations and tickets
```

Design notes and the full walkthrough (Slovak): [`docs/SERVICE_DESK.md`](docs/SERVICE_DESK.md).
