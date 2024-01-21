#!/bin/sh

env_file="$(dirname "$0")/../.env"

if [ ! -f "$env_file" ]; then
	echo "Missing cmd/.env"
	echo "    echo 'export HYPIXEL_API_KEY=<your-key-here>' > cmd/.env"
	exit 1
fi

. "$env_file"

go run cmd/get-stats/main.go "$1"
