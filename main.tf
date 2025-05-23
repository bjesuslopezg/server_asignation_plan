terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "inmem" {}
}

provider "aws" {
  region = "us-east-1"
}

module "pricing" {
  source = "terraform-aws-modules/pricing/aws//modules/pricing"

  resources = {

    "aws_instance.my_servers#9" = {
      instanceType = "i7i.4xlarge"
      location     = "us-east-1"
    }

    "aws_ebs_volume.my_disks#9" = {
      location     = "us-east-1"
      _quantity              = 2048
      volumeApiName = "gp3"
    }
  }
}

# ────────── Outputs ──────────
output "precio_por_hora" {
  value = module.pricing.total_price_per_hour
}

output "precio_total_mensual" {
  value = tonumber(module.pricing.total_price_per_hour) * 730
}