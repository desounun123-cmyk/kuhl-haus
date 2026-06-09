# Deploying kuhl-haus on Railway

This folder contains everything needed to provision the kuhl-haus stack
on [Railway](https://railway.com) programmatically — no clicking through
the dashboard required.

## Layout

| File | Purpose |
| --- | --- |
| `services.json` | Declarative spec of every service (image, env, volumes, public port). Single source of truth. |
| `provision.py` | Idempotent provisioner. Reads `services.json` + your shell env, creates/updates services via the Railway GraphQL API, attaches volumes, exposes the public domain, and triggers a redeploy. |
| `.env.example` | All environment variables the provisioner expects. Copy and fill in real values, then `set -a; source .env; set +a`. |

## Prerequisites

- A Railway account and an [API token](https://railway.app/account/tokens).
- Python 3.10+ on the machine that will run `provision.py` (standard
  library only — no `pip install` step).
- **Plan limits**: Railway's free plan caps a project at 5 services.
  The full stack is 9 services, so you need at least the Hobby plan to
  provision everything. The provisioner detects the limit, logs which
  services were skipped, and re-runs cleanly after you upgrade.

## First-time deployment

```bash
cp deploy/railway/.env.example deploy/railway/.env
# edit deploy/railway/.env — at minimum: RAILWAY_TOKEN, MASSIVE_API_KEY,
# FINLIGHT_API_KEY, WDS_API_KEY
set -a; source deploy/railway/.env; set +a
python3 deploy/railway/provision.py
```

On the very first run (no `RAILWAY_PROJECT_ID`), the script creates a
new project named `RAILWAY_PROJECT_NAME` and prints the id, e.g.:

```
Creating new Railway project 'kuhl-haus'...
  created project_id=66c2435d-a734-44da-8076-766ebe3b4a38 environment_id=...
  Export RAILWAY_PROJECT_ID=<this id> for future idempotent runs.
```

Add that id to your local `.env` (or your CI secret store) so subsequent
runs update the existing project in place instead of creating a new one.

## Subsequent updates

`provision.py` is fully idempotent:

- Services that already exist are reused; only their env / volumes are
  refreshed.
- Variables are upserted with `replace=true`, so removing a key from
  `services.json` also removes it from Railway on the next run.
- Volumes are created if missing, never destroyed.
- The public domain is reused if one already exists for the exposed
  service.
- A redeploy is triggered for every service at the end so Railway picks
  up the latest configuration / image.

Tweak `services.json` (add env vars, change an image tag, expose a
different port, etc.) and re-run the script. That's the whole loop.

## What gets provisioned

```
┌──────────────────────────────────────────────────────────────────────┐
│  Public:  https://scp-production-<hash>.up.railway.app  -> scp:8000  │
└──────────────────────────────────────────────────────────────────────┘
        ▲                                       ▲
        │                                       │
   ┌────┴────┐  ws://wds.railway.internal   ┌───┴───┐
   │   scp   │ ────────────────────────────▶│  wds  │
   │ py4web  │                              └───────┘
   └─────────┘                                  │
                                       redis://mdc.railway.internal
   ┌─────────┐  amqp://mdq.railway.internal     │
   │   mdl   │ ─┐                       ┌───────┴──────┐
   │   fdl   │ ─┤                       │  mdc (Redis) │
   │   mdp   │ ─┼──▶ ┌────────────┐     └──────────────┘
   │   fdp   │ ─┘    │ mdq (RMQ)  │
   │   mds   │ ─────▶└────────────┘
   └─────────┘
```

All inter-service traffic goes over Railway's private network using
`<service>.railway.internal` hostnames. Only `scp` is exposed publicly.

## Secrets handling

`services.json` never contains real secrets. Variables that should be
sourced from the shell use one of two placeholders:

- `"FROM_ENV:NAME"`  — required; the provisioner aborts if the variable
  is unset.
- `"FROM_ENV:NAME?"` — optional; the variable is simply omitted from
  the upsert when unset. This is how `DATABENTO_API_KEY` stays
  off the critical path until you actually want the fallback enabled.

`${NAME}`-style interpolation inside a literal value (e.g. the Rabbit
connection URL) is expanded against the same shell environment, so
secrets used in multiple services stay consistent.

## Enabling the Databento fallback

The MDL listener supports a Databento fallback (see
`packages/mdp/src/kuhl_haus/mdp/components/fallback_data_listener.py`).
Massive remains the primary provider; Databento only activates when
Massive cannot connect.

To turn it on:

```bash
export DATABENTO_API_KEY=db-...
python3 deploy/railway/provision.py
```

The provisioner will push `DATABENTO_API_KEY`, `DATABENTO_DATASET`, and
`DATABENTO_RECOVERY_INTERVAL_SECONDS` to the `mdl` service and trigger
a redeploy.

## Tearing the project down

The provisioner intentionally never deletes anything. Use the Railway
dashboard (or `railway` CLI) to delete the project when you're done —
that also removes every service, variable, volume, and domain in a
single click.
