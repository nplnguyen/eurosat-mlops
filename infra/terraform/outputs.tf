output "public_ip" {
  description = "IP publique (élastique) de la VM"
  value       = aws_eip.eurosat.public_ip
}

output "ssh_command" {
  value = "ssh ${var.deploy_user}@${aws_eip.eurosat.public_ip}"
}

output "deploy_command" {
  value = "./scripts/deploy.sh ${var.deploy_user}@${aws_eip.eurosat.public_ip}"
}

output "admin_tunnel" {
  description = "Accès à MLflow / Grafana / Prometheus (non exposés publiquement)"
  value       = "ssh -L 5001:localhost:5000 -L 3000:localhost:3000 -L 9090:localhost:9090 ${var.deploy_user}@${aws_eip.eurosat.public_ip}"
}
