# Lightsail first-time setup, step by step

A narrated walkthrough for standing up a **new** Lightsail instance for this
app and pointing a `redprana.com` subdomain at it. `docs/DEPLOY.md` is the
terse reference version of the same process — this one explains *why* each
step exists, with the actual values used for `soulmatch.redprana.com` as a
worked example. Use it as the template for the next subdomain/instance too.

## Worked example (soulmatch.redprana.com)

| Thing | Value used |
|---|---|
| Lightsail instance name | `soulmatch-prod` |
| Region | Mumbai, Zone A (`ap-south-1`) |
| Blueprint | Ubuntu 22.04 LTS (OS only, not an app blueprint) |
| Plan | 2 GB RAM / 2 vCPU / 60 GB SSD |
| Static IP name | `soulmatch-ip` |
| Static IP address | `13.126.191.8` |
| GoDaddy A record | Host `soulmatch` → `13.126.191.8` |
| Live URL | `https://soulmatch.redprana.com` |
| Repo path on server | `/opt/soulmatch` |

## 1. Create the instance

Lightsail instances are independent — having other sites already hosted
there doesn't block a new one, it's just another line item on the bill.

Lightsail console → **Create instance**:
- **Region/zone**: pick the same region as your other instances unless you
  want geographic separation (we used Mumbai/`ap-south-1`).
- **Platform**: Linux/Unix
- **Blueprint**: **OS Only → Ubuntu 22.04 LTS** — not one of the app
  blueprints (Node.js, WordPress, etc.), since this repo brings its own
  Docker setup.
- **Plan**: at least 2 GB RAM / 2 vCPU / 60 GB SSD. That's enough for
  Docker + Caddy + SQLite at this app's current scale (see
  `docs/AI-SoulMatch_Unit_Economics.xlsx`).
- **Name**: something identifying, e.g. `soulmatch-prod`. Don't reuse the
  name of another instance you're already running.

Click **Create instance** and wait for it to show **Running**.

## 2. Attach a static IP

By default a Lightsail instance's public IP **changes every time you stop
and start it**. DNS records point at a fixed IP, so an instance without a
static IP will eventually break its own domain.

Instance page → **Networking** tab → **Attach static IP** → give it a name
(we used `soulmatch-ip`) → attach to this instance.

The Networking tab will then show *"Your instance is using a static IP as
its public IPv4 address"* and the address itself (ours: `13.126.191.8`).
**This is the IP that goes into DNS** — always read it from the Static IPs
section, not just the plain IPv4 box, since attaching a static IP can
change the address from what the instance had before.

## 3. Open the firewall for web traffic

Same Networking tab, **IPv4 Firewall** section. By default only SSH (22)
is open. Add two more rules via **+ Add rule**:
- **HTTP**, TCP, port 80 — needed for Let's Encrypt's certificate
  challenge and to redirect to HTTPS.
- **HTTPS**, TCP, port 443 — the actual encrypted traffic.

You do **not** need to open the app's internal ports (8501 Streamlit,
8502 webhooks) — Caddy proxies to them over Docker's internal network,
they never need to be internet-facing.

## 4. Point the domain at the instance (GoDaddy)

GoDaddy → **My Products → DNS** for `redprana.com` → **Add record**:
- Type: **A**
- Name/Host: the subdomain, e.g. `soulmatch`
- Value: the static IP from step 2 (`13.126.191.8`)
- TTL: default

Leave the root `redprana.com` record untouched — this only adds the
subdomain. DNS propagation can take up to ~30 minutes; if the certificate
step later fails, this is the first thing to double check (`nslookup
soulmatch.redprana.com` from your own machine should return the static IP).

## 5. Connect to the instance

Lightsail console → instance → **Connect** tab → **"Connect using SSH"**.
This opens a browser-based terminal, already authenticated with the
instance's default key — no key file setup needed for this path.

## 6. Install Docker

In that terminal:
```bash
curl -fsSL https://get.docker.com | sh
sudo apt-get install -y docker-compose-plugin
sudo usermod -aG docker $USER
```
The last line adds your user to the `docker` group so you don't need
`sudo` before every docker command. **Log out and reconnect** (click
Connect again) for that group membership to take effect — it doesn't
apply retroactively to the current session.

## 7. Clone the repo

`/opt` is a root-owned system directory, so a plain `git clone` into it
fails with "Permission denied." Create and hand over the folder first:
```bash
sudo mkdir -p /opt/soulmatch
sudo chown $USER:$USER /opt/soulmatch
git clone https://github.com/avssprak/AI-SoulMatch /opt/soulmatch
cd /opt/soulmatch
```
The repo was made **public** for this first deploy so the plain `https://`
clone works without credentials. If it's switched back to private later,
`git pull` on the server will start failing the same way — set up a
GitHub Personal Access Token (`git config credential.helper store`, enter
the token once) or an SSH deploy key on the repo before flipping it
private again.

## 8. Configure environment variables

```bash
cp .env.example .env
```
This copies the template (placeholder values) into a real config file the
app actually reads. Then generate a secret before opening the editor:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
This just prints a random 64-character string — copy it. Then:
```bash
nano .env
```
Set at minimum:
- `SECRET_KEY=<the string you just generated>` — without this, every
  container restart invalidates every login session.
- `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` — a real admin
  login, not the template's `admin` / `changeme123`.
- `APP_BASE_URL=https://soulmatch.redprana.com` (the live subdomain).
- `LLM_PROVIDER` + matching API key when ready for real AI extraction
  (defaults to `mock` — safe to deploy with, just non-functional AI until set).

Save: `Ctrl+O`, `Enter` to confirm the filename, then `Ctrl+X` to exit.

## 9. Build and start

```bash
docker compose build
```
Builds the image from the `Dockerfile` — installs Python and all
dependencies. Takes a few minutes the first time.

```bash
docker compose up -d
```
Starts three containers in the background: the Streamlit app, the webhook
sidecar, and Caddy (reverse proxy + automatic HTTPS).

```bash
docker compose logs -f caddy
```
Watch until you see `certificate obtained successfully` — that's Caddy
confirming it got a real HTTPS certificate from Let's Encrypt for the
domain (this only works once DNS from step 4 has propagated). Press
`Ctrl+C` to stop watching (containers keep running).

Once that line appears, the site is live at the domain from step 4.

## 10. Install the nightly backup cron

`deploy/backup.sh` runs on the **host**, not inside a container, so it
needs two things installed on the server first: the script's own execute
bit, and the `sqlite3` CLI.

```bash
cd /opt/soulmatch
chmod +x deploy/backup.sh
sudo apt-get update
sudo apt-get install -y sqlite3
```

The `data/` folder is a Docker bind mount, and since the app inside the
container runs as root, the folder is root-owned on the host too — the
script will fail with "Permission denied" creating `data/backups/` until
you hand ownership back to your own user:
```bash
sudo chown -R $USER:$USER /opt/soulmatch/data
```

Test it manually before trusting it to cron:
```bash
./deploy/backup.sh
ls -lh data/backups/
```
Should print `Backed up to .../soulmatch_<timestamp>.db.gz` and show the
file. Confirm the app itself is still working afterward (load the site,
log in) — the chown only touches host-side ownership, but it's worth a
sanity check since containers keep running as root regardless.

Then schedule it:
```bash
crontab -e
```
Add this line (pick `nano` if prompted for an editor):
```
0 2 * * * /opt/soulmatch/deploy/backup.sh >> /var/log/soulmatch-backup.log 2>&1
```
Save (`Ctrl+O`, `Enter`, `Ctrl+X`), then confirm with `crontab -l`.

This runs at 2 AM in the server's **own** timezone, not necessarily IST —
check with `timedatectl` if the exact local time matters, and adjust the
cron hour accordingly (IST is UTC+5:30).

Backups auto-rotate after 14 days locally. For an offsite copy too
(recommended — local-only backups don't survive a disk/server failure),
uncomment the `rclone` line in `deploy/backup.sh` and set up an `rclone
config` remote (Backblaze B2, S3, etc.) — not yet done for this instance.

## 11. After launch — remaining items

See `docs/DEPLOY.md` §2, §4 for the parts not repeated here:
- Pointing Razorpay/Stripe webhooks at the live domain
- Ops checklist: `SENTRY_DSN`, uptime monitor, rehearsing a restore
  (`docs/RESTORE_DRILL.md`)

## Redeploying after a code change

```bash
cd /opt/soulmatch
git pull
docker compose build
docker compose up -d
```
Schema migrations run automatically on `app` container startup — no
manual migration step needed.
