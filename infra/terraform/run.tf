resource "google_cloud_run_v2_service" "backend" {
  name     = "shopper-backend"
  location = var.region

  # Reachable only from inside the VPC (the frontend) and Google services such
  # as Cloud Scheduler; never from the public internet.
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false

  template {
    service_account = google_service_account.backend.email

    # One instance: the demo clock and the shopping-run lock assume a single backend.
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    # Claude calls in a shopping run can take a while.
    timeout = "120s"

    vpc_access {
      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.run.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.backend_image

      env {
        name  = "DB_HOST"
        value = google_sql_database_instance.main.private_ip_address
      }
      env {
        name  = "DB_NAME"
        value = google_sql_database.app.name
      }
      env {
        name  = "DB_USER"
        value = google_sql_user.app.name
      }
      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }

      dynamic "env" {
        for_each = local.use_claude ? [1] : []
        content {
          name = "ANTHROPIC_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.anthropic_api_key[0].secret_id
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        http_get {
          path = "/api/health"
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_version.db_password,
    google_secret_manager_secret_iam_member.backend_db_password,
    google_secret_manager_secret_version.anthropic_api_key,
    google_secret_manager_secret_iam_member.backend_anthropic_api_key,
  ]
}

resource "google_cloud_run_v2_service" "frontend" {
  name     = "shopper-frontend"
  location = var.region

  ingress             = "INGRESS_TRAFFIC_ALL"
  iap_enabled         = true
  deletion_protection = false

  template {
    service_account = google_service_account.frontend.email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    # Route all egress through the VPC so calls to the backend's run.app URL
    # are treated as internal.
    vpc_access {
      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.run.id
      }
      egress = "ALL_TRAFFIC"
    }

    containers {
      image = var.frontend_image

      env {
        name  = "BACKEND_URL"
        value = google_cloud_run_v2_service.backend.uri
      }
      env {
        name  = "USE_ID_TOKEN"
        value = "true"
      }
    }
  }
}
