ARG BASE_IMAGE=python:3.13-slim
FROM ${BASE_IMAGE}

WORKDIR /opt/kuhl_haus/metrics
COPY . /opt/kuhl_haus/metrics/

# Install PDM
RUN pip install --no-cache-dir pdm

# Install the package directly from the wheel
RUN pdm build && pip install --no-cache-dir /opt/kuhl_haus/metrics/dist/*.whl

# Create an idle script that properly handles signals
RUN echo '#!/bin/sh\ntrap : TERM INT; sleep infinity & wait' > /idle.sh && \
    chmod +x /idle.sh

# Set the entrypoint to the idle script
ENTRYPOINT ["/idle.sh"]
