# Example: work travel

Business trips: an employee keeps a vehicle profile, logs trips, and submits a monthly
expense report; the manager approves it and payroll gets it. The report is filled into the
company's own xlsx form (the template and the cell mapping are an attachment in the app's
settings, not code), including the signatures.

Installed on the `apps` branch, which also carries the two primitives the app needs from
the action delegate: `vyplnXlsx` (`XlsxFillService`, fills in the xlsx form) and
`prenesPrilohu` (carries the signature over from the previous claim). On `main` the rest
works, but the export reports that the form could not be filled in and the signature is
not carried over.

```bash
cd etask-configuration
python3 tools/cestycheck.py  # acceptance test against the running engine
```
