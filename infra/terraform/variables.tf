variable "project_id" {
  description = "GCP project ID to deploy into."
  type        = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "app_users" {
  description = "Principals allowed through IAP to the web app, e.g. [\"user:you@example.com\"]."
  type        = list(string)
}

variable "backend_image" {
  description = "Full Artifact Registry image reference for the backend. Set by scripts/deploy.sh."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "frontend_image" {
  description = "Full Artifact Registry image reference for the frontend. Set by scripts/deploy.sh."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "db_tier" {
  description = "Cloud SQL machine tier. db-f1-micro is fine for a single-user pilot."
  type        = string
  default     = "db-f1-micro"
}

variable "db_deletion_protection" {
  type    = bool
  default = true
}

variable "anthropic_api_key" {
  description = "Optional Claude API key. Leave empty to run the agent on its keyword-rules fallback."
  type        = string
  default     = ""
  sensitive   = true
}
