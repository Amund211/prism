#!/bin/sh

set -eu

PORT="${1:-8800}"

UUID="a937646b-f115-44c3-8dbf-9ae4a65669a0"
UUID_SNIPPET="a937646b"

# NOTE: Not doing any cleanup here. Couldn't figure out how to get the
#		proper pid to kill.
echo 'Starting server' >&2
./cmd/run.sh "$PORT" >/dev/null 2>&1 &

while ! curl \
	--fail \
	--silent \
	"localhost:$PORT/playerdata?uuid=$UUID" >/dev/null 2>&1; do
	echo 'Waiting for server to start' >&2
	sleep 0.5
done

# Should all be allowed
echo 'Issuing initial (allowed) requests' >&2
for i in $(seq 1 480); do
	curl \
		--fail \
		--silent \
		-H "X-User-Id: my-user-id-$i" \
		"localhost:$PORT/playerdata?uuid=$UUID" |
		grep "$UUID_SNIPPET" >/dev/null 2>&1
done

# Might get denied, depending on how long we took
echo 'Issuing secondary (maybe disallowed) requests' >&2
for i in $(seq 1 480); do
	curl \
		--silent \
		-H "X-User-Id: my-user-id-$i" \
		"localhost:$PORT/playerdata?uuid=$UUID" >/dev/null 2>&1 ||
		true
done

echo 'Issuing final (disallowed) requests' >&2
for i in $(seq 1 10); do
	if ! curl \
		--fail \
		-H "X-User-Id: my-user-id-$i" \
		"localhost:$PORT/playerdata?uuid=$UUID" >/dev/null 2>&1; then
		exit 0
	fi
done
echo 'All requests succeeded when ip should have been rate limited!' >&2
exit 1
