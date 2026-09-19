# Copilot instructions

**Read [`AGENTS.md`](../AGENTS.md) at the repository root first.** It holds the full rules and
it is the file the other assistants read, so it is kept current. This file exists because
Copilot looks here rather than there; it is a pointer plus the few rules that matter most.

- Application logic belongs in **Petriflow nets** (`etask-configuration/processes/*.xml`), not
  in Java and not in Angular. Never start in framework code.
- Moving down a layer (net, then action delegate, then framework) has to be justified by one
  sentence naming **which primitive is missing one layer up**.
- Adding an application does not require Java. Generate it with
  `python3 tools/pfnew.py`, never by hand editing the manifest.
- Verify with `pflint`, `pfgroovy`, `pfi18n`, `pfview`, then `pfsync --sync`. **Ground truth is
  the running engine**, and a failed import returns a bare `{"status":500}` whose reason is only
  in the server log.
- The engine imports a net only when it is **missing** from the database. After editing an
  existing net, nothing happens at startup until `pfsync --sync` runs.
- Java **11**. Not 17, not 21.
- Never run `pfcheck` or `pfsync --sync` against production.

The documentation is in Slovak, in `docs/`, indexed by `tools/pfdoc.py`. Read one chapter, not
the whole set.
