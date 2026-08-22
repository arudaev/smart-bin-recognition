#!/usr/bin/env bash
# Measure latency and concurrency on a controlled x86 host, then destroy it.
#
#     service/deploy/measure-on-gce.sh
#
# WHY THIS EXISTS. docs/12 P8 established that the development laptop cannot
# hold a concurrency figure still: the identical baseline measured 7 concurrent
# scanners at 22:30 and 4 at 23:48, because host CPU sat at ~50 % with the
# tooling on it and `docker run --cpus 2` is a cgroup *ceiling, not a floor*.
# Every absolute number this project has published about concurrency came from
# that host and none of them is admissible.
#
# WHY FOUR vCPU FOR A TWO-vCPU MEASUREMENT. The service gets exactly two, pinned
# with `--cpuset-cpus 0,1`, which is what the cost model is arithmetic about.
# The other two exist so the **load-test client** has somewhere to run that is
# not the service's cores. The old protocol worked because the Snapdragon had
# twelve cores and the client had ten free ones; putting the client on the
# service's two would reproduce P8's contention deliberately.
#
# WHY THE CPU PLATFORM IS PINNED. E2 picks its platform dynamically and N2
# without `--min-cpu-platform` may land on Cascade Lake or Ice Lake. Two runs on
# different silicon are not comparable, and P9-versus-P10 measured the identical
# graph 31 % apart for exactly that reason.
#
# COST. n2-standard-4 in europe-west3 is USD 0.250248/hour on demand
# (4 x 0.040730 CPU + 16 GiB x 0.005458 RAM, Cloud Billing Catalog, 2026-08-21)
# plus ~USD 0.0033/h for the boot disk. THE VM IS DELETED ON EVERY EXIT PATH,
# including failure and Ctrl-C - see the trap.
set -euo pipefail

PROJECT="${PROJECT:-smart-bin-recognition}"
ZONE="${ZONE:-europe-west3-a}"
VM="${VM:-sbr-bench-$(date +%s)}"
MACHINE="${MACHINE:-n2-standard-4}"
PLATFORM="${PLATFORM:-Intel Cascade Lake}"
IMAGE="${IMAGE:-europe-west3-docker.pkg.dev/smart-bin-recognition/sbr/detect@sha256:7399db5724405430752e2b1d82f31159b83c8405e2a69154aa110e63e067fa8a}"
OUT="${OUT:-artifacts/gce}"
LEVELS="${LEVELS:-1 2 3 4 5 6 7 8 9 10 11 12 13 14}"
REPEATS="${REPEATS:-3}"
HOLD="${HOLD:-20}"

# WHICH MEASUREMENT. `gate` is the phase-2 gate and is what ran on 2026-08-21:
# whatever the service loads from the model repo, at 1 and 6 bins per frame.
# `fp32` is docs/12 P13: the validator in BOTH formats on one instance, arms
# alternated, with the fp32 graph shipped from the working tree because it is
# not published and must not be. They are different questions, they write
# different files, and neither path can silently become the other.
ARM="${ARM:-gate}"
CYCLES="${CYCLES:-5}"
FP32_SRC="${FP32_SRC:-artifacts/local}"

mkdir -p "$OUT"

# The VM is billed by the second and this is the only thing standing between a
# failed run and a box nobody remembers. It fires on error and on interrupt.
cleanup() {
  echo ">>> deleting $VM (this runs on every exit path)"
  gcloud compute instances delete "$VM" --zone "$ZONE" --project "$PROJECT" --quiet || true
}
trap cleanup EXIT INT TERM

echo ">>> creating $VM ($MACHINE, $PLATFORM, $ZONE)"
gcloud compute instances create "$VM" \
  --project "$PROJECT" --zone "$ZONE" --machine-type "$MACHINE" \
  --min-cpu-platform "$PLATFORM" \
  --image-family cos-stable --image-project cos-cloud \
  --boot-disk-size 20GB --boot-disk-type pd-balanced \
  --scopes "https://www.googleapis.com/auth/cloud-platform"

echo ">>> waiting for ssh"
until gcloud compute ssh "$VM" --zone "$ZONE" --project "$PROJECT" \
        --command "true" --quiet 2>/dev/null; do sleep 5; done

# ONE TARBALL, not a recursive copy.
#
# Two things bite here and both look like permissions problems. Container-
# Optimized OS expands no `~` in an scp target and has no home directory until
# something makes one, so `~/loadtest` fails with "unable to create directory".
# And the Windows `pscp` that gcloud shells out to will not CREATE a recursive
# destination - `--recurse src VM:/tmp/sbr/loadtest` fails with "unable to open"
# unless that directory already exists. Sending a single file sidesteps both.
REMOTE=/tmp/sbr
STAGE="$(mktemp -d)"
TARBALL="$STAGE/harness.tar.gz"

# STRIP CR BEFORE SHIPPING. `.gitattributes` says `*.sh text eol=lf` and its
# comment even predicts this failure, but that governs what git checks OUT - a
# file written on Windows and never round-tripped through a checkout is still
# CRLF in the working tree. It ships, and the remote shell then reports
# `set: pipefail: invalid option name` and `$'\r': command not found`, neither
# of which mentions line endings. Normalising here makes the harness immune to
# the state of the working copy rather than dependent on it.
cp -r service/loadtest "$STAGE/loadtest"
cp service/deploy/gce-run.sh service/deploy/gce-latency.py "$STAGE/"
# `run.py` resolves `wire` from ITS PARENT directory - the loadtest is a client
# of the same wire the browser speaks, and the byte-level contract is the point.
# Shipping loadtest/ alone gives ModuleNotFoundError: No module named 'wire'.
cp service/wire.py "$STAGE/"
rm -rf "$STAGE/loadtest/__pycache__"

# THE fp32 GRAPH TRAVELS IN THE TARBALL and is never published. SBR_ARTEFACT_DIR
# (service/settings.py) is what the service reads it through. Publishing an
# ungated graph to the model repo so a benchmark could reach it would leave it
# one environment variable away from a deployment, which is not a trade worth
# making for a measurement.
if [ "$ARM" = "fp32" ]; then
  echo ">>> staging the fp32 validator from $FP32_SRC"
  mkdir -p "$STAGE/fp32"
  cp "$FP32_SRC/validator-v1.onnx" "$FP32_SRC/validator-v1.json" "$STAGE/fp32/"
  # The identifier travels with it: SBR_ARTEFACT_DIR is all-or-nothing, so a
  # directory holding only a validator makes the service fail to find role B
  # rather than fall back to the Hub for it.
  cp "$FP32_SRC/identifier-v1.onnx" "$FP32_SRC/identifier-v1.json" "$STAGE/fp32/"
  python -c "import json,sys; raise SystemExit(0 if json.load(open(sys.argv[1])).get('quantised') is False else 1)" "$STAGE/fp32/validator-v1.json" || {
    echo "REFUSING: $FP32_SRC/validator-v1.json does not say quantised: false"; exit 1; }
  cp service/deploy/gce-fp32.sh service/deploy/gce-latency-paired.py "$STAGE/"
fi
find "$STAGE" -type f -name '*.sh' -exec sed -i 's/\r$//' {} +
find "$STAGE" -type f -name '*.py' -exec sed -i 's/\r$//' {} +
# `if`, not `[ ... ] && EXTRA=...`. This script runs under `set -e`, and a bare
# test that evaluates false IS a failing command at statement level - so the
# one-liner form would abort the default arm rather than skip the assignment.
EXTRA=""
if [ "$ARM" = "fp32" ]; then
  EXTRA="fp32 gce-fp32.sh gce-latency-paired.py"
fi
# shellcheck disable=SC2086
tar -czf "$TARBALL" -C "$STAGE" loadtest gce-run.sh gce-latency.py wire.py $EXTRA

echo ">>> copying the harness to $REMOTE"
gcloud compute ssh "$VM" --zone "$ZONE" --project "$PROJECT" --quiet \
  --command "mkdir -p $REMOTE/results"
gcloud compute scp "$TARBALL" "$VM":"$REMOTE/harness.tar.gz" \
  --zone "$ZONE" --project "$PROJECT" --quiet
gcloud compute ssh "$VM" --zone "$ZONE" --project "$PROJECT" --quiet \
  --command "cd $REMOTE && tar -xzf harness.tar.gz && \
             mv -f deploy/gce-run.sh deploy/gce-latency.py . 2>/dev/null; ls -la $REMOTE"

# `bash <script>` rather than executing it. /tmp is mounted NOEXEC on
# Container-Optimized OS, so the file is -rwxr-xr-x and still refuses to run.
# The error is "Permission denied", which sends people to chmod for an hour.
echo ">>> running the '$ARM' arm"
REMOTE_SCRIPT=gce-run.sh
if [ "$ARM" = "fp32" ]; then
  REMOTE_SCRIPT=gce-fp32.sh
fi
gcloud compute ssh "$VM" --zone "$ZONE" --project "$PROJECT" --quiet --command \
  "HF_TOKEN='${HF_TOKEN:-}' IMAGE='$IMAGE' \
   LEVELS='$LEVELS' REPEATS='$REPEATS' HOLD='$HOLD' WORK='$REMOTE' \
   CYCLES='$CYCLES' \
   bash $REMOTE/$REMOTE_SCRIPT"

echo ">>> collecting"
gcloud compute ssh "$VM" --zone "$ZONE" --project "$PROJECT" --quiet \
  --command "cd $REMOTE && tar -czf results.tar.gz results"
gcloud compute scp "$VM":"$REMOTE/results.tar.gz" "$OUT/results.tar.gz" \
  --zone "$ZONE" --project "$PROJECT" --quiet || true
tar -xzf "$OUT/results.tar.gz" -C "$OUT" 2>/dev/null || true

echo ">>> done; $OUT holds the reports and the trap will delete the VM"
