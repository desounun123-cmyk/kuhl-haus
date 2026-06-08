<!-- 

TODO:
[![ReadTheDocs](https://readthedocs.org/projects/kuhl-haus-metrics/badge/?version=latest)](https://kuhl-haus-metrics.readthedocs.io/en/stable/)

-->



# kuhl-haus-metrics

[![License](https://img.shields.io/github/license/kuhl-haus/kuhl-haus-metrics)](https://github.com/kuhl-haus/kuhl-haus-metrics/blob/mainline/LICENSE.txt)
[![PyPI](https://img.shields.io/pypi/v/kuhl-haus-metrics.svg)](https://pypi.org/project/kuhl-haus-metrics/)
[![Downloads](https://static.pepy.tech/badge/kuhl-haus-metrics/month)](https://pepy.tech/project/kuhl-haus-metrics)
[![Build Status](https://github.com/kuhl-haus/kuhl-haus-metrics/actions/workflows/publish-to-pypi.yml/badge.svg)](https://github.com/kuhl-haus/kuhl-haus-metrics/actions/workflows/publish-to-pypi.yml)
[![CodeQL](https://github.com/kuhl-haus/kuhl-haus-metrics/workflows/CodeQL/badge.svg)](https://github.com/kuhl-haus/kuhl-haus-metrics/actions/workflows/github-code-scanning/codeql/)
[![codecov](https://codecov.io/gh/kuhl-haus/kuhl-haus-metrics/branch/mainline/graph/badge.svg)](https://codecov.io/gh/kuhl-haus/kuhl-haus-metrics)
[![GitHub issues](https://img.shields.io/github/issues/kuhl-haus/kuhl-haus-metrics)](https://github.com/kuhl-haus/kuhl-haus-metrics/issues)
[![GitHub pull requests](https://img.shields.io/github/issues-pr/kuhl-haus/kuhl-haus-metrics)](https://github.com/kuhl-haus/kuhl-haus-metrics/pulls)

## Overview

kuhl-haus-metrics is a Python library for application logging and instrumentation. It provides tools and utilities to help developers track application performance, collect metrics, and monitor system behavior in real-time.

## Features

- Comprehensive application logging
- Performance metrics collection
- Instrumentation for monitoring application behavior
- Extensible architecture for custom metrics

## Installation

You can install kuhl-haus-metrics via pip:

```bash
pip install kuhl-haus-metrics
```

## Quick Start

Here's a simple example to get you started:

```python
import ssl
import time
from datetime import datetime
from logging import Logger

import OpenSSL
from kuhl_haus.metrics.data.metrics import Metrics
from kuhl_haus.metrics.factories.logs import get_logger
from kuhl_haus.metrics.clients.carbon_poster import CarbonPoster


def get_tls_cert_expiration_days(hostname: str, port: int) -> int:
    raw_cert = ssl.get_server_certificate((hostname, port))
    cert = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, raw_cert.encode())
    expiration_time = time.mktime(datetime.strptime(cert.get_notAfter().decode(), '%Y%m%d%H%M%S%fZ').timetuple())
    current_time = time.mktime(datetime.now().timetuple())
    return int(expiration_time - current_time) // 60 // 60 // 24


logger: Logger = get_logger(log_level='INFO')
carbon_poster: CarbonPoster = CarbonPoster(server_ip="127.0.0.1", pickle_port=2004)

# hostname and port to check
host_name = "foo.com"
host_port = 443
# Initialize metrics
metrics: Metrics = Metrics(
    mnemonic="mnemonic",
    namespace="namespace",
    hostname=host_name,
    counters={
        'exceptions': 0,
        'requests': 0,
        'responses': 0,
    },
    attributes={
        "hostport": host_port
    }
)
try:
    metrics.set_counter('requests', 1)
    days_until_expiration = get_tls_cert_expiration_days(host_name, host_port)
    metrics.set_counter('responses', 1)
    metrics.attributes["days_until_expiration"] = days_until_expiration
    metrics.attributes["expires_today"] = days_until_expiration <= 1
    metrics.attributes["is_valid"] = days_until_expiration > 0
except Exception as e:
    metrics.set_counter('exceptions', 1)
    metrics.attributes['exception'] = repr(e)
    logger.exception(msg=f"unhandled exception processing {host_name}:{host_port}", exc_info=e)

carbon_poster.post_metrics(metrics=metrics.carbon)

```

## Documentation

For detailed documentation and API reference, please visit our [documentation site](https://github.com/kuhl-haus/kuhl-haus-metrics/wiki).

## Requirements

- Python 3.12+

## Development

### Setting Up Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/kuhl-haus/kuhl-haus-metrics.git
   cd kuhl-haus-metrics
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install development dependencies:
   ```bash
   pip install -r requirements.txt
   pdm install
   ```

### Running Tests

Tests are managed with pytest:

```bash
pdm run pytest tests -v
```

For test coverage:

```bash
pdm run pytest --cov=kuhl_haus.metrics --cov-report=html --cov-report=xml tests -v
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please make sure to update tests as appropriate and adhere to the project's coding standards.

## License

This project is licensed under the terms of the license file included in the repository. See [LICENSE.txt](https://github.com/kuhl-haus/kuhl-haus-metrics/blob/mainline/LICENSE.txt) for details.

## Support

If you encounter any issues or have questions, please [open an issue](https://github.com/kuhl-haus/kuhl-haus-metrics/issues) on GitHub.

## Acknowledgements

- This project was generated with [PyScaffold](https://pyscaffold.org/) 4.6

---

Built with ❤️ by the kuhl-haus team.

