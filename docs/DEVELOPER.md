# Netgrif AI starter for developers

Everything the [README](../README.md) leaves out: other ways to run the stack, editors and AI
assistants in detail, adding and verifying an agenda, and what to do when it does not start.

## How it works

The database, the REST layer, the frontend, login, IAM, roles and permissions are already
here and already work. What you add is the **business logic**: Petriflow nets. The
framework is around 5 500 lines, the nets around 9 700, and that ratio is the point.

The nets that came out of the demo are `ai-config/processes/on_request.xml` and
`on_menu.xml`.

---

## Run it with the scripts

`docker compose up` from the [README](../README.md) is the shortest path. `up.sh` does the same and more: it checks
the ports before it builds anything, rebuilds the images when your sources are newer, and
can stop, rebuild or wipe the stack. Two ways. Pick the first unless you already have Java
11 on the machine.

### Everything in Docker (recommended)

You need **Docker Desktop** and **Git**. On Windows run the command from **Git Bash**, not
from PowerShell or cmd. No Java, no Maven and no Node on your machine: all three live in the
images. **Python 3** is the one extra: starting the app does not need it, but every checking
tool in `ai-config/tools/` is Python, including the one below that proves the
agenda actually runs.

```bash
git clone https://github.com/lubospetrovic13/netgrif-ai-starter.git
cd netgrif-ai-starter
ai-config/tools/up.sh --docker
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

Then prove it rather than assume it. The onboarding app from the demo comes with an
acceptance test that walks the whole path against the running engine: raising a request,
having it sent back, completed, approved, and the three accounts ticked off. It is active out of
the box, so run it from `ai-config/`: `python3 tools/oncheck.py`.

It prints one line per check and a count at the end. If that passes, the platform and the
agenda both work on your machine.

```bash
ai-config/tools/up.sh --docker --stop     # stop, keep the data
ai-config/tools/up.sh --docker --build    # force a rebuild of the images
ai-config/tools/up.sh --docker --fresh    # start over, DELETES the data
```

You do not normally need `--build`: `up.sh` compares your sources against the image it
would run and rebuilds by itself when they are newer.

**If something of yours already holds one of these ports**, a local Mongo on 27017 being
the usual one, move them instead of stopping your own services. `up.sh` checks the ports
before it builds anything and tells you which one is taken.

```bash
MONGO_PORT=27018 ELASTIC_PORT=19200 MAILPIT_PORT=18025 SMTP_PORT=11025 \
  ai-config/tools/up.sh --docker
```

**If you keep more than one checkout of this repository**, give each one its own stack. The
project name decides which database the stack attaches to and the image tag decides which
build it runs, so without both, two checkouts share one database and overwrite each other's
images, and `--fresh` in either deletes the data of both.

```bash
COMPOSE_PROJECT_NAME=netgrif-mybranch IMAGE_TAG=mybranch   ai-config/tools/up.sh --docker
```

### On your machine

A faster edit-to-see loop for net work, but you supply the toolchain: **Java 11** (Groovy 3
crashes on JDK 17+), **Maven**, **Docker**, **Python 3**, and **Node 18** if you want the
Angular dev server.

```bash
ai-config/tools/up.sh              # backend on :8080
ai-config/tools/up.sh --frontend   # and ng serve on :4200
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
code netgrif-ai-starter
```

`.vscode/extensions.json` recommends the Java, Groovy, XML, Angular and Docker extensions.
`Ctrl+Shift+P` then **Tasks: Run Task** gives you *Run the stack in Docker*, *Stop the
stack*, *Lint the nets* and the rest, so no script paths to remember.

### GitHub Codespaces or a dev container

`.devcontainer/devcontainer.json` pins Java 11, Node 18, Python 3 and Docker-in-Docker, and
forwards ports 4200, 8080 and 8025. In VS Code: **Reopen in Container**. On GitHub: **Code
> Codespaces > Create codespace**. Nothing has to be installed on the host.

### IntelliJ IDEA

Open the repository root and let IDEA import `platform/backend/pom.xml` as a Maven
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
| `ai-config/tools/pfdoc.py` | the documentation index, so the agent reads one chapter instead of 86 000 tokens | all of them |

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
cd netgrif-ai-starter
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
claude-cli://open?repo=lubospetrovic13/netgrif-ai-starter&q=This%20is%20the%20Netgrif%20AI%20starter.%20If%20you%20do%20not%20have%20it%20yet%2C%20clone%20https%3A%2F%2Fgithub.com%2Flubospetrovic13%2Fnetgrif-ai-starter%20and%20cd%20into%20it.%0AThen%20read%20README.md%2C%20start%20the%20stack%20with%20ai-config%2Ftools%2Fup.sh%20--docker%2C%20and%20tell%20me%20when%20the%20portal%20is%20up%20on%20http%3A%2F%2Flocalhost%3A4200.
```

It opens a terminal session in your clone of this repository with the prompt already written.
If you have not cloned it yet, the prompt tells Claude Code to do that first. **Nothing is
sent until you read it and press Enter**, and the session shows a `Prompt from an external
link` warning until you do.

The same link is a working button on
[the page that hosts the demo video](https://claude.ai/artifact/Nfms7SUMAAuejGeVf7aLnb#run).
It cannot be a button here: GitHub strips every non-`http` scheme from README links, so
`[label](claude-cli://...)` would render as dead text. That is also why the badge at the top
of the README points at this section rather than at the link itself.

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

> Read `examples/onboarding/request.md` and build the agenda it describes as
> Petriflow nets. Follow `CLAUDE.md` and use the `petriflow` skill. Verify with `pflint`
> and `pfcheck` against the running engine before you tell me it works.

That file is the demo input, kept in the repository so the run can be replayed. What came
out of it the first time is in `examples/onboarding/`, so you can compare. Start the
stack first: without a running engine the agent can write a net but cannot prove it imports.

**The documentation is largely in Slovak.** `CLAUDE.md`, the runbook and the Petriflow skill
are Slovak; the code, the net IDs and the tooling are not. Assistants read it without
trouble. This README and `AGENTS.md` are the English entry point.

---

## Add your own agenda

```bash
cd ai-config
python3 tools/pfnew.py myapp request "My request" --role worker
python3 tools/pflint.py processes/
python3 tools/pfsync.py --sync        # import into the running engine, assign roles
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
cd ai-config
python3 tools/pflint.py processes/       # structure, silent traps
python3 tools/pfgroovy.py processes/     # Groovy syntax in actions
tools/pftest.sh                          # regression tests for the tooling
```

Then the one that matters, an actual import into the engine. Where the server log comes from
depends on how you started it:

```bash
tools/pfcheck.sh --container netgrif-backend-1 processes/   # started with --docker
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
ai-config/              the AI-native configuration
  processes/            the business logic (.xml), one app = a few nets
  processes.json        what gets imported, menu cards, bootstrap cases
  seed.json             which user gets which process role
  examples/skeleton.xml the smallest net that works, used by pfnew
  tools/                pfnew, pflint, pfgroovy, pfi18n, pfview, pfsync, pfcheck, pfmcp, up.sh
platform/
  backend/              Java and Groovy: the engine, EtaskActionDelegate, runners
  frontend/             Angular 13: portal, theme and custom field components
  docker-compose.yml    the stack, included by compose.yaml in the root
examples/               finished apps; onboarding (from the demo) is active, the rest install with pfapp
docs/                   the long form documentation (Slovak), read through pfdoc
```

`ai-config/processes/` holds user management, what every instance needs, and the one active
example, onboarding. The other examples live in `examples/` and are installed with
`pfapp install`, see [examples/README.md](../examples/README.md).

---

## Where to go next

| I want to | read |
|---|---|
| run it, add an app, menus, users, anonymous access, theming, components | [`docs/RUNBOOK.md`](RUNBOOK.md) (SK) |
| write Petriflow nets | [`.claude/skills/petriflow/SKILL.md`](../.claude/skills/petriflow/SKILL.md) (SK) |
| the methods callable from actions | [`docs/reference/action-api.md`](reference/action-api.md) |
| why the repository is built this way | [`docs/AI_STARTER_ANALYSIS.md`](AI_STARTER_ANALYSIS.md) (SK) |
| the rules an AI agent follows here | [`CLAUDE.md`](../CLAUDE.md) (SK), [`AGENTS.md`](../AGENTS.md) (EN) |

---

## When it does not start

| symptom | cause |
|---|---|
| `Unsupported class file major version` | JDK 17 or 21. Groovy 3 needs **Java 11** |
| public forms return 401 with no message | the JWT key is missing. Run `ai-config/tools/bootstrap.sh` |
| `port is already allocated` | an older stack is up. `up.sh --docker --stop`, or stop a local backend with `up.sh --stop` |
| a net change has no effect | the engine imports a net only when it is missing from the database. `up.sh` reconciles at the end, so do not skip that with `ETASK_NO_SYNC=1` |
| `UnicodeEncodeError: 'charmap' codec` on Windows | the Python tools print Slovak into a cp1252 console. Set `PYTHONIOENCODING=utf-8` |
| `python3: command not found` on Windows | the WindowsApps alias. Use `py -3`, which `up.sh` already falls back to |

The runbook covers each of these at length.
