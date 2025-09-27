#!/bin/sh

set -eu

docker_repository_url='northamerica-northeast2-docker.pkg.dev/prism-overlay/flashlight-dockerimages'

function_name="${1:-}"

case $function_name in
flashlight)
	service_name='flashlight-cr'
	sentry_dsn_key='flashlight-sentry-dsn'
	environment='production'
	image_name='flashlight'
	;;
flashlight-test)
	service_name='flashlight-test-cr'
	sentry_dsn_key='flashlight-test-sentry-dsn'
	environment='staging'
	image_name='flashlight-test'
	;;
*)
	echo "Invalid/missing function name '$function_name'. Must be 'flashlight' or 'flashlight-test'" >&2
	exit 1
	;;
esac

image="$docker_repository_url/$image_name:latest"

docker build -t "$image" .

docker push "$image"

gcloud run deploy "$service_name" \
	--image "$image" \
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
		"https://${service_name}-184945651621.northamerica-northeast2.run.app/v1/playerdata?uuid=a937646b-f115-44c3-8dbf-9ae4a65669a0"
)"

echo 'Verifying response from new deployment' >&2
if ! echo "$response" | grep 'Skydeath' >/dev/null; then
	echo 'Could not find username in response!' >&2
	echo "Response: $response" >&2
	exit 1
fi
