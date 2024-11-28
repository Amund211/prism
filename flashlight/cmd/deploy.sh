#!/bin/sh

set -eu

function_name="${1:-}"

case $function_name in
flashlight)
	sentry_dsn_key='flashlight-sentry-dsn'
	environment='production'
	;;
flashlight-test)
	sentry_dsn_key='flashlight-test-sentry-dsn'
	environment='staging'
	;;
*)
	echo "Invalid/missing function name '$function_name'. Must be 'flashlight' or 'flashlight-test'" >&2
	exit 1
	;;
esac

gcloud functions deploy "$function_name" \
	--gen2 \
	--region=northamerica-northeast2 \
	--runtime=go122 \
	--entry-point=flashlight \
	--trigger-http \
	--max-instances=1 \
	--min-instances=0 \
	--timeout=30s \
	--cpu=1 \
	--memory=128Mi \
	--allow-unauthenticated \
	--concurrency 100 \
	--set-secrets HYPIXEL_API_KEY=prism-hypixel-api-key:latest \
	--set-secrets "SENTRY_DSN=${sentry_dsn_key}:latest" \
	--set-env-vars "FLASHLIGHT_ENVIRONMENT=${environment}"

# Verify that newly deployed function works
echo 'Making request to new deployment' >&2
response="$(
	curl \
		--fail \
		-sS \
		-H "X-User-Id: github-actions-$function_name" \
		"https://northamerica-northeast2-prism-overlay.cloudfunctions.net/${function_name}?uuid=a937646b-f115-44c3-8dbf-9ae4a65669a0"
)"

echo 'Verifying response from new deployment' >&2
if ! echo "$response" | grep 'Skydeath' >/dev/null; then
	echo 'Could not find username in response!' >&2
	echo "Response: $response" >&2
	exit 1
fi
