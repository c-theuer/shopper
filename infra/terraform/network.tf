# Private network: Cloud SQL has no public IP, and the frontend reaches the
# internal-only backend through Direct VPC egress.

resource "google_compute_network" "main" {
  name                    = "shopper-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.this]
}

resource "google_compute_subnetwork" "run" {
  name          = "shopper-run-${var.region}"
  network       = google_compute_network.main.id
  region        = var.region
  ip_cidr_range = "10.10.0.0/24"

  # Required so calls to *.run.app from the VPC count as internal traffic.
  private_ip_google_access = true
}

# Private Services Access range for Cloud SQL.
resource "google_compute_global_address" "sql_psa" {
  name          = "shopper-sql-psa"
  network       = google_compute_network.main.id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
}

resource "google_service_networking_connection" "sql" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.sql_psa.name]
}
