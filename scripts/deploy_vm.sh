#!/usr/bin/env bash
# Déploiement en une commande sur une VM Ubuntu (créée par Terraform ou à la main) :
#   ./scripts/deploy_vm.sh azureuser@IP
# Construit les images directement sur la VM (aucun registre nécessaire).
set -euo pipefail
TARGET="${1:?usage: deploy_vm.sh user@ip}"
DIR=/opt/eurosat
echo ">> Attente de la fin de l'initialisation de la VM (cloud-init)"
ssh -o StrictHostKeyChecking=accept-new "$TARGET" 'cloud-init status --wait >/dev/null 2>&1 || true'
echo ">> Installation de Docker si nécessaire"
ssh "$TARGET" 'command -v docker >/dev/null || (curl -fsSL https://get.docker.com | sudo sh)'
ssh "$TARGET" "sudo mkdir -p $DIR && sudo chown \$(id -u) $DIR"
echo ">> Copie du projet"
rsync -az --delete --exclude .git --exclude '.venv*' --exclude 'loadtest/images' --exclude '__pycache__' \
  --exclude 'infra/terraform*/.terraform' --exclude '*.tfstate*' ./ "$TARGET:$DIR/"
[ -f .env.vm ] || python3 scripts/make_env.py .env.vm
scp -q .env.vm "$TARGET:$DIR/.env"
echo ">> Construction et lancement (10-15 min la première fois)"
ssh "$TARGET" "cd $DIR && sudo docker compose up -d --build"
HOST="${TARGET#*@}"
echo ">> Attente du modèle (le premier entraînement prend 15-30 min sur la VM)"
for i in $(seq 1 120); do
  if curl -fs "http://$HOST/api/health/ready" >/dev/null; then
    echo "Déploiement OK : http://$HOST  (API : http://$HOST/api/docs)"
    exit 0
  fi
  sleep 30
done
echo "Pas encore prêt. Logs : ssh $TARGET 'cd $DIR && sudo docker compose logs --tail 30 trainer'"
exit 1
