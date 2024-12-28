#!/bin/sh

set -eu

function_name="${1:-}"

case $function_name in
flashlight)
	service_name='flashlight-cr'
	sentry_dsn_key='flashlight-sentry-dsn'
	environment='production'
	;;
flashlight-test)
	service_name='flashlight-test-cr'
	sentry_dsn_key='flashlight-test-sentry-dsn'
	environment='staging'
	;;
*)
	echo "Invalid/missing function name '$function_name'. Must be 'flashlight' or 'flashlight-test'" >&2
	exit 1
	;;
esac

gcloud run deploy "$service_name" \
	--source . \
	--region=northamerica-northeast2 \
	--max-instances=1 \
	--min-instances=0 \
	--timeout=30s \
	--cpu=1 \
	--memory=128Mi \
	--allow-unauthenticated \
	--concurrency 100 \
	--set-cloudsql-instances prism-overlay:northamerica-northeast2:flashlight-postgres \
	--set-secrets HYPIXEL_API_KEY=prism-hypixel-api-key:latest \
	--set-secrets DB_PASSWORD=flashlight-db-password:latest \
	--set-secrets "SENTRY_DSN=${sentry_dsn_key}:latest" \
	--set-env-vars "FLASHLIGHT_ENVIRONMENT=${environment}" \
	--set-env-vars 'DB_USERNAME=postgres' \
	--set-env-vars 'CLOUDSQL_UNIX_SOCKET=/cloudsql/prism-overlay:northamerica-northeast2:flashlight-postgres'

# Verify that newly deployed function works
echo 'Making request to new deployment' >&2
response="$(
	curl \
		--fail \
		-sS \
		-H 'X-User-Id: gha-deployment-verifier' \
		-H 'User-Agent: gha-deployment-verifier' \
		"https://${service_name}-184945651621.northamerica-northeast2.run.app/playerdata?uuid=a937646b-f115-44c3-8dbf-9ae4a65669a0"
)"

echo 'Verifying response from new deployment' >&2
if ! echo "$response" | grep 'Skydeath' >/dev/null; then
	echo 'Could not find username in response!' >&2
	echo "Response: $response" >&2
	exit 1
fi
