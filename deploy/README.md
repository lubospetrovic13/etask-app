# Nasadenie eTask na vlastný server

Pipeline zbuilduje obrazy na GitHube, pushne ich do GHCR a nasadí ich na server
po SSH. Spúšťa sa **ručne** — nasadenie na produkciu má byť rozhodnutie, nie
následok pushu.

```
GitHub Actions ──build──> GHCR ──pull──> tvoj server
       │                                      ▲
       └──────────── ssh: compose up ─────────┘
```

Na **vývoj a demo** je v tom istom priečinku `docker-compose.dev.yml`, ktorý
obrazy nebuildí z GHCR, ale z tohto checkoutu, a pridáva SMTP server (Mailpit)
a testovacie účty. Nasadenie s ním nemá nič spoločné, spúšťa sa cez

```bash
etask-configuration/tools/up.sh --docker
```

a je opísaný v `docs/RUNBOOK.md`, kapitola 12.

---

## Jednorazová príprava

### 1. Server

Potrebné: Docker Engine s pluginom `compose`, 8 GB RAM, otvorený SSH port pre
runnery GitHubu.

```bash
# dedikovaný účet na nasadzovanie - nepoužívaj root
sudo adduser --disabled-password --gecos "" deploy
sudo usermod -aG docker deploy

sudo mkdir -p /opt/etask
sudo chown deploy:deploy /opt/etask
```

Vygeneruj kľúč **na svojom stroji**, nie na serveri, a verejnú časť nahraj:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/etask_deploy -C "github-actions-etask" -N ""
ssh-copy-id -i ~/.ssh/etask_deploy.pub deploy@TVOJ_SERVER
```

Vypni prihlasovanie heslom, ak ešte nie je vypnuté (`/etc/ssh/sshd_config`:
`PasswordAuthentication no`).

Odovzdaj konfiguráciu:

```bash
scp deploy/.env.example deploy@TVOJ_SERVER:/opt/etask/.env
ssh deploy@TVOJ_SERVER 'chmod 600 /opt/etask/.env && ${EDITOR:-vi} /opt/etask/.env'
```

### 2. GitHub — secrets

`Settings → Secrets and variables → Actions → Secrets`

| Secret | Obsah |
|---|---|
| `SSH_HOST` | IP alebo hostname servera |
| `SSH_USER` | `deploy` |
| `SSH_PRIVATE_KEY` | celý obsah `~/.ssh/etask_deploy` vrátane hlavičiek |
| `SSH_KNOWN_HOSTS` | výstup `ssh-keyscan -H TVOJ_SERVER` |

`SSH_KNOWN_HOSTS` nie je formalita — bez pinnutého host key je nasadenie
zraniteľné na man-in-the-middle.

### 3. GitHub — variables

`Settings → Secrets and variables → Actions → Variables`

| Variable | Default | Kedy nastaviť |
|---|---|---|
| `DEPLOY_PATH` | `/opt/etask` | ak nasadzuješ inam |
| `SSH_PORT` | `22` | ak SSH nebeží na 22 |
| `COMPOSE_PROFILES` | prázdne | `edge`, ak má TLS riešiť Caddy z compose |

### 4. GitHub — environment

Vytvor environment s názvom **`production`**
(`Settings → Environments → New environment`). Workflow ho vyžaduje. Môžeš mu
pridať required reviewers — vtedy bude každý deploy čakať na schválenie
človekom.

---

## TLS a domény

Compose to rieši dvoma spôsobmi, vyber si jeden.

**Už mám vlastný nginx/traefik.** Nechaj `COMPOSE_PROFILES` prázdne. Frontend
kontajner poslúcha na `FRONTEND_PORT` (default `8081`) a ty na to napojíš svoju
proxy. Musí prechádzať aj `/api` — frontend a backend musia byť pre prehliadač
na tom istom origine.

**Chcem to nechať na compose.** Nastav `COMPOSE_PROFILES=edge`, v `.env` vyplň
`DOMAIN` a nechaj otvorené porty 80 a 443. Caddy si certifikát vyrieši sám.

---

## Nasadenie

Z webu GitHubu: `Actions → Deploy → Run workflow`.

Z terminálu:

```bash
gh workflow run deploy.yml --ref claude/handoff-stav-repa-orv6u9
gh run watch
```

Z Claude Code session stačí povedať, že sa má prenasadiť — spustenie workflow,
sledovanie behu aj čítanie logov ide cez GitHub API.

### Rollback

Každý úspešný deploy si na serveri odloží tag do `.deployed_tag` a predchádzajúci
do `.previous_tag`. Spusti workflow znova a do `deploy_tag` zadaj ten
predchádzajúci — build sa preskočí a nasadí sa existujúci obraz.

```bash
ssh deploy@TVOJ_SERVER 'cat /opt/etask/.previous_tag'
gh workflow run deploy.yml -f deploy_tag=abc123def456
```

---

## Čo pipeline kontroluje

1. **Start-Class v obraze.** Build padne, ak sa do obrazu dostane jar, ktorý
   nemá `Start-Class: com.netgrif.etask.EtaskApplication`. Dôvod nižšie.
2. **Frontend odpovedá** na svojom porte.
3. **`/api` prechádza** na backend cez nginx proxy.
4. **Prihlásenie vydá token.** Toto je ten dôležitý. Appka môže bežať, porty
   odpovedať — a login pritom padať na 500. Nastav `SMOKE_USER` a
   `SMOKE_PASSWORD` v `.env`, inak sa krok preskočí a nahlási to.

---

## Tri veci, ktoré tento repozitár potrebuje opraviť, aby sa dal nasadiť

Všetky tri sú overené na reálnom builde a nasadení, nie odhady.

### Chýbajúce závislosti — `deploy/vendor-deps.sh`

Dve tranzitívne závislosti Netgrif AE 6.3.1 sa **nedajú stiahnuť** na žiadnom
čistom stroji:

- `com.novemberain:quartz-mongodb:2.2.0-rc2` neexistuje na Maven Central,
  Clojars, scijava ani mulesoft. Pôvodne žila na `maven.imagej.net`, ktorý bol
  vyradený a dnes presmerováva na scijava, kde artefakt nie je. Na Central je
  zrkadlo pod `io.fluidsonic.mirror` — ten istý projekt, tí istí autori, tá istá
  verzia.
- `com.github.kenglxn.qrgen:javase:2.6.0` je na JitPacku, ale pom enginu JitPack
  ako repozitár nedeklaruje.

Skript oboje dorieši a je idempotentný. Volá ho backend Dockerfile pred
`mvn package`. **Bez neho `docker build` padne** — nielen v CI, na akomkoľvek
stroji, ktorý nemá tie artefakty už v `~/.m2`.

### Nespustiteľný jar v Dockerfile

Originálny Dockerfile kopíroval `target/app-exec.jar`. Ten má v manifeste
`Start-Class: org.springframework.boot.loader.JarLauncher` — ukazuje sám na seba
a pri štarte skončí na `StackOverflowError`. Spôsobuje to
`<classifier>exec</classifier>` na exekúcii `build-info` v `pom.xml`.
Spustiteľný je `target/app.jar`. Pipeline to navyše po builde overí.

### Frontend nemal kam volať

`nae.json` má natvrdo `http://localhost:8080/api`, čo v prehliadači zákazníka
neexistuje. Riešenie je `AUTO_RESOLVE_URL=true` (frontend si adresu odvodí zo
svojho originu) plus lokácia `/api` v nginxe, ktorá proxuje na backend —
`deploy/nginx.conf`. Frontend a backend sú tým same-origin a CORS sa nerieši.

> Pasca: hodnota z `env.js` prichádza ako **string**, takže
> `AUTO_RESOLVE_URL=false` sa chová ako `true` — `"false"` je v JavaScripte
> truthy. Ak chceš auto-resolve naozaj vypnúť, nastav prázdnu hodnotu.

---

## Prevádzkové pasce

**Locale musí byť UTF-8.** Backend ukladá nahraný Petriflow model pod názvom
procesu ako názov súboru. Pri ASCII locale zhodí `InvalidPathException` každý
upload procesu s diakritikou v názve — „Servisná požiadavka“ neprejde. V obraze
je `LANG=C.UTF-8` nastavené, nechaj to tak.

**Import procesu nie je atomický.** Keď upload zlyhá v polovici, stihne vytvoriť
procesné role a priradiť ich používateľovi. Zostane osirelý odkaz na
neexistujúcu sieť a **prihlásenie začne vracať 500**. Po každom uploade procesu
si over, že sa dá prihlásiť. Presne to robí smoke test v pipeline.

**Case si drží verziu siete.** Po uploade novej verzie procesu existujúce casy
bežia na starej. Zmeny, ktoré majú platiť pre bežiace tickety, nesmú byť
v sieti — musia byť v konfiguračných casoch, na ktoré sieť odkazuje.

---

## Ručné nasadenie bez pipeline

```bash
ssh deploy@TVOJ_SERVER
cd /opt/etask
echo TVOJ_GHCR_TOKEN | docker login ghcr.io -u TVOJE_MENO --password-stdin
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f backend
```
