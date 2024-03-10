#!/bin/sh

set -eu

function_name="${1:-}"

case $function_name in
	flashlight)
		sentry_dsn_key='flashlight-sentry-dsn'
		;;
	flashlight-test)
		sentry_dsn_key='flashlight-test-sentry-dsn'
		;;
	*)
		echo "Invalid/missing function name '$function_name'. Must be 'flashlight' or 'flashlight-test'" >&2
		exit 1
		;;
esac

gcloud functions deploy "$function_name" \
	--gen2 \
	--region=northamerica-northeast2 \
	--runtime=go121 \
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
	--set-secrets "SENTRY_DSN=${sentry_dsn_key}:latest"

# Verify that newly deployed function works
curl --fail "https://northamerica-northeast2-prism-overlay.cloudfunctions.net/${function_name}?uuid=a937646b-f115-44c3-8dbf-9ae4a65669a0"
