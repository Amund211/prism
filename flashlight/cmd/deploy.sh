#!/bin/sh

set -eu

script_dir="$(dirname "$0")"

docker_repository_url='northamerica-northeast2-docker.pkg.dev/prism-overlay/flashlight-dockerimages'

function_name="${1:-}"

case $function_name in
flashlight)
	service_name='flashlight-cr'
	sentry_dsn_key='flashlight-sentry-dsn'
	auth_challenge_signing_keys_key='flashlight-auth-challenge-signing-keys'
	auth_session_signing_keys_key='flashlight-auth-session-signing-keys'
	environment='production'
	image_name='flashlight'
	public_url='https://flashlight.prismoverlay.com'
	;;
flashlight-test)
	service_name='flashlight-test-cr'
	sentry_dsn_key='flashlight-test-sentry-dsn'
	auth_challenge_signing_keys_key='flashlight-test-auth-challenge-signing-keys'
	auth_session_signing_keys_key='flashlight-test-auth-session-signing-keys'
	environment='staging'
	image_name='flashlight-test'
	public_url='https://flashlight-test.prismoverlay.com'
	;;
*)
	echo "Invalid/missing function name '$function_name'. Must be 'flashlight' or 'flashlight-test'" >&2
	exit 1
	;;
esac

# NOTE: Deprecated in favor of $public_url. Still verified so we notice if it breaks.
deprecated_cloud_run_url="https://${service_name}-184945651621.northamerica-northeast2.run.app"

# Requests the verifier player and checks that we get their username back.
verify_serving() {
	url="$1"

	echo "Making request to $url" >&2
	response="$(
		curl \
			--fail \
			-sS \
			-H 'X-User-Id: gha-deployment-verifier' \
			-H 'User-Agent: gha-deployment-verifier' \
			"$url/v1/playerdata?uuid=a937646b-f115-44c3-8dbf-9ae4a65669a0"
	)"

	echo "Verifying response from $url" >&2
	if ! echo "$response" | grep 'Skydeath' >/dev/null; then
		echo "Could not find username in response from $url!" >&2
		echo "Response: $response" >&2
		return 1
	fi
}

sidecar_image="$("$script_dir/../collector/build.sh" get-url "$function_name")"

image="$docker_repository_url/$image_name:latest"

docker build -t "$image" .

docker push "$image"

# NOTE: Since we're using a sidecar for telemetry collection, it is recommended to use an
# always-allocated CPU
# We're currently not doing this.
# Ref: https://cloud.google.com/stackdriver/docs/instrumentation/choose-approach#run
SERVICE_NAME="$service_name" \
	SERVICE_IMAGE="$(docker inspect --format='{{index .RepoDigests 0}}' "$image")" \
	FLASHLIGHT_ENVIRONMENT="$environment" \
	SENTRY_DSN_KEY="$sentry_dsn_key" \
	AUTH_CHALLENGE_SIGNING_KEYS_KEY="$auth_challenge_signing_keys_key" \
	AUTH_SESSION_SIGNING_KEYS_KEY="$auth_session_signing_keys_key" \
	COLLECTOR_IMAGE="$sidecar_image" \
	envsubst <"$script_dir/service.tmpl.yaml" >"$script_dir/service.yaml"

echo 'Deploying new service description:' >&2
cat "$script_dir/service.yaml" >&2

# Measure deploy-to-serving time: `gcloud run services replace` blocks until the
# revision is health-checked and Ready (so the cold start / startup probes happen
# here), and the first verification request below confirms it actually serves. We
# time from just before the replace through that response, i.e. through the public
# url clients actually use. The deprecated url is verified after the clock stops.
deploy_to_serving_start="$(date +%s.%N)"

gcloud run services replace "$script_dir/service.yaml"

# Verify that newly deployed function works
verify_serving "$public_url"

deploy_to_serving_end="$(date +%s.%N)"

verify_serving "$deprecated_cloud_run_url"

deploy_to_serving_seconds="$(awk "BEGIN { printf \"%.1f\", $deploy_to_serving_end - $deploy_to_serving_start }")"
echo "✓ Deployed and serving in ${deploy_to_serving_seconds}s (rollout + first successful request)." >&2
