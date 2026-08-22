#!/bin/sh
# P13 arm C. Runs ON the measuring VM. Started by measure-on-gce.sh; not useful alone.
#
# **This file must be LF**, and measure-on-gce.sh normalises line endings when it
# builds the tarball. See gce-run.sh's header for the afternoon that bought that.
#
# WHAT THIS ANSWERS, and why gce-run.sh could not.
#
# gce-run.sh measures whatever the service loads from the model repo, which is
# the int8 validator. The fp32 validator has never been published and must not
# be - measuring a format is not a reason to put an ungated graph where a
# deployment could reach it. So the fp32 graph is SHIPPED from the working tree
# and mounted, and `SBR_ARTEFACT_DIR` (service/settings.py) points the service
# at it. Nothing here touches the model repo.
#
# TWO MEASUREMENTS, BOTH PAIRED:
#
#   LATENCY      - both formats, one host, arms alternated cycle by cycle.
#                  `SBR_SERVICE_HOST` is set, so the result is representative
#                  and a gate may be decided on it.
#
#   CONCURRENCY  - the whole container under virtual scanners, once per format,
#                  service pinned to CPUs 0-1 and the client to 2-3. The two
#                  ramps run back to back on the same instance so the comparison
#                  is between formats and not between VMs.
set -eu

IMAGE="${IMAGE:?}"
LEVELS="${LEVELS:-1 2 3 4 5 6 7 8}"
REPEATS="${REPEATS:-3}"
HOLD="${HOLD:-20}"
CYCLES="${CYCLES:-5}"
WORK="${WORK:-/tmp/sbr}"
HOST_LABEL="${HOST_LABEL:-GCE n2-standard-4, service pinned to 2 of 4 vCPU, Intel Cascade Lake, europe-west3-a, docker --cpus 2 --cpuset-cpus 0,1}"
RESULTS="$WORK/results"
FP32_DIR="$WORK/fp32"

mkdir -p "$RESULTS"
# World-writable: the service image drops to its own uid, so /out is read-only
# to it and a PermissionError arrives AFTER the measurement, losing a result
# that was already taken.
chmod 777 "$RESULTS"

echo "### host"
{
  echo "uname: $(uname -a)"
  echo "nproc: $(nproc)"
  grep -m1 'model name' /proc/cpuinfo || true
  echo "--- int8 acceleration is the whole question, so record the flags ---"
  grep -m1 -o 'avx512_vnni\|avx_vnni\|avx512f\|avx2' /proc/cpuinfo || echo "no vnni/avx flags found"
  grep -m1 'flags' /proc/cpuinfo | tr ' ' '\n' | grep -c 'avx512_vnni' || true
} | tee "$RESULTS/host-fp32.txt"

echo "### the fp32 graph shipped from the working tree"
ls -la "$FP32_DIR"

echo "### authenticating to Artifact Registry"
REGISTRY="$(echo "$IMAGE" | cut -d/ -f1)"
if command -v docker-credential-gcr >/dev/null 2>&1; then
  docker-credential-gcr configure-docker --registries="$REGISTRY"
else
  TOKEN="$(curl -s -H 'Metadata-Flavor: Google' \
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
    | tr ',' '\n' | grep access_token | cut -d'"' -f4)"
  echo "$TOKEN" | docker login -u oauth2accesstoken --password-stdin "https://$REGISTRY"
fi

echo "### pulling the service image"
docker pull "$IMAGE"

# --------------------------------------------------------------------------- #
# 1. Latency, both formats, alternated, ON THIS HOST
# --------------------------------------------------------------------------- #
echo "### latency, paired"
docker run --rm --cpuset-cpus 0,1 --network host \
  -e HF_TOKEN="${HF_TOKEN:-}" \
  -e CYCLES="$CYCLES" \
  -e FP32_DIR=/fp32 \
  -e SBR_SERVICE_HOST="GCE n2-standard-4, 2 of 4 vCPU pinned, Intel Cascade Lake, europe-west3-a" \
  -v "$RESULTS":/out -v "$FP32_DIR":/fp32:ro \
  -v "$WORK/gce-latency-paired.py":/gce-latency-paired.py \
  --entrypoint python "$IMAGE" /gce-latency-paired.py

# --------------------------------------------------------------------------- #
# 2. Concurrency, one ramp per format
# --------------------------------------------------------------------------- #
#
# SBR_FORCE_CROPS is what makes "one bin per frame" true rather than a label:
# the client sends smooth noise, a trained validator finds nothing in it, and
# without this the identifier never runs and both ramps measure a
# validator-only frame. gce-run.sh's header records the run that got this wrong.
#
# SBR_ALLOW_UNGATED is required here and is the sanctioned use of that flag:
# neither validator can ship, and a load test is exactly what the flag exists
# for. Nothing about this reaches a public URL.
start_service() {
  fmt="$1"
  docker rm -f sbr >/dev/null 2>&1 || true
  if [ "$fmt" = "fp32" ]; then
    ART="-e SBR_ARTEFACT_DIR=/artefacts -v $FP32_DIR:/artefacts:ro"
  else
    ART=""
  fi
  # shellcheck disable=SC2086
  docker run -d --name sbr \
    --cpus 2 --cpuset-cpus 0,1 \
    -p 8080:8080 \
    -e SBR_ALLOW_UNGATED=1 \
    -e SBR_INTRA_OP_THREADS=2 \
    -e SBR_FORCE_CROPS=1 \
    -e HF_TOKEN="${HF_TOKEN:-}" \
    $ART \
    "$IMAGE" >/dev/null

  for _ in $(seq 1 120); do
    if curl -sf -m 3 http://localhost:8080/health >/dev/null; then break; fi
    sleep 5
  done
  curl -s http://localhost:8080/health > "$RESULTS/health-$fmt.json"

  # ASSERT THE SERVICE IS SERVING THE FORMAT THIS ARM IS ABOUT. Without this the
  # fp32 arm silently falls back to the model repo on any mount problem and
  # produces a second int8 curve labelled fp32 - which is precisely the failure
  # gce-run.sh's header documents for crop counts.
  # Read the verdict with the IMAGE's python, not the host's. Container-Optimized
  # OS is deliberately minimal and ships no python3; the image certainly has one,
  # and using it costs a container start we can afford once per arm.
  got="$(docker run --rm -v "$RESULTS":/out:ro --entrypoint python "$IMAGE" -c     "import json;print(json.load(open('/out/health-$fmt.json'))['artefacts']['validator']['quantised'])"     2>/dev/null || echo UNKNOWN)"
  echo "service up for $fmt; validator quantised=$got"
  if [ "$fmt" = "fp32" ] && [ "$got" != "False" ]; then
    echo "REFUSING: the fp32 arm loaded a quantised validator. The mount did not take."
    exit 1
  fi
  if [ "$fmt" = "int8" ] && [ "$got" != "True" ]; then
    echo "REFUSING: the int8 arm did not load a quantised validator."
    exit 1
  fi
}

for fmt in int8 fp32; do
  echo "--- concurrency, $fmt"
  start_service "$fmt"
  docker run --rm --cpuset-cpus 2,3 --network host \
    -v "$WORK":/lt -v "$RESULTS":/out -w /lt/loadtest \
    python:3.12-slim sh -c "
      pip install -q -r requirements.txt &&
      python run.py --url http://localhost:8080 \
        --levels $LEVELS --hold $HOLD --repeats $REPEATS \
        --bins 1 --label gce-n2-standard-4-$fmt \
        --host '$HOST_LABEL' --representative \
        --out /out/loadtest-1bin-$fmt.json
    " || echo "loadtest for $fmt failed - recorded as an absence, not a zero"
  docker logs sbr > "$RESULTS/service-$fmt.log" 2>&1 || true
done

docker rm -f sbr >/dev/null 2>&1 || true
echo "### done"
ls -la "$RESULTS"
