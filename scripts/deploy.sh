#!/usr/bin/env bash
# Déploiement sur une VM existante en une commande :
#   ./scripts/deploy.sh <user@host> [image_tag]
#
# Pré-requis sur la VM : Docker + plugin compose (installés par le cloud-init
# Terraform). Les images sont tirées depuis le registre (GHCR) : la VM ne
# compile rien. Le fichier .env de production n'est jamais versionné.
set -euo pipefail

TARGET="${1:?usage: deploy.sh user@host [image_tag]}"
TAG="${2:-latest}"
REMOTE_DIR="/opt/eurosat"
ENV_FILE="${ENV_FILE:-.env.prod}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

[[ -f "$ENV_FILE" ]] || { echo "Fichier $ENV_FILE manquant"; exit 1; }

echo ">> Copie des fichiers de configuration vers $TARGET:$REMOTE_DIR"
ssh "$TARGET" "sudo mkdir -p $REMOTE_DIR && sudo chown \$(id -u):\$(id -g) $REMOTE_DIR"
rsync -az --delete --relative \
  docker-compose.yml docker-compose.prod.yml gateway/ monitoring/ postgres/ \
  "$TARGET:$REMOTE_DIR/"
scp -q "$ENV_FILE" "$TARGET:$REMOTE_DIR/.env"
ssh "$TARGET" "sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=$TAG/' $REMOTE_DIR/.env"

echo ">> Pull des images ($TAG) et redémarrage progressif"
ssh "$TARGET" "cd $REMOTE_DIR && $COMPOSE pull -q && $COMPOSE up -d --remove-orphans && docker image prune -f >/dev/null"

echo ">> Smoke test"
HOST="${TARGET#*@}"
for i in $(seq 1 30); do
  if curl -fs "http://$HOST/api/health/ready" >/dev/null; then
    echo "Déploiement OK : http://$HOST  (API : http://$HOST/api/docs)"
    exit 0
  fi
  sleep 10
done
echo "Le service n'est pas prêt après 5 minutes" >&2
ssh "$TARGET" "cd $REMOTE_DIR && $COMPOSE ps && $COMPOSE logs --tail=50 api-stable" >&2
exit 1
