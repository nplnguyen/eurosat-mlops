variable "region" {
  description = "Région AWS (Paris par défaut)"
  type        = string
  default     = "eu-west-3"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "instance_type" {
  description = "4 vCPU / 16 Go : suffisant pour 3 réplicas ONNX INT8 + monitoring"
  type        = string
  default     = "t3.xlarge"
}

variable "disk_size_gb" {
  type    = number
  default = 60
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/id_ed25519.pub"
}

variable "ssh_allowed_cidrs" {
  description = "CIDR autorisés en SSH (IP du binôme + runners GitHub si CD)"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "deploy_user" {
  type    = string
  default = "ubuntu"
}
