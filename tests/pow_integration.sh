#!/usr/bin/env bash
# Run the overlay's --test-pow mode and assert which solver ran, so a fallback
# to a slower solver can't pass.
#
# Usage: tests/pow_integration.sh <command that runs the overlay...>
# Set POW_TEST_ARCH when the command runs as another architecture (Rosetta).
set -euo pipefail

cmd=("$@")
arch="${POW_TEST_ARCH:-$(uname -m)}"
os="$(uname -s)"

mkdir -p pow-test
# Don't open the settings prompt
echo 'autowho = true' > pow-test/settings.toml
touch pow-test/latest.log

run_pow() {
	"${cmd[@]}" --test-pow="$1" --settings=pow-test/settings.toml --logfile=pow-test/latest.log
}

# check <solver> <expected name>
check() {
	local out
	out="$(run_pow "$1")"
	echo "$out"
	if ! grep -qx "Proof-of-work OK: $2" <<< "$out"; then
		echo "::error::--test-pow=$1 did not run solver $2"
		exit 1
	fi
}

# refuse <solver>: the solver must not claim to run on this CPU
refuse() {
	if run_pow "$1" > /dev/null 2>&1; then
		echo "::error::--test-pow=$1 ran, but this CPU should not support it"
		exit 1
	fi
	echo "Refused as expected: $1"
}

# Native solvers this CPU supports, best first, detected without our library
case "$os/$arch" in
	Linux/x86_64)
		if grep -qw sha_ni /proc/cpuinfo; then native="sha-ni portable"; else native="portable"; fi
		;;
	Linux/aarch64)
		if grep -qw sha2 /proc/cpuinfo; then native="armv8 portable"; else native="portable"; fi
		;;
	Darwin/arm64)
		native="armv8 portable"
		;;
	Darwin/x86_64)
		if arch -x86_64 sysctl -n machdep.cpu.leaf7_features 2> /dev/null | grep -qw SHA; then
			native="sha-ni portable"
		else
			native="portable"
		fi
		;;
	*)
		# Windows: no independent detection here, so accept the library's
		native=""
		;;
esac

if [ -z "$native" ]; then
	out="$(run_pow native)"
	echo "$out"
	best="$(sed -n 's/^Proof-of-work OK: //p' <<< "$out")"
	case "$best" in
		sha-ni) native="sha-ni portable" ;;
		portable) native="portable" ;;
		*)
			echo "::error::--test-pow=native ran ${best:-nothing}, expected sha-ni or portable"
			exit 1
			;;
	esac
	echo "::notice::No independent CPU detection on $os/$arch, the library picked $best"
fi

echo "Expecting native solvers: $native"
check native "${native%% *}"
for solver in $native; do
	check "$solver" "$solver"
done
for solver in sha-ni armv8; do
	if ! grep -qw -- "$solver" <<< "$native"; then
		refuse "$solver"
	fi
done
check python python
