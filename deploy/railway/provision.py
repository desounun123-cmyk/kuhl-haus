#!/usr/bin/env python3
"""Idempotent Railway provisioner for the kuhl-haus monorepo.

Reads ``deploy/railway/services.json`` and reconciles a Railway project
with the declared services, environment variables, volumes, and public
domains. Safe to re-run: services that already exist are updated in
place, never recreated. Missing services are created, and on each
successful reconcile a redeploy is triggered so the new configuration
takes effect.

Usage
-----

    RAILWAY_TOKEN=<account-or-team-token> \\
    RAILWAY_PROJECT_ID=<existing-project-uuid> \\
        python3 deploy/railway/provision.py

If ``RAILWAY_PROJECT_ID`` is unset a new project named
``RAILWAY_PROJECT_NAME`` (default ``kuhl-haus``) is created and its id
is printed on stdout — store it in your shell so subsequent runs are
in-place updates rather than fresh projects.

Secrets are sourced from the local shell. Any service variable whose
value matches the pattern ``FROM_ENV:<NAME>`` (or ``FROM_ENV:<NAME>?``
for optional) is substituted with ``os.environ[<NAME>]`` at deploy
time; the literal placeholder is never sent to Railway. References to
``${OTHER}`` inside a value are expanded against the same shell
environment so cross-service credentials (e.g. RabbitMQ user/pass in a
connection URL) stay consistent.

This script intentionally has no third-party dependencies — only the
Python standard library — so it can run inside CI without an install
step.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

API = "https://backboard.railway.app/graphql/v2"
SPEC_PATH = Path(__file__).with_name("services.json")
PROJECT_NAME_DEFAULT = "kuhl-haus"

TOKEN = os.environ.get("RAILWAY_TOKEN")
PROJECT_ID = os.environ.get("RAILWAY_PROJECT_ID")
PROJECT_NAME = os.environ.get("RAILWAY_PROJECT_NAME", PROJECT_NAME_DEFAULT)
ENVIRONMENT_NAME = os.environ.get("RAILWAY_ENVIRONMENT", "production")


# ---------------------------------------------------------------------------
# GraphQL helper
# ---------------------------------------------------------------------------

def gql(query: str, variables: Optional[dict] = None) -> dict:
    if not TOKEN:
        sys.exit("RAILWAY_TOKEN is required in the environment.")
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "kuhl-haus-railway-provisioner/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        sys.exit(f"Railway API HTTP {exc.code}: {exc.read().decode(errors='replace')}")
    if payload.get("errors"):
        message = json.dumps(payload["errors"], indent=2)
        sys.exit(f"Railway GraphQL error:\n{message}")
    return payload["data"]


# ---------------------------------------------------------------------------
# Variable substitution (FROM_ENV: + ${VAR})
# ---------------------------------------------------------------------------

_FROM_ENV_RE = re.compile(r"^FROM_ENV:([A-Z0-9_]+)(\??)$")
_INTERP_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def resolve_value(raw: str) -> Optional[str]:
    """Return the concrete value to push to Railway, or ``None`` to skip.

    Rules:
      * ``FROM_ENV:NAME``  — required; aborts if NAME is unset.
      * ``FROM_ENV:NAME?`` — optional; returns None (variable skipped)
        if NAME is unset.
      * Otherwise the literal value with ``${OTHER}`` expansions.
    """
    m = _FROM_ENV_RE.match(raw)
    if m:
        name, optional = m.group(1), m.group(2) == "?"
        value = os.environ.get(name)
        if value is None:
            if optional:
                return None
            sys.exit(f"Environment variable {name!r} is required but not set.")
        return value
    return _INTERP_RE.sub(lambda mm: os.environ.get(mm.group(1), ""), raw)


# ---------------------------------------------------------------------------
# Project / environment bootstrap
# ---------------------------------------------------------------------------

def ensure_project() -> tuple[str, str]:
    """Return (project_id, environment_id), creating the project if needed."""
    if PROJECT_ID:
        data = gql(
            "query($id: String!) { project(id: $id) { id environments { edges { node { id name } } } } }",
            {"id": PROJECT_ID},
        )
        project = data["project"]
        env_id = next(
            edge["node"]["id"]
            for edge in project["environments"]["edges"]
            if edge["node"]["name"] == ENVIRONMENT_NAME
        )
        return project["id"], env_id

    print(f"Creating new Railway project {PROJECT_NAME!r}...")
    data = gql(
        "mutation($name: String!) { projectCreate(input: { name: $name }) { id environments { edges { node { id name } } } } }",
        {"name": PROJECT_NAME},
    )
    proj = data["projectCreate"]
    env_id = next(
        e["node"]["id"]
        for e in proj["environments"]["edges"]
        if e["node"]["name"] == ENVIRONMENT_NAME
    )
    print(
        f"  created project_id={proj['id']} environment_id={env_id}\n"
        "  Export RAILWAY_PROJECT_ID=<this id> for future idempotent runs."
    )
    return proj["id"], env_id


def list_existing_services(project_id: str) -> dict[str, str]:
    data = gql(
        "query($id: String!) { project(id: $id) { services { edges { node { id name } } } } }",
        {"id": project_id},
    )
    return {
        edge["node"]["name"]: edge["node"]["id"]
        for edge in data["project"]["services"]["edges"]
    }


# ---------------------------------------------------------------------------
# Per-service operations
# ---------------------------------------------------------------------------

def create_service(project_id: str, name: str, image: str) -> str:
    data = gql(
        """
        mutation($projectId: String!, $name: String!, $image: String!) {
          serviceCreate(input: { projectId: $projectId, name: $name, source: { image: $image } }) {
            id name
          }
        }
        """,
        {"projectId": project_id, "name": name, "image": image},
    )
    return data["serviceCreate"]["id"]


def upsert_variables(project_id: str, env_id: str, service_id: str, env: dict) -> None:
    materialised: dict[str, str] = {}
    for k, v in env.items():
        resolved = resolve_value(v)
        if resolved is not None:
            materialised[k] = resolved
    gql(
        "mutation($input: VariableCollectionUpsertInput!) { variableCollectionUpsert(input: $input) }",
        {
            "input": {
                "projectId": project_id,
                "environmentId": env_id,
                "serviceId": service_id,
                "variables": materialised,
                "replace": True,
            }
        },
    )


def ensure_volume(project_id: str, env_id: str, service_id: str, mount: str) -> None:
    """Create the volume only if the service has none attached yet.

    Railway enforces a hard limit of one volume per service, so we must
    inspect the project's existing volume instances and skip when there
    is already an attachment for this service. Re-running the
    provisioner therefore never raises a "would have 2 volumes" error.
    """
    data = gql(
        """
        query($id: String!) {
          project(id: $id) {
            volumes {
              edges {
                node {
                  id
                  volumeInstances {
                    edges { node { id serviceId mountPath } }
                  }
                }
              }
            }
          }
        }
        """,
        {"id": project_id},
    )
    for vol_edge in data["project"]["volumes"]["edges"]:
        for inst_edge in vol_edge["node"]["volumeInstances"]["edges"]:
            inst = inst_edge["node"]
            if inst["serviceId"] == service_id:
                # Already mounted; nothing to do (even if the mountPath
                # differs — Railway only allows one volume per service).
                return
    gql(
        "mutation($input: VolumeCreateInput!) { volumeCreate(input: $input) { id } }",
        {
            "input": {
                "projectId": project_id,
                "environmentId": env_id,
                "serviceId": service_id,
                "mountPath": mount,
            }
        },
    )


def ensure_public_domain(env_id: str, service_id: str, port: int) -> Optional[str]:
    """Idempotently expose ``service_id`` on a Railway-generated domain."""
    existing = gql(
        """
        query($svc: String!, $env: String!) {
          domains(serviceId: $svc, environmentId: $env) {
            serviceDomains { id domain targetPort }
          }
        }
        """,
        {"svc": service_id, "env": env_id},
    ).get("domains", {}).get("serviceDomains", [])
    if existing:
        return existing[0]["domain"]
    data = gql(
        "mutation($input: ServiceDomainCreateInput!) { serviceDomainCreate(input: $input) { id domain } }",
        {
            "input": {
                "environmentId": env_id,
                "serviceId": service_id,
                "targetPort": port,
            }
        },
    )
    return data["serviceDomainCreate"]["domain"]


def trigger_redeploy(env_id: str, service_id: str) -> None:
    gql(
        "mutation($serviceId: String!, $environmentId: String!) { serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId) }",
        {"serviceId": service_id, "environmentId": env_id},
    )


# ---------------------------------------------------------------------------
# Main reconcile loop
# ---------------------------------------------------------------------------

def main() -> None:
    spec: dict[str, Any] = json.loads(SPEC_PATH.read_text())
    services = spec["services"]

    project_id, env_id = ensure_project()
    existing = list_existing_services(project_id)
    print(f"Project {project_id} environment {env_id}; {len(existing)} existing service(s).")

    public_domain: Optional[str] = None

    for svc in services:
        name = svc["name"]
        if name in existing:
            service_id = existing[name]
            print(f"\n[=] {name}  ({service_id}, already present)")
        else:
            print(f"\n[+] {name}  (creating from {svc['image']})")
            try:
                service_id = create_service(project_id, name, svc["image"])
            except SystemExit as exc:
                if "Free plan resource provision limit" in str(exc):
                    print(
                        f"    SKIPPED — Railway free-plan service cap reached. "
                        f"Upgrade the workspace and re-run to provision {name}."
                    )
                    continue
                raise

        if svc.get("env"):
            upsert_variables(project_id, env_id, service_id, svc["env"])
            print(f"    variables: {len(svc['env'])} keys set")

        if svc.get("volume"):
            ensure_volume(project_id, env_id, service_id, svc["volume"])
            print(f"    volume:    {svc['volume']}")

        if svc.get("expose"):
            domain = ensure_public_domain(env_id, service_id, svc["expose"])
            public_domain = domain
            print(f"    public:    https://{domain}  -> :{svc['expose']}")

        trigger_redeploy(env_id, service_id)
        print(f"    redeploy:  triggered")

    print("\nReconcile complete.")
    if public_domain:
        print(f"Public URL: https://{public_domain}")


if __name__ == "__main__":
    main()
