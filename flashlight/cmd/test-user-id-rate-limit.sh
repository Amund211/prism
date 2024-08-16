#!/bin/sh

set -eu

PORT="${1:-8900}"

# NOTE: Not doing any cleanup here. Couldn't figure out how to get the
#		proper pid to kill.
echo 'Starting server' >&2
./cmd/run.sh "$PORT" >/dev/null 2>&1 &

while ! curl \
		--fail \
		--silent \
		"localhost:$PORT?uuid=some-requested-uuid" >/dev/null 2>&1; do
	echo 'Waiting for server to start' >&2
	sleep 0.5
done

# Should all be allowed
echo 'Issuing initial (allowed) requests' >&2
for _ in $(seq 1 120); do
	curl \
		--fail \
		--silent \
		-H 'X-User-Id: my-user-id' \
		"localhost:$PORT?uuid=some-requested-uuid" \
		| grep 'some-requested-uuid' >/dev/null 2>&1
done

# Might get denied, depending on how long we took
echo 'Issuing secondary (maybe disallowed) requests' >&2
for _ in $(seq 1 120); do
	curl \
		--silent \
		-H 'X-User-Id: my-user-id' \
		"localhost:$PORT?uuid=some-requested-uuid" >/dev/null 2>&1 \
		|| true
done

echo 'Issuing final (disallowed) request' >&2
if curl \
		--fail \
		-H 'X-User-Id: my-user-id' \
		"localhost:$PORT?uuid=some-requested-uuid" >/dev/null 2>&1; then
	echo 'Request succeeded when user should have been rate limited!'
	exit 1
fi
