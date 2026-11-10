# Dockerfile for the sidecar OTEL Collector
# Based on: https://cloud.google.com/run/docs/tutorials/custom-metrics-opentelemetry-sidecar
# https://github.com/GoogleCloudPlatform/opentelemetry-operations-collector
FROM us-docker.pkg.dev/cloud-ops-agents-artifacts/google-cloud-opentelemetry-collector/otelcol-google:0.162.0@sha256:4e67d188de2ccb863ce6fb0808a257e9ecb6df93f8be9227cfb5c4e00cc26f24

COPY config.yaml /etc/otelcol-google/config.yaml
