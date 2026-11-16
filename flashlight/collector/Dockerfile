# Dockerfile for the sidecar OTEL Collector
# Based on: https://cloud.google.com/run/docs/tutorials/custom-metrics-opentelemetry-sidecar
# https://github.com/GoogleCloudPlatform/opentelemetry-operations-collector
FROM us-docker.pkg.dev/cloud-ops-agents-artifacts/google-cloud-opentelemetry-collector/otelcol-google:0.164.0@sha256:871b9e716d8749660c0e5fd7e7fd5a21b04d412919ab86792528ee4cfa258f89

COPY config.yaml /etc/otelcol-google/config.yaml
