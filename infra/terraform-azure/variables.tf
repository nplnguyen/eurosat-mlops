variable "subscription_id" {
  description = "Identifiant de l'abonnement Azure (az account show --query id -o tsv)"
  type        = string
}

variable "location" {
  description = "Région Azure"
  type        = string
  default     = "francecentral"
}

variable "vm_size" {
  description = "2 vCPU / 8 Go : compatible avec les quotas des abonnements étudiants"
  type        = string
  default     = "Standard_B2ms"
}

variable "admin_username" {
  type    = string
  default = "azureuser"
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/id_ed25519.pub"
}

variable "ssh_allowed_cidrs" {
  description = "Adresses autorisées en SSH (votre IP en /32 de préférence)"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
