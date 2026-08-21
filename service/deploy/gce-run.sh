#!/bin/sh
# Runs ON the measuring VM. Started by measure-on-gce.sh; not useful alone.
#
# **This file must be LF, and `.gitattributes` says so** (`*.sh text eol=lf`),
# with a comment that predicts the exact failure. A CRLF working copy still got
# tarred up and shipped here anyway, because that attribute governs what git
# checks OUT and a file written on Windows never round-tripped through a
# checkout. The errors pointed everywhere except at line endings: the shell
# read the trailing carriage return as part of the last word on each line, so
# `set -eu` became an invalid option and every other line became a command
# named after a control character.
#
# An earlier version of this comment blamed Container-Optimized OS for not
# implementing `pipefail`. That was wrong; the shell is fine.
# `measure-on-gce.sh` now normalises line endings when it builds the tarball,
# so the state of the working copy cannot resurrect this.
#
# It stays POSIX `sh` anyway, which costs nothing and is one less thing to be
# wrong about on a minimal image.
#
# Two measurements, and they answer different halves of the phase-2 gate:
#
#   LATENCY     - each graph on its own, onnxruntime pinned to two threads.
#                 `SBR_SERVICE_HOST` is set, so `sbr.bench.hardware()` reports
#                 `representative: true` and `gate.py` will decide on it. That
#                 is a deliberate act: it says this box counts as the service.
#
#   CONCURRENCY - the whole container under virtual scanners, service pinned to
#                 CPUs 0-1 and the client to 2-3, so the client cannot steal the
#                 cores the number is about.
set -eu

IMAGE="${IMAGE:?}"
LEVELS="${LEVELS:-1 2 3 4 5 6 7 8 9 10 11 12 13 14}"
REPEATS="${REPEATS:-3}"
HOLD="${HOLD:-20}"
WORK="${WORK:-/tmp/sbr}"
# Named once and passed to both measurements, because a figure without its
# hardware beside it is the kind of number AGENTS.md forbids shipping - and
# `run.py` refuses `--out` without `--host` for exactly that reason.
HOST_LABEL="${HOST_LABEL:-GCE n2-standard-4, service pinned to 2 of 4 vCPU, Intel Cascade Lake, europe-west3-a, docker --cpus 2 --cpuset-cpus 0,1}"
RESULTS="$WORK/results"
mkdir -p "$RESULTS"
# World-writable because the containers that write here do not run as this
# user: the service image drops to its own uid, so /out is read-only to it and
# `PermissionError: /out/latency.json` arrives AFTER the measurement, losing a
# result that was already taken.
chmod 777 "$RESULTS"

echo "### host"
{
  echo "uname: $(uname -a)"
  echo "nproc: $(nproc)"
  grep -m1 'model name' /proc/cpuinfo || true
} | tee "$RESULTS/host.txt"

# Artifact Registry needs a credential. The VM was created with the
# cloud-platform scope, so the metadata server can mint one - better than
# shipping a key here, and the reason the instance has a service account at
# all. Without this the pull fails with "denied: Unauthenticated request",
# which reads like the image is missing rather than like an auth problem.
#
# `docker-credential-gcr` is preinstalled on Container-Optimized OS and is the
# supported path; the raw metadata token is the fallback for an image that
# lacks it.
echo "### authenticating to Artifact Registry"
REGISTRY="$(echo "$IMAGE" | cut -d/ -f1)"
if command -v docker-credential-gcr >/dev/null 2>&1; then
  docker-credential-gcr configure-docker --registries="$REGISTRY"
  echo "configured docker-credential-gcr for $REGISTRY"
else
  TOKEN="$(curl -s -H 'Metadata-Flavor: Google'     "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"     | tr ',' '
' | grep access_token | cut -d'"' -f4)"
  echo "metadata token length: ${#TOKEN}"
  echo "$TOKEN" | docker login -u oauth2accesstoken --password-stdin "https://$REGISTRY"
fi

echo "### pulling the service image"
docker pull "$IMAGE"

echo "### starting the service on CPUs 0-1"
docker rm -f sbr >/dev/null 2>&1 || true
docker run -d --name sbr \
  --cpus 2 --cpuset-cpus 0,1 \
  -p 8080:8080 \
  -e SBR_ALLOW_UNGATED=1 \
  -e SBR_INTRA_OP_THREADS=2 \
  -e HF_TOKEN="${HF_TOKEN:-}" \
  "$IMAGE"

echo "### waiting for health"
for _ in $(seq 1 120); do
  if curl -sf -m 3 http://localhost:8080/health >/dev/null; then break; fi
  sleep 5
done
curl -s http://localhost:8080/health > "$RESULTS/health.json"
echo "service up"

# --------------------------------------------------------------------------- #
# 1. Latency, per graph, ON THIS HOST
# --------------------------------------------------------------------------- #
echo "### latency"
docker run --rm --cpuset-cpus 0,1 --network host   -e HF_TOKEN="${HF_TOKEN:-}"   -e SBR_SERVICE_HOST="GCE n2-standard-4, 2 of 4 vCPU pinned, Intel Cascade Lake, europe-west3-a"   -v "$RESULTS":/out -v "$WORK/gce-latency.py":/gce-latency.py   --entrypoint python "$IMAGE" /gce-latency.py

# --------------------------------------------------------------------------- #
# 2. Concurrency, the whole container, client on the OTHER two cores
# --------------------------------------------------------------------------- #
# The WHOLE work directory is mounted, not just loadtest/. `run.py` resolves
# `wire` from its own PARENT - the load test speaks the same byte-level wire the
# browser does, which is the point of it - so mounting the client alone puts
# run.py at /lt/run.py, makes its parent `/`, and gives
# "ModuleNotFoundError: No module named 'wire'".
echo "### concurrency"
for bins in 1 6; do
  echo "--- $bins bin(s) per frame"
  docker run --rm --cpuset-cpus 2,3 --network host \
    -v "$WORK":/lt -v "$RESULTS":/out -w /lt/loadtest \
    python:3.12-slim sh -c "
      pip install -q -r requirements.txt &&
      python run.py --url http://localhost:8080 \
        --levels $LEVELS --hold $HOLD --repeats $REPEATS \
        --bins $bins --label gce-n2-standard-4 \
        --host '$HOST_LABEL' --representative \
        --out /out/loadtest-${bins}bin.json
    " || echo "loadtest at $bins bins failed - recorded as an absence, not a zero"
done

docker logs sbr > "$RESULTS/service.log" 2>&1 || true
docker rm -f sbr >/dev/null 2>&1 || true
echo "### done"
ls -la "$RESULTS"
