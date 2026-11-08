# Provisionnement de la VM de production sur AWS (EC2).
#
#   cd infra/terraform
#   terraform init
#   cp terraform.tfvars.example terraform.tfvars   # puis adapter
#   terraform apply
#
# La VM est livrée avec Docker et le plugin compose (cloud-init) : il ne reste
# qu'à lancer ./scripts/deploy.sh (ou la pipeline CD).

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
  # Backend distant recommandé en binôme pour partager l'état :
  # backend "s3" {
  #   bucket = "eurosat-tfstate"
  #   key    = "prod/terraform.tfstate"
  #   region = "eu-west-3"
  # }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project   = "eurosat-mlops"
      ManagedBy = "terraform"
      Env       = var.environment
    }
  }
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
}

data "aws_vpc" "default" {
  default = true
}

resource "aws_key_pair" "deployer" {
  key_name   = "eurosat-${var.environment}"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

resource "aws_security_group" "eurosat" {
  name        = "eurosat-${var.environment}"
  description = "EuroSAT MLOps : HTTP public, SSH restreint"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP (passerelle nginx)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH (administrateurs + runner CD)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.ssh_allowed_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "eurosat" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.deployer.key_name
  vpc_security_group_ids = [aws_security_group.eurosat.id]

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    deploy_user = var.deploy_user
  })

  root_block_device {
    volume_size = var.disk_size_gb
    volume_type = "gp3"
    encrypted   = true
  }

  metadata_options {
    http_tokens = "required" # IMDSv2 uniquement
  }

  tags = { Name = "eurosat-${var.environment}" }
}

resource "aws_eip" "eurosat" {
  instance = aws_instance.eurosat.id
  domain   = "vpc"
}
