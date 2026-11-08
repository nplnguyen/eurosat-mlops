SHELL := /bin/bash
COMPOSE      := docker compose
COMPOSE_PROD := docker compose -f docker-compose.yml -f docker-compose.prod.yml
API_URL      ?= http://localhost/api
HOST         ?=
USERS        ?= 50
DURATION     ?= 3m

.PHONY: help env up down logs ps train promote rollback status create-user test lint \
        sample-images loadtest drift-demo scale tf-init tf-apply tf-destroy deploy k8s-apply

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- Niveau 0
env: ## Génère .env avec des secrets aléatoires
	@python3 scripts/make_env.py .env || python scripts/make_env.py .env

up: env ## Lance TOUT le système en local (une commande)
	$(COMPOSE) up -d --build
	@echo "UI : http://localhost   API : $(API_URL)/docs   MLflow : http://localhost:5001   Grafana : http://localhost:3000"

down: ## Arrête le système
	$(COMPOSE) down

logs: ## Logs de l'API et du trainer
	$(COMPOSE) logs -f api-stable api-canary trainer

ps:
	$(COMPOSE) ps

# ----------------------------------------------------------- Cycle de vie
train: ## Entraînement complet (MLflow) -> nouvelle version "challenger"
	$(COMPOSE) run --rm trainer python -m training.train --arch $${ARCH:-resnet18} --epochs $${EPOCHS:-10}

status: ## Versions et alias du Model Registry
	$(COMPOSE) run --rm trainer python -m training.promote status

promote: ## challenger -> champion (fin du canary)
	$(COMPOSE) run --rm trainer python -m training.promote promote

rollback: ## Revient au champion précédent
	$(COMPOSE) run --rm trainer python -m training.promote rollback

create-user: ## make create-user NAME=alice [QUOTA=120]
	$(COMPOSE) exec api-stable python -m app.cli create-user $(NAME) $(if $(QUOTA),--quota $(QUOTA))

scale: ## Scaling horizontal local : make scale N=3
	$(COMPOSE) up -d --no-deps --scale api-stable=$${N:-3} api-stable
	$(COMPOSE) restart gateway

# ------------------------------------------------------------------ Qualité
test: ## Tests unitaires et d'intégration
	pytest -q

lint:
	ruff check api training tests scripts loadtest ui

# ------------------------------------------------------- Charge & drift
sample-images: ## Copie un échantillon EuroSAT dans loadtest/images
	$(COMPOSE) run --rm -v "$(CURDIR)/loadtest:/workspace/loadtest" -v "$(CURDIR)/scripts:/workspace/scripts" \
	  trainer python scripts/sample_images.py --data-dir /data

loadtest: ## make loadtest API_URL=http://IP/api EUROSAT_API_KEY=... USERS=100
	mkdir -p loadtest/results
	locust -f loadtest/locustfile.py --host $(API_URL) --headless -u $(USERS) -r 10 -t $(DURATION) \
	  --csv loadtest/results/u$(USERS) --html loadtest/results/u$(USERS).html

drift-demo: ## make drift-demo KEY=eus_... P=clouds
	python scripts/simulate_drift.py --url $(API_URL) --key $(KEY) --perturbation $${P:-clouds}

# -------------------------------------------------------- Niveaux 1 et 2
tf-init:
	cd infra/terraform && terraform init

tf-apply: ## Crée la VM de production (AWS)
	cd infra/terraform && terraform apply

tf-destroy:
	cd infra/terraform && terraform destroy

deploy: ## make deploy HOST=ubuntu@IP [TAG=v1.0.0]
	./scripts/deploy.sh $(HOST) $${TAG:-latest}

# --------------------------------------------------------------- Niveau 3
k8s-apply: ## Déploiement Kubernetes (ingress-nginx requis)
	kubectl apply -k k8s/
