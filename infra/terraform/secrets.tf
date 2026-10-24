# Optional Claude API key for the shopping agent.
locals {
  use_claude = var.anthropic_api_key != ""
}

resource "google_secret_manager_secret" "anthropic_api_key" {
  count     = local.use_claude ? 1 : 0
  secret_id = "shopper-anthropic-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.this]
}

resource "google_secret_manager_secret_version" "anthropic_api_key" {
  count       = local.use_claude ? 1 : 0
  secret      = google_secret_manager_secret.anthropic_api_key[0].id
  secret_data = var.anthropic_api_key
}

resource "google_secret_manager_secret_iam_member" "backend_anthropic_api_key" {
  count     = local.use_claude ? 1 : 0
  secret_id = google_secret_manager_secret.anthropic_api_key[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.backend.member
}
