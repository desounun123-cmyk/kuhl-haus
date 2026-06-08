# Kuhl Haus MDP - Market Data Platform

## Overview

The Kuhl Haus Market Data Platform (MDP) is a distributed system for collecting, processing, and serving real-time market data. Built on Kubernetes and leveraging microservices architecture, MDP provides scalable infrastructure for financial data analysis and visualization.

Check out [my blog post](https://the.oldschool.engineer/what-i-built-after-quitting-amazon-spoiler-its-a-stock-scanner-part-3-eab7d9bbf5f7), where I walk through the complete MDP deployment process—from scratch installation on Docker Desktop to end-to-end validation testing.


## Prerequisites

### System Requirements

- **Operating System**: Linux, macOS, or Windows with WSL2
- **RAM**: Minimum 8 GB (16 GB recommended)
- **Disk Space**: 20 GB available
- **Network**: Stable internet connection for Docker image pulls

### Required Software

#### Kubernetes

This tutorial uses Kubernetes on Docker Desktop for consistency and ease of setup. The deployment manifests can be adapted for production Kubernetes clusters such as Amazon EKS, Google GKE, or Azure AKS with minimal modifications to network and ingress configurations.

**Installation**:
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop)
2. Enable Kubernetes in Docker Desktop settings
3. Verify installation: `kubectl version --client`

#### Ansible

Ansible 2.19 or higher is required for running the deployment playbooks.

**Installation**: Follow the [official Ansible installation guide](https://docs.ansible.com/ansible/latest/installation_guide/index.html) for your operating system.

---

## Setup

### 1. Clone the Repositories

Create a workspace directory and clone all three project repositories:

```bash
mkdir ~/kuhl-haus
cd ~/kuhl-haus
gh repo clone kuhl-haus/kuhl-haus-mdp-servers
gh repo clone kuhl-haus/kuhl-haus-mdp-app
gh repo clone kuhl-haus/kuhl-haus-mdp-deployment
```

**Note**: If you don't have the GitHub CLI installed, you can use standard `git clone` commands with HTTPS URLs.

### 2. Configure Ansible Vault

Sensitive configuration values are stored in an encrypted Ansible Vault file. Create and configure it as follows:

```bash
cd ~/kuhl-haus/kuhl-haus-mdp-deployment
ansible-vault create ansible/group_vars/secrets.yml
```

You'll be prompted to create a vault password. Store this password securely - you'll need it for all future deployments.

**Useful Vault Commands**:

```bash
# Edit existing encrypted file
ansible-vault edit ansible/group_vars/secrets.yml

# View encrypted file contents
ansible-vault view ansible/group_vars/secrets.yml

# Change vault password
ansible-vault rekey ansible/group_vars/secrets.yml
```

### 3. Configure Secrets

Add the following configuration to your `secrets.yml` file (while in edit mode):

```yaml
# AWS SES SMTP credentials for email notifications
aws_ses_smtp_username: ""
aws_ses_smtp_password: ""

# AWS Route53 credentials for ACME certificate management
acme_prod_route53_access_key_id: ""
acme_prod_route53_secret_access_key: ""

# Cloudflare DNS credentials for ACME certificate management
cloudflare_prod_dns_api_token: ""
cloudflare_prod_global_api_key: ""

# Google OAuth credentials (obtain from Google Cloud Console)
google_oauth_client_id: ""
google_oauth_client_secret: ""

# Market data API credentials
prod_massive_api_key: ""
prod_massive_s3_access_key: ""
prod_massive_s3_secret_key: ""

# Administrator information
admin_name: ""
admin_email: ""

# Development environment credentials
dev_otel_exporter_otlp_endpoint: ""
dev_otel_exporter_otlp_headers: ""
dev_admin_password: ""
dev_wds_api_token: ""
dev_postgres_password: ""
dev_replication_password: ""
dev_rabbitmq_password: ""
dev_redis_password: ""

# py4web session encryption key (generate with: python -c "import secrets; print(secrets.token_hex(32))")
py4web_session_secret_key: ""
```

Replace empty strings with your actual credentials and save the file.

---

## Deployment

### Environment Configuration

Before running any deployment scripts, set the required environment variables:

```bash
export APP_ENV=development
export BASE_WORKING_DIR=~/kuhl-haus

# Domain configuration (adjust for your environment)
export APP_DOMAIN=mdp.example.com
export MDC_SERVER_DOMAIN=mdp-cache.example.com
export MDL_SERVER_DOMAIN=mdp-listener.example.com
export MDP_SERVER_DOMAIN=mdp-processor.example.com
export MDQ_SERVER_DOMAIN=mdp-queues.example.com
export WDS_SERVER_DOMAIN=wds.example.com
```

**Variable Reference**:

| Variable | Description | Example |
|----------|-------------|---------|
| `APP_ENV` | Deployment environment (development/staging/production) | `development` |
| `BASE_WORKING_DIR` | Root directory containing cloned repositories | `~/kuhl-haus` |
| `APP_DOMAIN` | Main application domain | `mdp.example.com` |
| `MDC_SERVER_DOMAIN` | Market data cache service domain | `mdp-cache.example.com` |
| `MDL_SERVER_DOMAIN` | Market data listener service domain | `mdp-listener.example.com` |
| `MDP_SERVER_DOMAIN` | Market data processor service domain | `mdp-processor.example.com` |
| `MDQ_SERVER_DOMAIN` | Market data queues service domain | `mdp-queues.example.com` |
| `WDS_SERVER_DOMAIN` | Widget data service domain | `wds.example.com` |

### Deployment Steps

#### Step 1: Install Prerequisites

Install required dependencies on the Ansible control host:

```bash
./scripts/01-run-prereq-playbook.sh
```

This installs necessary Python packages, Kubernetes tools, and Ansible collections.

#### Step 2: Deploy Kubernetes Infrastructure

Provision the essential Kubernetes infrastructure including networking, ingress, and certificate manager:

```bash
./scripts/02-run-k8s-infra-playbook.sh
```

#### Step 3: Deploy the Application

Deploy the frontend application and web server:

```bash
./scripts/03-run-app-playbook.sh
./scripts/smoke-test-app.sh
```

The smoke test verifies that the application is running and responding correctly.

#### Step 4: Deploy Data Plane Services

Deploy backend services in the following order:

##### Step 4.1 - Certificate Manager

Deploy certificate management for TLS/SSL:

```bash
./scripts/04-run-data-plane-playbook.sh deploy-dp-cm.yml
```

##### Step 4.2 - Market Data Cache

Deploy Redis-based caching layer:

```bash
./scripts/04-run-data-plane-playbook.sh deploy-mdc.yml
./scripts/smoke-test-mdc.sh
```

##### Step 4.3 - Market Data Queues

Deploy RabbitMQ message queuing system:

```bash
./scripts/04-run-data-plane-playbook.sh deploy-mdq.yml
./scripts/smoke-test-mdq.sh
```

##### Step 4.4 - Market Data Listener

Deploy the market data ingestion service:

```bash
./scripts/04-run-data-plane-playbook.sh deploy-mdl.yml
./scripts/smoke-test-mdl.sh
```

##### Step 4.5 - Market Data Processors

Deploy data processing workers:

```bash
./scripts/04-run-data-plane-playbook.sh deploy-mdp.yml
./scripts/smoke-test-mdp.sh
```

##### Step 4.6 - Widget Data Service

Deploy the widget data WebSocket service:

```bash
./scripts/04-run-data-plane-playbook.sh deploy-wds.yml
./scripts/smoke-test-wds.sh
```



---

## Troubleshooting

### Common Issues

**Issue**: Ansible vault password prompt fails

**Solution**: Ensure you're using the correct vault password. Use `ansible-vault rekey` if you need to change it.

**Issue**: Pods remain in `Pending` state

**Solution**: Check resource availability with `kubectl describe pod <pod-name>`. You may need to allocate more resources to Docker Desktop.

**Issue**: Certificate provisioning fails

**Solution**: Verify your DNS credentials in `secrets.yml` and ensure DNS records are properly configured. Verify the value for `acme_prod_email` and ensure it is correct.

**Issue**: Service health checks fail

**Solution**: Review logs with `kubectl logs <pod-name>` and verify all dependencies are running.

---

