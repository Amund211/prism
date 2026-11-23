# Dockerfile for the sidecar OTEL Collector
# Based on: https://cloud.google.com/run/docs/tutorials/custom-metrics-opentelemetry-sidecar
# https://github.com/GoogleCloudPlatform/opentelemetry-operations-collector
FROM us-docker.pkg.dev/cloud-ops-agents-artifacts/google-cloud-opentelemetry-collector/otelcol-google:0.165.1@sha256:8cdd5c85128a7f0b73710761487ee747ff9eadc7d7c090d91873aa3fdc1663cd

COPY config.yaml /etc/otelcol-google/config.yaml
