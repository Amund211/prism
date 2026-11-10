#!/bin/sh

set -eu

env_file="$(dirname "$0")/.env"

if [ ! -f "$env_file" ]; then
	echo "Missing cmd/.env"
	echo "    echo 'export HYPIXEL_API_KEY=<your-key-here>' > cmd/.env"
	exit 1
fi

. "$env_file"

LOCAL_ONLY=true
FLASHLIGHT_ENVIRONMENT="${FLASHLIGHT_ENVIRONMENT:-development}" \
	PORT="${1:-8123}" \
	go run main.go
