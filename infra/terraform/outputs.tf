output "app_url" {
  description = "Web app URL (behind IAP)."
  value       = google_cloud_run_v2_service.frontend.uri
}

output "backend_url" {
  description = "Internal-only backend URL."
  value       = google_cloud_run_v2_service.backend.uri
}

output "image_repo" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "db_private_ip" {
  value = google_sql_database_instance.main.private_ip_address
}
