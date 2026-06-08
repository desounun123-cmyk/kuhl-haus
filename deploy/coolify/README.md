# Deploying kuhl-haus on Coolify

This directory contains a Coolify-optimised Docker Compose stack
(`compose.yaml`) and an `.env.example` listing every variable you must
supply in Coolify's **Environment Variables** tab.

## Prerequisites

- A running Coolify instance (v4+) with at least one server connected.
- A domain (or subdomain) pointed at the Coolify server, e.g.
  `app.example.com`. Coolify will issue a Let's Encrypt cert automatically.
- Outbound network access from the Coolify server to `ghcr.io` (the
  prebuilt service images live there) and to the Massive / Finlight APIs.

## Steps

1. **Create a new resource**
   - Coolify dashboard → *+ New* → *Docker Compose*.
   - Source: *Public Repository* (or your private GitHub app installation).
   - Repository: `https://github.com/desounun123-cmyk/kuhl-haus`
   - Branch: `main`
   - Build pack: *Docker Compose*
   - Base directory: `/deploy/coolify`
   - Docker Compose file location: `compose.yaml`

2. **Set environment variables**
   - Open the *Environment Variables* tab.
   - Paste the contents of `deploy/coolify/.env.example`.
   - Fill in real values for `MASSIVE_API_KEY`, `FINLIGHT_API_KEY`,
     `WDS_API_KEY`, and (recommended) strong values for `REDIS_PASSWORD`,
     `RABBITMQ_USER`, `RABBITMQ_PASSWORD`.
   - Set `SERVICE_FQDN_SCP_8000` to your public URL, e.g.
     `https://app.example.com`. Coolify reads the `SERVICE_FQDN_SCP_8000`
     magic variable and wires Traefik to route that hostname to the
     `scp` service on port 8000.

3. **Deploy**
   - Click *Deploy*. Coolify will pull the prebuilt images from
     `ghcr.io/kuhl-haus/*` and start the stack.
   - First boot can take a couple of minutes while RabbitMQ initialises.

4. **Verify**
   - Visit your `SERVICE_FQDN_SCP_8000` URL → the py4web dashboard should
     load.
   - In Coolify *Logs*, confirm each service reaches a healthy state.

## Optional: expose RabbitMQ / Redis Insight UIs

By default only the `scp` app is reachable from the public internet.
If you want to expose the RabbitMQ management UI or Redis Insight, add
another magic variable in Coolify and (re)deploy:

```env
SERVICE_FQDN_MDQ_15672=https://rabbit.example.com
SERVICE_FQDN_MDC_8001=https://redis.example.com
```

Coolify will create routes automatically — no compose changes needed.

## Updating

- Coolify can watch the repo and redeploy on every push to `main`
  (*Webhooks* tab). Alternatively click *Redeploy* manually.
- To pick up new versions of the prebuilt images, enable
  *Force rebuild* / *Pull latest images* before redeploying.

## Local development

For local Docker Compose development continue to use
`deploy/Docker/compose.yaml` — it keeps the host port bindings and
preset credentials that are convenient on a dev machine.
