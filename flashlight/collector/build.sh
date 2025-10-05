#!/bin/sh

set -eu

docker_repository_url='northamerica-northeast2-docker.pkg.dev/prism-overlay/flashlight-dockerimages'

action="${1:-}"
service_name="${2:-}"

case $service_name in
flashlight)
    image_name='flashlight-otel-collector'
    ;;
flashlight-test)
    image_name='flashlight-test-otel-collector'
    ;;
*)
    echo "Invalid/missing service name '$service_name'. Must be 'flashlight' or 'flashlight-test'" >&2
    exit 1
    ;;
esac

image="$docker_repository_url/$image_name:latest"

case $action in
get-url)
    echo "$image"

    exit 0
    ;;
build-and-push)
    docker build -t "$image" "$(dirname "$0")"
    docker push "$image"

    exit 0
    ;;
*)
    echo "Invalid/missing action '$action'. Must be 'get-url' or 'build-and-push'" >&2
    exit 1
    ;;
esac
