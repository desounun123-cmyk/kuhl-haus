# kuhl-haus

Kuhl Haus Market Data Platform — monorepo.

## Structure

````
packages/
  mdp/       # Core market data processing library
  servers/   # Backend microservices (MDL, MDP, LBA, WDS, FDL, FDP, MDS)
  app/       # Web app / dashboard (py4web + Vue.js)
  metrics/   # Logging / instrumentation library
deploy/
  Docker/    # Docker Compose for local development
  ansible/   # Kubernetes production deployment
  scripts/   # Deployment automation
```

## Quick Start (Docker Compose)

````bash
export MASSIVE_API_KEY=your_key
docker compose -f deploy/Docker/compose.yaml up -d --build
open http://localhost:8000
```

## Documentation

See [kuhl-haus-mdp.readthedocs.io](https://kuhl-haus-mdp.readthedocs.io)
