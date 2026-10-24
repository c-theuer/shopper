terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 8.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Create the bucket once before `terraform init` (see infra/README.md).
  backend "gcs" {
    bucket = "shopper-511919-tfstate"
    prefix = "shopper"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Only needed for google_project_service_identity (IAP service agent).
provider "google-beta" {
  project = var.project_id
  region  = var.region
}
