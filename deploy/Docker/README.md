# Stock Scanner - Docker Configuration

**TL;DR:** Public Docker Compose and Dockerfile configurations for the stock scanner application detailed in [Part 2 of the blog series](https://the.oldschool.engineer/what-i-built-after-quitting-amazon-spoiler-its-a-stock-scanner-part-2-94e445914951). Pre-built images available for quick deployment with real-time WebSocket market data via Massive.com API.

## Quick Start

1. Clone this repository
2. Add your Massive.com API key to compose.yaml (edit the MASSIVE_API_KEY environment variable)
3. Launch: `docker compose up -d`
4. Access the application at http://localhost:8000 and login

## What's Included

- **`compose.yaml`**: Orchestrates pre-built container images for immediate deployment
- **`Dockerfile`**: Build configuration for custom modifications

## Prerequisites

- Docker & Docker Compose installed
- **Massive.com API subscription** (Stocks Advanced $200/month recommended for real-time WebSocket data)

---

## FAQ

**Q: Can I use the free Massive.com tier?**  
A: No. The free Stocks Basic plan lacks WebSocket support required for real-time data. The $29/month Stocks Starter _might_ work but has 15-minute delayed data.

**Q: Do I need to build from source?**  
A: No. The `compose.yaml` references pre-built public images. Only build from source if you're customizing the application.

**Q: Where do I add my API key?**  
A: Edit the `MASSIVE_API_KEY` environment variable in `compose.yaml` before running `docker compose up`.

**Q: What port does the application use?**  
A: Check the port mapping in `compose.yaml`. Default is typically exposed in the `ports:` section.

**Q: Can I customize the scanner logic?**  
A: Yes. Use the `Dockerfile` to build from source with your modifications. See [Part 2 of the blog series](https://the.oldschool.engineer/what-i-built-after-quitting-amazon-spoiler-its-a-stock-scanner-part-2-94e445914951) for building instructions.

