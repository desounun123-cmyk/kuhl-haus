# Monitoring

Prometheus-based monitoring for the kuhl-haus data plane components using the [Prometheus JSON Exporter](https://github.com/prometheus-community/json_exporter) to scrape health check endpoints and convert the JSON responses into Prometheus metrics.

## Overview

The data plane exposes HTTP health check endpoints (`/health`) on each component. The JSON Exporter acts as a sidecar that fetches these JSON payloads and translates them into Prometheus-compatible metrics. Prometheus then scrapes the JSON Exporter using its `/probe` endpoint with relabel configs to pass through the original target URL.

### Components Monitored

| Component | Module | Health Endpoint | Description |
|---|---|---|---|
| **MDL** — Market Data Listener | `mdl_health` | `https://mdl.example.com/health` | Listens to market data feeds via WebSocket and publishes messages to queues |
| **MDP** — Market Data Processor | `mdp_health` | `https://mdp.example.com/health` | Consumes queued messages and processes them with parallel workers |
| **WDS** — Widget Data Service | `wds_health` | `https://wds.example.com/health` | Serves processed data to clients over WebSocket |
| **FDL** — Finlight Data Listener | `fdl_health` | `https://fdl.example.com/health` | Connects to Finlight WebSocket feed and publishes enriched news articles to RabbitMQ |
| **FDP** — Finlight Data Processor | `fdp_health` | `https://fdp.example.com/health` | Consumes news articles from RabbitMQ and caches enriched results in Redis |

## Architecture

```
Health Endpoints ──► JSON Exporter (:7979) ──► Prometheus (:9090)
```

Prometheus is configured to scrape each component every 30 seconds. It sends requests to the JSON Exporter's `/probe` endpoint, which in turn fetches the JSON from the target health URL, extracts metrics according to `json_exporter_config.yml`, and returns them in Prometheus exposition format.

## Files

| File | Purpose |
|---|---|
| `compose.yml` | Docker Compose stack running the JSON Exporter and Prometheus |
| `json_exporter_config.yml` | Metric extraction rules — maps JSON paths from health responses to Prometheus metrics |
| `prometheus.yml` | Prometheus scrape configuration with jobs for MDL, MDP, WDS, FDL, and FDP |

## Metrics

### MDL (Market Data Listener)

| Metric | Description |
|---|---|
| `kuhl_haus_service_up` | Service status (1=OK, 0=not OK), with `service`, `container_image`, and `image_version` labels |
| `kuhl_haus_mdl_auto_start_enabled` | Whether auto-start is enabled |
| `kuhl_haus_mdl_mdq_connected` | Connection status to the message queue |
| `kuhl_haus_mdl_feed_connected` | WebSocket feed connection status (includes `feed` and `market` labels) |
| `kuhl_haus_mdl_reconnect_attempts_total` | Total reconnection attempts |
| `kuhl_haus_mdl_messages_received_total` | Total messages received from the WebSocket feed |
| `kuhl_haus_mdl_message_total` | Messages by queue type (`trades`, `aggregate`, `quotes`, `halts`, `news`, `unknown`) |
| `kuhl_haus_mdl_errors_total` | Error counts by type (e.g. `unsupported`) |

### MDP (Market Data Processor)

| Metric | Description |
|---|---|
| `kuhl_haus_service_up` | Service status (1=OK, 0=not OK) |
| `kuhl_haus_mdp_parallelism` | Configured parallelism level |
| `kuhl_haus_mdp_prefetch_count` | Queue prefetch count |
| `kuhl_haus_mdp_max_concurrency` | Max concurrency setting |

Per-worker metrics (labeled by `worker_id`, workers 0–31):

| Metric | Description |
|---|---|
| `kuhl_haus_mdp_processor_alive` | Worker alive status |
| `kuhl_haus_mdp_processor_running` | Worker running status |
| `kuhl_haus_mdp_processor_processed_total` | Total messages processed |
| `kuhl_haus_mdp_processor_errors_total` | Total processing errors |
| `kuhl_haus_mdp_processor_decoding_errors_total` | Total decoding errors |
| `kuhl_haus_mdp_processor_published_total` | Total messages published |
| `kuhl_haus_mdp_processor_processing_errors` | Errors due to DataAnalysisException |
| `kuhl_haus_mdp_processor_mdq_connected` | MDQ connection status |
| `kuhl_haus_mdp_processor_mdc_connected` | MDC connection status |
| `kuhl_haus_mdp_processor_restarts_total` | Worker restart count |

### WDS (Widget Data Service)

| Metric | Description |
|---|---|
| `kuhl_haus_service_up` | Service status (1=OK, 0=not OK) |
| `kuhl_haus_wds_active_websocket_clients` | Number of active WebSocket client connections |

### FDL (Finlight Data Listener)

| Metric | Description |
|---|---|
| `kuhl_haus_service_up` | Service status (1=OK, 0=not OK), with `service`, `container_image`, and `image_version` labels |
| `kuhl_haus_fdl_auto_start_enabled` | Whether auto-start is enabled |
| `kuhl_haus_fdl_fdq_connected` | RabbitMQ queue connection status |
| `kuhl_haus_fdl_fdq_messages_received_total` | Total messages received from the RabbitMQ queue |
| `kuhl_haus_fdl_fdq_news_received_total` | Total news messages received (labeled `queue: 'news'`) |
| `kuhl_haus_fdl_fdq_reconnect_attempts_total` | Total RabbitMQ reconnection attempts |
| `kuhl_haus_fdl_feed_connected` | Finlight WebSocket feed connection status |
| `kuhl_haus_fdl_feed_healthy` | Finlight WebSocket feed health status |
| `kuhl_haus_fdl_articles_received_total` | Total articles received from Finlight |
| `kuhl_haus_fdl_errors_total` | Total Finlight connection errors |

### FDP (Finlight Data Processor)

| Metric | Description |
|---|---|
| `kuhl_haus_service_up` | Service status (1=OK, 0=not OK) |
| `kuhl_haus_fdp_prefetch_count` | RabbitMQ prefetch count |
| `kuhl_haus_fdp_max_concurrency` | Maximum processing concurrency |
| `kuhl_haus_fdp_processed_total` | Total articles processed (labeled `processor_type: 'news'`) |
| `kuhl_haus_fdp_published_total` | Total results published to Redis (labeled `processor_type: 'news'`) |
| `kuhl_haus_fdp_errors_total` | Total processing errors (labeled `processor_type: 'news'`) |
| `kuhl_haus_fdp_processing_errors_total` | Total processing-stage errors (labeled `processor_type: 'news'`) |
| `kuhl_haus_fdp_decoding_errors_total` | Total message decoding errors (labeled `processor_type: 'news'`) |
| `kuhl_haus_fdp_mdq_connected` | MDQ (RabbitMQ) connection status |
| `kuhl_haus_fdp_mdc_connected` | MDC (Redis) connection status |

## Usage

### Prerequisites

- Docker and Docker Compose
- Network access to the health check endpoints of your data plane components

### Getting Started

1. Update `prometheus.yml` with your actual health check URLs and the IP address of the host running the JSON Exporter:

   ```yaml
   static_configs:
     - targets:
       - https://your-mdl-host.example.com/health
   # ...
   relabel_configs:
     - target_label: __address__
       replacement: <your-json-exporter-host>:7979
   ```

2. Optionally update the `UID` and `GID` environment variables in `compose.yml` to match your host user. Find your values with:

   ```bash
   id -u && id -g
   ```

3. Start the stack:

   ```bash
   docker compose up -d
   ```

4. Prometheus will be available at `http://localhost:9090`.