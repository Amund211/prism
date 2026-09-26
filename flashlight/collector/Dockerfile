# Dockerfile for the sidecar OTEL Collector
# Based on: https://cloud.google.com/run/docs/tutorials/custom-metrics-opentelemetry-sidecar
# https://github.com/GoogleCloudPlatform/opentelemetry-operations-collector
FROM us-docker.pkg.dev/cloud-ops-agents-artifacts/google-cloud-opentelemetry-collector/otelcol-google:0.160.0@sha256:2bebb885ef33c00e1d999dc0b0dd13b089f8ddb1734b62c0a0524b2cf20c515e

COPY config.yaml /etc/otelcol-google/config.yaml
