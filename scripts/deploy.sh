#!/usr/bin/env bash
# Build both images, push them to Artifact Registry, and apply Terraform.
# Usage: PROJECT_ID=my-project scripts/deploy.sh            (tag defaults to a UTC timestamp)
#        PROJECT_ID=my-project TAG=v1 scripts/deploy.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to your GCP project ID, e.g. PROJECT_ID=my-project scripts/deploy.sh}"
REGION="${REGION:-us-central1}"
TAG="${TAG:-$(date -u +%Y%m%d-%H%M%S)}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="$ROOT/infra/terraform"
REPO="$REGION-docker.pkg.dev/$PROJECT_ID/shopper"

cd "$TF_DIR"
terraform init -input=false -backend-config="bucket=$PROJECT_ID-tfstate"

# First run: the registry must exist before images can be pushed.
terraform apply -input=false -auto-approve \
  -var "project_id=$PROJECT_ID" \
  -target=google_project_service.this \
  -target=google_artifact_registry_repository.images

gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

# Cloud Run runs linux/amd64.
docker buildx build --platform linux/amd64 -t "$REPO/backend:$TAG" --push "$ROOT/backend"
docker buildx build --platform linux/amd64 -t "$REPO/frontend:$TAG" --push "$ROOT/frontend"

terraform apply -input=false \
  -var "project_id=$PROJECT_ID" \
  -var "backend_image=$REPO/backend:$TAG" \
  -var "frontend_image=$REPO/frontend:$TAG"
