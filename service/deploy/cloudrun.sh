#!/usr/bin/env bash
# Deploy the inference service to Cloud Run.
#
#     service/deploy/cloudrun.sh              # build, then deploy
#     service/deploy/cloudrun.sh --no-build   # deploy the image already there
#
# Read service/deploy/README.md before changing any flag below. Every one of
# them is either a cost control or a correctness control, and the two that look
# most like tuning knobs - --min-instances and --concurrency - are the two that
# decide whether this costs nothing or empties the free tier in a day.
set -euo pipefail

PROJECT="${SBR_PROJECT:-smart-bin-recognition}"
REGION="${SBR_REGION:-europe-west3}"
SERVICE="${SBR_SERVICE:-sbr-detect}"
REPO="${SBR_REPO:-sbr}"
IMAGE="${SBR_IMAGE:-detect}"
TAG="${SBR_TAG:-v1}"

REF="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/${IMAGE}:${TAG}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ "${1:-}" != "--no-build" ]]; then
  echo "building ${REF} on Cloud Build (amd64 - Cloud Run will not run an arm64 image)"
  gcloud builds submit "${ROOT}" \
    --project="${PROJECT}" \
    --region="${REGION}" \
    --config="${ROOT}/service/deploy/cloudbuild.yaml" \
    --substitutions="_REGION=${REGION},_REPO=${REPO},_IMAGE=${IMAGE},_TAG=${TAG}"
fi

echo "deploying ${SERVICE} to ${REGION}"
gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --image="${REF}" \
  \
  `# 2 vCPU is what the entire cost model is arithmetic about (docs/05 § 3).` \
  `# Changing it invalidates every latency number this project has published.` \
  --cpu=2 \
  --memory=2Gi \
  \
  `# THE BILLING MODE, and it is decided by these two together. Scale to zero` \
  `# with no always-allocated CPU means REQUEST-BASED billing: CPU is charged` \
  `# only while a request is in flight, against a free tier of 180 000` \
  `# vCPU-seconds a month. Set --min-instances=1, or add --no-cpu-throttling,` \
  `# and it silently becomes INSTANCE-BASED, where an idle instance bills CPU` \
  `# and memory too - one always-on 2-vCPU instance eats the whole monthly` \
  `# allowance in about twenty-five hours.` \
  --min-instances=0 \
  --max-instances=1 \
  \
  `# One request per instance. The container holds two onnxruntime sessions` \
  `# pinned to both vCPUs; a second concurrent request does not go twice as` \
  `# fast, it halves the speed of the first. With --max-instances=1 this also` \
  `# makes the deployment a demonstrator rather than a capacity - see the` \
  `# README, which says so in those words.` \
  --concurrency=1 \
  --timeout=60s \
  \
  `# PUBLIC BY DEFAULT because the Vercel client calls this cross-origin with no` \
  `# credentials. Set SBR_PUBLIC=0 for a private revision - and then READ THE` \
  `# CHECK BELOW, because the flag alone is not enough.` \
  "$([[ "${SBR_PUBLIC:-1}" == "1" ]] && echo --allow-unauthenticated || echo --no-allow-unauthenticated)" \
  --port=8080 \
  --set-env-vars="SBR_INTRA_OP_THREADS=2,SBR_MAX_CROPS=6,SBR_INFERENCE_SLOTS=1,SBR_ALLOWED_ORIGINS=${SBR_ALLOWED_ORIGINS:-*}" \
  --labels="project=smart-bin-recognition,component=inference"

URL="$(gcloud run services describe "${SERVICE}" --project="${PROJECT}" --region="${REGION}" --format='value(status.url)')"

# WHO CAN ACTUALLY REACH IT, asked of the internet rather than of the flag.
#
# Learned the hard way on 2026-08-16. A first deploy with --allow-unauthenticated
# grants allUsers at the service level. A LATER deploy with
# --no-allow-unauthenticated does not revoke it: the revision came up private by
# every reading gcloud offered - `get-iam-policy` returned no bindings at all -
# and an anonymous curl still got 200 and a full /health body. The only check
# worth trusting is the request itself.
echo
echo "verifying who can reach it"
CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "${URL}/health" || echo 000)"
if [[ "${SBR_PUBLIC:-1}" == "1" ]]; then
  [[ "${CODE}" == "200" ]] \
    && echo "  public, as intended (HTTP ${CODE})" \
    || echo "  WARNING: meant to be public but an anonymous request got HTTP ${CODE}"
else
  if [[ "${CODE}" == "200" ]]; then
    echo "  DANGER: this was meant to be PRIVATE and an anonymous request got HTTP 200."
    echo "  Revoke it now, and do not trust the flag:"
    echo "    gcloud run services remove-iam-policy-binding ${SERVICE} \\"
    echo "      --project=${PROJECT} --region=${REGION} --member=allUsers --role=roles/run.invoker"
    echo "  If that reports the binding is not found and it is still reachable, delete the service."
    exit 1
  fi
  echo "  private, as intended (HTTP ${CODE})"
fi

echo
echo "service: ${URL}"
echo "health:  ${URL}/health"
echo
echo "Point the client at it with:  VITE_DETECT_URL=${URL}/detect"
echo
echo "It will refuse to serve an artefact whose sidecar does not say may_ship,"
echo "which today means it refuses to start unless SBR_ALLOW_UNGATED is set."
echo "That is the gate working, not a deployment failure."
