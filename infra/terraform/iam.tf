resource "google_service_account" "backend" {
  account_id   = "shopper-backend"
  display_name = "Shopper backend (Cloud Run)"
}

resource "google_service_account" "frontend" {
  account_id   = "shopper-frontend"
  display_name = "Shopper frontend (Cloud Run)"
}

resource "google_secret_manager_secret_iam_member" "backend_db_password" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.backend.member
}

# Only the frontend may invoke the backend.
resource "google_cloud_run_v2_service_iam_member" "frontend_invokes_backend" {
  name     = google_cloud_run_v2_service.backend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = google_service_account.frontend.member
}

# IAP fronts the web app: its service agent invokes the frontend,
# and only the listed users may pass through IAP.
resource "google_project_service_identity" "iap" {
  provider = google-beta
  service  = "iap.googleapis.com"
}

resource "google_cloud_run_v2_service_iam_member" "iap_invokes_frontend" {
  name     = google_cloud_run_v2_service.frontend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = google_project_service_identity.iap.member
}

resource "google_iap_web_cloud_run_service_iam_member" "app_users" {
  for_each               = toset(var.app_users)
  project                = var.project_id
  location               = var.region
  cloud_run_service_name = google_cloud_run_v2_service.frontend.name
  role                   = "roles/iap.httpsResourceAccessor"
  member                 = each.value
}
