# AGENTS.md

Rules for any AI coding assistant working in this repository: Cursor, Codex, Copilot,
Gemini CLI, Windsurf, Claude Code.

**`CLAUDE.md` is the source of truth.** It is in Slovak and it is short by design. Read it.
This file is the same content in English so that the rules are not restated in two places
and allowed to drift. Where the two disagree, `CLAUDE.md` wins.

Two assistants look elsewhere by default, so they are pointed back here rather than given a
third copy: `.github/copilot-instructions.md` for GitHub Copilot and `.gemini/settings.json`
for Gemini CLI. If you change a rule, change `CLAUDE.md` and this file. Those two are
pointers and should stay that way.

---

## What this repository is

A Petriflow-first application stack on the Netgrif Application Engine 6.3.1. The
application logic belongs in Petriflow nets, **not in Java and not in Angular**. The
framework is around 5 500 lines and the nets around 9 700. That ratio is intentional, and
keeping it is part of your job here.

## Before you change anything

Read `docs/reference/cheatsheet.md` (around 2 000 tokens): the procedure, the eight
decisions that determine whether it will work at all, and the list of things that fail
silently.

For nets, actions, permissions and forms, read `.claude/skills/petriflow/SKILL.md`. It is
written as a Claude Code skill but it is plain Markdown and applies to any assistant.

Do not read the documentation file by file. It is around 86 000 tokens in total and is
indexed by chapter, at roughly 500 tokens each:

```bash
cd etask-configuration
python3 tools/pfdoc.py                  # what is where, priced in tokens
python3 tools/pfdoc.py hladaj "menu"    # which chapter covers it
python3 tools/pfdoc.py runbook 4        # just that chapter
```

`docs/RUNBOOK.md` has a verified recipe for most common tasks. Do not improvise past one.

## The three layers

```
1. Petriflow XML          <- the default. State, transitions, data, case permissions.
2. Custom action delegate <- I/O, foreign APIs, computation an action cannot express.
3. Framework/runtime code <- rendering, the HTTP layer, and what the engine does not provide.
```

**Never start at layer 3.** Moving down a layer has to be justified by one sentence naming
**which primitive is missing one layer up**. If you cannot write that sentence, the problem
belongs higher.

Layer 2 is not an escape hatch, it is where the language grows. A method on
`EtaskActionDelegate` is a new Petriflow primitive, callable by name from every net. When
you write the same Groovy in a second net, move it there.

**Before writing a new delegate method**, open `docs/reference/action-api.md`, the generated
inventory of engine and project methods. The delegate is dynamic, so a typo passes both the
parser and the import and only fails at runtime. That list is the only defence.

## Adding an application

```bash
cd etask-configuration
python3 tools/pfnew.py myapp request "Request for something" --role worker
```

This generates the net, the menu net with views and columns, updates the manifest and
writes an acceptance test. **Adding an application does not require Java.** The manifest has
four sections across two files (`import`, `bootstrapCase`, `uriNodes`, `netScope`) and each
one can be missing in a way that reports nothing, which is why it is not edited by hand.

## Verification

After a net change, in this order:

```bash
cd etask-configuration
python3 tools/pflint.py processes/        # 0.3 s
python3 tools/pfgroovy.py processes/      # 3 s
python3 tools/pfi18n.py processes/        # every visible string has a translation
python3 tools/pfview.py                   # the frontend renders what the net asks for
python3 tools/pfsync.py --sync            # import plus roles, only what diverged
```

`python3 tools/pfloop.py --fix` runs the same chain at once, applies the fixes that have an
unambiguous solution, and writes the rest as a task list into `.run/pfloop-zadanie.md`.

**Ground truth is the running engine.** On failure the import endpoint returns a bare
`{"status":500}` with no reason and the cause is only in the server log. Without an import
a net is not verified.

`NetRunner` imports a net only when it is **missing** from the database. After you change an
existing XML, nothing happens at startup: the engine keeps the old model and new cases are
created from it, with no message anywhere. `pfsync --sync` is what fixes that.

Two consequences, each worth at least one debugging session:

* **A case keeps the net version it was created from.** Testing on an old case after a
  change tests the old model.
* **After roles are assigned, sign out and back in.** A live session holds the old role
  `stringId` and creating a case returns **403**.

When an offline tool and the engine disagree, **the tool is wrong**. Fix the tool and run
`tools/pftest.sh`.

If you touched startup order, URI nodes, the manifest or the runners, add one more step, a
clean database, and **ask the user first because it deletes data**:

```bash
etask-configuration/tools/up.sh --docker --fresh --build
```

A running instance carries state from earlier runs and that is exactly what masks ordering
bugs.

## Do not

* Do not add an Angular component for something a net can express.
* Do not write a Java service before it is proven the delegate cannot do it.
* Do not trust the schema in the net header. The runtime differs from it.
* Do not check the order of `<data>` subelements in tooling. Three sources of truth
  contradict each other, nets violate the schema, and they import anyway.
* **Do not run `pfcheck` or `pfsync --sync` against production.** They import a new net
  version.
* Do not hang a read-only view on a read arc from a place that some transition consumes.
  A rejected `finish` deletes that task and never restores it.
* Do not read `docs/petriflow_reference.md` whole (27 000 tokens). Use `pfdoc hladaj`.

## Environment

* Java **11**. Not 17, not 21: Groovy 3 fails with `Unsupported class file major version`.
* `LANG=C.UTF-8` is required, otherwise importing a process with diacritics in its name
  throws `InvalidPathException`.
* `certificates/private.der` is gitignored, so it is missing after `git clone`. Without it
  the engine does not sign the anonymous session and **public forms return 401** with no
  message connecting it to the key. `up.sh` calls `bootstrap.sh` and generates it.

## Running it

```bash
etask-configuration/tools/up.sh           # the whole stack, idempotent
etask-configuration/tools/up.sh --docker  # the same thing entirely in Docker
```

`EtaskRunner` prints a security check at every startup: default admin password, test
accounts, missing key. When you see that in the log it is not noise.

## Language

The repository documentation is in Slovak. Code, identifiers, net IDs and tool names are
not. Write code and identifiers in the language already used by the file you are editing.
