# Deploying SoulMatch (V3-4)

Production target: a small VPS (Hetzner CX22-class or equivalent — 2 vCPU /
4GB RAM is comfortably enough for SQLite at this app's scale, per
`docs/AI-SoulMatch_Unit_Economics.xlsx`), Docker Compose, Caddy for
automatic HTTPS. Postgres is deliberately **not** part of this setup —
deferred until the app has ~1-2k users (see `V3_PLAN.md`).

## 0. Prerequisites `[HUMAN]`

- [ ] Rent the VPS (Hetzner CX22-class or similar). Note its public IPv4 address.
- [ ] `redprana.com` DNS is on GoDaddy — add an **A record**:
      `soulmatch` → `<VPS public IP>` (root `redprana.com` stays untouched).
      DNS propagation can take up to ~30 min; verify with `dig soulmatch.redprana.com`
      before starting Caddy, or its first certificate request will fail.
- [ ] Install Docker + Docker Compose on the VPS (`curl -fsSL https://get.docker.com | sh`,
      then `apt-get install docker-compose-plugin`).
- [ ] Copy `.env.example` → `.env` on the server and fill it in — **at minimum**:
  - `SECRET_KEY` — generate one (`python -c "import secrets; print(secrets.token_hex(32))"`)
    and set it. Without this, every server restart invalidates every login
    session (see the ephemeral-key warning `soulmatch/config.py` already emits).
  - `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` — set a real
    password before first run, or change it immediately after first login.
  - `LLM_PROVIDER` + the matching API key, once you're ready for real AI
    extraction (defaults to `mock` — safe to deploy with, just non-functional AI).
  - `APP_BASE_URL=https://soulmatch.redprana.com`
  - Razorpay/Stripe keys — see `V3_PLAN.md` Sprint V3-3's `[HUMAN]` note;
    checkout buttons show a support message until these are set, which is
    fine for a soft launch.

## 1. First deploy

```bash
git clone <this repo> /opt/soulmatch
cd /opt/soulmatch
cp .env.example .env   # then edit it — see Prerequisites above
docker compose build
docker compose up -d
docker compose logs -f caddy   # watch for "certificate obtained successfully"
```

Once Caddy logs show the certificate was issued, the app is live at
`https://soulmatch.redprana.com`.

## 2. Point the payment gateways at production `[HUMAN]`

Once the domain is live (this step needs a real public URL — gateways
cannot reach `localhost`, use a tunnel like ngrok only for local testing):

- Razorpay dashboard → Webhooks → add `https://soulmatch.redprana.com/webhooks/razorpay`,
  subscribe to `subscription.activated`/`.charged`/`.halted`/`.cancelled`,
  copy the signing secret into `.env` as `RAZORPAY_WEBHOOK_SECRET`.
- Stripe dashboard → Developers → Webhooks → add
  `https://soulmatch.redprana.com/webhooks/stripe`, subscribe to
  `checkout.session.completed`/`invoice.paid`/`invoice.payment_failed`/
  `customer.subscription.deleted`, copy the signing secret into `.env` as
  `STRIPE_WEBHOOK_SECRET`.
- `docker compose restart app webhooks` to pick up the new `.env` values.

## 3. Backups

`deploy/backup.sh` runs `sqlite3 .backup` (safe against a live database) and
gzips the result into `data/backups/`, keeping 14 days locally. Schedule it
on the **host** (outside the containers, since it needs `sqlite3` + cron):

```bash
crontab -e
# add:
0 2 * * * /opt/soulmatch/deploy/backup.sh >> /var/log/soulmatch-backup.log 2>&1
```

`[HUMAN]`: uncomment the `rclone` line in `backup.sh` and configure a remote
(`rclone config`) so backups also leave the server they're protecting
against — see the comment in that file. Rehearse a restore at least once
before relying on this: `docs/RESTORE_DRILL.md` walks through it.

## 4. Ops hygiene checklist

- [ ] `SECRET_KEY` set in `.env` (see Prerequisites — this is the #1 thing
      to forget, and the symptom — everyone logged out on every deploy — is
      easy to misdiagnose as something else).
- [ ] `SENTRY_DSN` set in `.env` if you want error alerting (optional —
      the app runs fine without it; see `soulmatch/config.py`).
- [ ] Uptime monitor `[HUMAN]` (e.g. UptimeRobot, free tier) pinging
      `https://soulmatch.redprana.com/` every few minutes.
- [ ] Backup cron installed (§3) and a restore rehearsed (`docs/RESTORE_DRILL.md`).

## Redeploying after a code change

```bash
cd /opt/soulmatch
git pull
docker compose build
docker compose up -d
```

`init_db()` runs automatically on `app` container startup and applies any
new schema migrations (see `soulmatch/db.py`) — no manual migration step.
