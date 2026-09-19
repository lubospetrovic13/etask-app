# eTask

[![Open in GitHub Codespaces](https://img.shields.io/badge/Open_in-GitHub_Codespaces-2497f2?logo=github&logoColor=white)](https://codespaces.new/lubospetrovic13/etask-app)
[![Open in Dev Container](https://img.shields.io/badge/Open_in-Dev_Container-3abead?logo=visualstudiocode&logoColor=white)](https://vscode.dev/redirect?url=vscode%3A%2F%2Fms-vscode-remote.remote-containers%2FcloneInVolume%3Furl%3Dhttps%3A%2F%2Fgithub.com%2Flubospetrovic13%2Fetask-app)
[![Open in Claude Code](https://img.shields.io/badge/Open_in-Claude_Code-6038b2?logo=claude&logoColor=white)](#one-click-if-you-already-have-claude-code)

A Petriflow-first application stack on top of the Netgrif Application Engine 6.3.1.

The database, the REST layer, the frontend, login, IAM, roles and permissions are already
here and already work. What you add is the **business logic**: Petriflow nets. The
framework is around 5 500 lines, the nets around 9 700, and that ratio is the point.

This is the repository behind the recorded demo where one Word document from the business
("onboarding a new employee") became a running agenda in the portal. The nets that came out
of it are `etask-configuration/processes/on_request.xml` and `on_menu.xml`.

---

## Run it

Two ways. Pick the first unless you already have Java 11 on the machine.

### Everything in Docker (recommended)

You need **Docker Desktop** and **Git**. On Windows run the command from **Git Bash**, not
from PowerShell or cmd. No Java, no Maven and no Node on your machine: all three live in the
images. **Python 3** is the one extra, and only once you start working on nets, because the
checking tools in `etask-configuration/tools/` are Python. Running the app does not need it.

```bash
git clone https://github.com/lubospetrovic13/etask-app.git
cd etask-app
etask-configuration/tools/up.sh --docker
```

The first run builds the backend and frontend images, which is Maven plus an Angular
build: budget ten minutes or so, and most of it is that one build. Every run after that is
under two minutes, because `up -d` reuses the images.

**Give Docker at least 6 GB.** Mongo reserves 1.5 GB of cache, Elasticsearch takes up to
1 GB of heap and the backend up to 2 GB. Below that the backend is killed mid startup and
the failure looks like a hang rather than a memory problem.

| what | where |
|---|---|
| portal | http://localhost:4200 |
| backend API | http://localhost:8080 |
| all mail the app sends | http://localhost:8025 |
| Mongo | localhost:27017 |
| Elasticsearch | http://localhost:9200 |

Sign in as `super@netgrif.com` / `password`.

Then prove it rather than assume it. This walks the whole onboarding path against the
running engine, raising a request, having it sent back, completed, approved, and the three
accounts ticked off, and it checks the rules that cannot be seen in the XML: that only the
one chosen manager can approve, that nothing is created before approval, and that a
returned request continues as the same case.

```bash
cd etask-configuration && python3 tools/oncheck.py
```

It prints one line per check and a count at the end. If that passes, the platform and the
agenda both work on your machine.

```bash
etask-configuration/tools/up.sh --docker --stop     # stop, keep the data
etask-configuration/tools/up.sh --docker --build    # force a rebuild of the images
etask-configuration/tools/up.sh --docker --fresh    # start over, DELETES the data
```

You do not normally need `--build`: `up.sh` compares your sources against the image it
would run and rebuilds by itself when they are newer.

**If something of yours already holds one of these ports**, a local Mongo on 27017 being
the usual one, move them instead of stopping your own services. `up.sh` checks the ports
before it builds anything and tells you which one is taken.

```bash
MONGO_PORT=27018 ELASTIC_PORT=19200 MAILPIT_PORT=18025 SMTP_PORT=11025 \
  etask-configuration/tools/up.sh --docker
```

**If you keep more than one checkout of this repository**, give each one its own stack.
The project name decides which database the stack attaches to, so two checkouts otherwise
share one, and `--fresh` in either deletes the data of both.

```bash
COMPOSE_PROJECT_NAME=etask-mybranch etask-configuration/tools/up.sh --docker
```

### On your machine

A faster edit-to-see loop for net work, but you supply the toolchain: **Java 11** (Groovy 3
crashes on JDK 17+), **Maven**, **Docker**, **Python 3**, and **Node 18** if you want the
Angular dev server.

```bash
etask-configuration/tools/up.sh              # backend on :8080
etask-configuration/tools/up.sh --frontend   # and ng serve on :4200
```

The script is idempotent: it leaves running things running. It generates the JWT signing
key, picks Java 11, starts Mongo, Elasticsearch and Redis, builds, and reconciles the nets
in the repository against the ones the engine actually holds. Run it again after every net
change. `--stop`, `--restart` and `--fresh` do what they say.

**Why a script and not a paragraph.** Every step here has a trap that does not surface as an
error: a missing JWT key makes public forms return a bare 401, JDK 17 fails with
`Unsupported class file major version`, a missing `LANG=C.UTF-8` throws
`InvalidPathException` on a net with diacritics in its name, a stale `target/` silently
ships a jar without your nets, and a missing Redis brings Spring down at the session store
long after startup. `up.sh` handles all five.

---

## Open it in an editor

A fresh clone is meant to be workable straight away.

### VS Code

```bash
code etask-app
```

`.vscode/extensions.json` recommends the Java, Groovy, XML, Angular and Docker extensions.
`Ctrl+Shift+P` then **Tasks: Run Task** gives you *Run the stack in Docker*, *Stop the
stack*, *Lint the nets* and the rest, so no script paths to remember.

### GitHub Codespaces or a dev container

`.devcontainer/devcontainer.json` pins Java 11, Node 18, Python 3 and Docker-in-Docker, and
forwards ports 4200, 8080 and 8025. In VS Code: **Reopen in Container**. On GitHub: **Code
> Codespaces > Create codespace**. Nothing has to be installed on the host.

### IntelliJ IDEA

Open the repository root and let IDEA import `etask-backend-starter/pom.xml` as a Maven
project. Set the project SDK to **Java 11**.

Shared run configurations are committed in `.run/`, so the run menu already has *eTask
(Docker)*, *eTask (local)*, *Stop eTask*, *Rebuild images*, *Lint the nets*, *Check Groovy
in actions* and *Sync nets into the engine*. The first four are shell scripts; on Windows,
open one of them once and point the interpreter at the `bash.exe` inside your Git
installation if IDEA does not find `bash` on its own.

## Open it in an AI coding assistant

Everything an agent needs is committed, so there is no per machine setup: clone, start the
assistant inside the checkout, and it already knows the rules of this repository.

| file | what it does | who reads it |
|---|---|---|
| `CLAUDE.md` | the rules. In context in every session, so it is short on purpose | Claude Code |
| `AGENTS.md` | the same rules in English, in the cross tool format | most of the rest |
| `.claude/skills/petriflow/SKILL.md` | how to write a Petriflow net, its traps, how to verify it | Claude Code, and readable by anything else |
| `.mcp.json` | an MCP server that lets the agent lint, validate and import nets itself | Claude Code and other MCP clients |
| `.github/copilot-instructions.md` | a pointer to `AGENTS.md` plus the rules that matter most | GitHub Copilot |
| `.gemini/settings.json` | tells Gemini CLI its context file is `AGENTS.md` | Gemini CLI |
| `etask-configuration/tools/pfdoc.py` | the documentation index, so the agent reads one chapter instead of 86 000 tokens | all of them |

### Claude Code

Install it once. It needs a Claude Pro, Max, Team, Enterprise or Console account; the free
plan does not include Claude Code.

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

On Windows PowerShell:

```powershell
irm https://claude.ai/install.ps1 | iex
```

`winget install Anthropic.ClaudeCode`, `brew install --cask claude-code` and
`npm install -g @anthropic-ai/claude-code` also work. Check it with `claude --version`.

Then start it inside the checkout:

```bash
cd etask-app
claude
```

Nothing else to configure. It loads `CLAUDE.md`, finds the `petriflow` skill, and asks you
once to approve the MCP server from `.mcp.json`. Say yes: that server is what lets it lint,
validate and import nets itself instead of guessing whether a net is correct.

On Windows, install [Git for Windows](https://git-scm.com/downloads/win) as well, otherwise
Claude Code runs shell commands through PowerShell and the `tools/*.sh` scripts in this
repository will not run.

#### One click, if you already have Claude Code

Claude Code registers a `claude-cli://` URL handler, so a link can open a session for you.
Paste this into your browser's address bar:

```text
claude-cli://open?repo=lubospetrovic13/etask-app&q=This%20is%20the%20eTask%20Petriflow%20starter.%20If%20you%20do%20not%20have%20it%20yet%2C%20clone%20https%3A%2F%2Fgithub.com%2Flubospetrovic13%2Fetask-app%20and%20cd%20into%20it.%0AThen%20read%20README.md%2C%20start%20the%20stack%20with%20etask-configuration%2Ftools%2Fup.sh%20--docker%2C%20and%20tell%20me%20when%20the%20portal%20is%20up%20on%20http%3A%2F%2Flocalhost%3A4200.
```

It opens a terminal session in your clone of this repository with the prompt already written.
If you have not cloned it yet, the prompt tells Claude Code to do that first. **Nothing is
sent until you read it and press Enter**, and the session shows a `Prompt from an external
link` warning until you do.

The same link is a working button on
[the page that hosts the demo video](https://claude.ai/artifact/Nfms7SUMAAuejGeVf7aLnb#run).
It cannot be a button here: GitHub strips every non-`http` scheme from README links, so
`[label](claude-cli://...)` would render as dead text. That is also why the badge at the top
of this file points at this section rather than at the link itself.

Two conditions, both easy to miss:

- The handler is registered **the first time you send a prompt in an interactive session**,
  not when Claude Code is installed. If clicking does nothing, run `claude` once, send
  anything, and try again.
- `repo=` resolves to a clone Claude Code has **already seen**. Run `claude` inside the
  checkout once so it records the path, otherwise the session opens in your home directory
  and follows the prompt's clone instruction instead.

Needs Claude Code 2.1.91 or newer. The VS Code extension has its own handler,
`vscode://anthropic.claude-code/open?prompt=...`, which opens a Claude Code tab in the
focused window rather than a terminal.

### Cursor, Codex CLI, Gemini CLI, Copilot, Windsurf

`AGENTS.md` carries the same rules in the format the rest of them read. It points at
`CLAUDE.md` as the single source of truth so the two cannot drift apart.

| assistant | what to do | what it reads |
|---|---|---|
| Cursor | open the folder | `AGENTS.md` |
| Codex CLI | `codex` inside the checkout | `AGENTS.md` |
| Gemini CLI | `gemini` inside the checkout | `AGENTS.md`, via `.gemini/settings.json` |
| GitHub Copilot | open the folder in VS Code | `.github/copilot-instructions.md` |
| Windsurf, Zed, Aider, Junie, Amp | open the folder | `AGENTS.md` |

Only Claude Code gets the Petriflow skill and the net tooling over MCP. The rest get the
rules and the documentation, which is most of it. Any of them can still call the tools
directly from the terminal: `pflint`, `pfgroovy`, `pfi18n`, `pfview` and `pfsync` are plain
Python scripts.

### A good first prompt

Give it a real request rather than a technical instruction. The demo used a Word document
handed over unedited, typo included:

> Read `docs/examples/app-request-onboarding.md` and build the agenda it describes as
> Petriflow nets. Follow `CLAUDE.md` and use the `petriflow` skill. Verify with `pflint`
> and `pfcheck` against the running engine before you tell me it works.

That file is the demo input, kept in the repository so the run can be replayed. What came
out of it the first time is described in `docs/ONBOARDING.md`, so you can compare. Start the
stack first: without a running engine the agent can write a net but cannot prove it imports.

**The documentation is largely in Slovak.** `CLAUDE.md`, the runbook and the Petriflow skill
are Slovak; the code, the net IDs and the tooling are not. Assistants read it without
trouble. This README and `AGENTS.md` are the English entry point.

---

## Add your own agenda

```bash
cd etask-configuration
cp examples/skeleton.xml processes/myapp.xml   # change <id>, <initials>, <title>
# add "myapp.xml" to the "import" list in processes.json
python3 tools/pflint.py processes/myapp.xml
cd .. && etask-configuration/tools/up.sh --docker
```

**Adding an application does not require Java.** If you find yourself editing the framework
while adding an agenda, you are probably doing something other than what you think.

Extending the platform is legitimate and common, though. A customer application often needs
a capability the engine does not have: reading attachments, sending mail, calling a foreign
API, a new dependency. That is when a primitive is added to `EtaskActionDelegate`, possibly
with a service and a dependency in `pom.xml`, together with a sentence saying **which
primitive is missing one layer up**.

---

## Verify

```bash
cd etask-configuration
python3 tools/pflint.py processes/       # structure, silent traps
python3 tools/pfgroovy.py processes/     # Groovy syntax in actions
tools/pftest.sh                          # regression tests for the tooling
```

Then the one that matters, an actual import into the engine. Where the server log comes from
depends on how you started it:

```bash
tools/pfcheck.sh --container etask-backend-1 processes/   # started with --docker
tools/pfcheck.sh --log ../.run/backend.log processes/     # started on your machine
```

Without `--container` or `--log`, `pfcheck` still runs but cannot tell you why an import
failed, and it says so.

Ground truth is the running engine. On a bad net the import endpoint returns a bare
`{"status":500}` with no reason and the cause is only in the server log, which is why
`pfcheck` reads that log. `pfcheck` and `pfseed` write into the instance, so **never point
them at production**.

---

## Layout

```
etask-configuration/    nets, documentation, tooling
  processes/            the business logic (.xml)
  processes.json        what gets imported, menu cards, bootstrap cases
  examples/skeleton.xml the smallest net that works
  tools/                up.sh, pflint, pfgroovy, pfcheck, pfseed, pfapi, pftest
etask-backend-starter/  Java and Groovy: the engine, EtaskActionDelegate, runners
etask-frontend-starter/ Angular 13: theme and custom field components
deploy/                 docker compose and the VPS pipeline
docs/                   the long form documentation (Slovak)
```

**Service Desk (`processes/sd_*.xml`) is an example application, not part of the
framework.** The runtime does not know it by name. Delete those nets and their lines in
`processes.json` and it is gone.

---

## Where to go next

| I want to | read |
|---|---|
| run it, add an app, menus, users, anonymous access, theming, components | [`docs/RUNBOOK.md`](docs/RUNBOOK.md) (SK) |
| write Petriflow nets | [`.claude/skills/petriflow/SKILL.md`](.claude/skills/petriflow/SKILL.md) (SK) |
| the methods callable from actions | [`docs/reference/action-api.md`](docs/reference/action-api.md) |
| why the repository is built this way | [`docs/AI_STARTER_ANALYSIS.md`](docs/AI_STARTER_ANALYSIS.md) (SK) |
| the rules an AI agent follows here | [`CLAUDE.md`](CLAUDE.md) (SK), [`AGENTS.md`](AGENTS.md) (EN) |

---

## When it does not start

| symptom | cause |
|---|---|
| `Unsupported class file major version` | JDK 17 or 21. Groovy 3 needs **Java 11** |
| public forms return 401 with no message | the JWT key is missing. Run `etask-configuration/tools/bootstrap.sh` |
| `port is already allocated` | an older stack is up. `up.sh --docker --stop`, or stop a local backend with `up.sh --stop` |
| a net change has no effect | the engine imports a net only when it is missing from the database. `up.sh` reconciles at the end, so do not skip that with `ETASK_NO_SYNC=1` |
| `UnicodeEncodeError: 'charmap' codec` on Windows | the Python tools print Slovak into a cp1252 console. Set `PYTHONIOENCODING=utf-8` |
| `python3: command not found` on Windows | the WindowsApps alias. Use `py -3`, which `up.sh` already falls back to |

The runbook covers each of these at length.

---

## Licensing

`etask-backend-starter` and `etask-frontend-starter` are covered by the **NETGRIF Community
License v1.0** (`etask-backend-starter/LICENSE.txt`). Read it before using this
commercially. The configuration, the nets and the tooling in this repository carry no
licence of their own yet.
