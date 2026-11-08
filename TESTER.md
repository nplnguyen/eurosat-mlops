# Tester le projet pas à pas

Ce guide part de zéro : un PC (Windows, macOS ou Linux) avec VS Code.
Comptez environ 30 minutes la première fois, dont 10 à 20 minutes
d'entraînement automatique du premier modèle.

> Sous Windows, `make` n'existe pas par défaut. Chaque étape donne donc
> aussi la commande `docker compose` équivalente, à taper dans le terminal
> de VS Code.

---

## Étape 0 — Installer les outils (une seule fois)

| Outil | Pourquoi | Lien |
|---|---|---|
| **Docker Desktop** | fait tourner les 10 conteneurs | https://www.docker.com/products/docker-desktop |
| **Git** | cloner et pousser le dépôt | https://git-scm.com |
| **Python 3.11+** | scripts (génération de secrets, démo de drift, Locust, tests) | https://www.python.org |
| **VS Code** + extensions *Docker* et *Python* | éditeur et terminal intégré | https://code.visualstudio.com |

Sous Windows, Docker Desktop doit utiliser **WSL 2** (proposé à
l'installation). Dans *Docker Desktop → Settings → Resources*, allouez au
moins **4 CPU et 8 Go de RAM**.

Vérification dans un terminal :

```bash
docker --version          # >= 24
docker compose version    # >= 2.24
python --version          # >= 3.11
```

## Étape 1 — Ouvrir le projet dans VS Code

1. Dézippez le projet (ou clonez le dépôt Git).
2. *File → Open Folder…* → dossier `eurosat-mlops`.
3. Ouvrez un terminal : *Terminal → New Terminal* (Ctrl + ù / Ctrl + `).

Toutes les commandes suivantes se tapent dans ce terminal, à la racine du projet.

## Étape 2 — Générer les secrets

```bash
python scripts/make_env.py
```

Le script crée `.env` et affiche la **clé admin** (`eus_…`) et le mot de
passe Grafana. Notez-les : la clé admin sert aux étapes suivantes. Le
fichier `.env` est ignoré par Git.

## Étape 3 — Lancer tout le système (niveau 0)

```bash
make up
# équivalent sans make :
docker compose up -d --build
```

Le premier build télécharge les images et PyTorch, ce qui prend 5 à
10 minutes. Suivez ensuite l'entraînement automatique du premier modèle :

```bash
docker compose logs -f trainer
```

On voit le téléchargement d'EuroSAT, puis trois époques
(`[01] train loss=… | val … f1=…`), puis `Version 1 -> alias 'champion'`.
Le conteneur `trainer` s'arrête alors : c'est normal.

Vérifiez que tout tourne :

```bash
docker compose ps
```

Tous les services doivent être `running` / `healthy`, sauf `trainer`,
qui est `exited (0)` une fois le premier modèle entraîné.

Le modèle est chargé par l'API quand cette URL répond `"status": "ready"` :
http://localhost/api/health/ready

> **Port 80 déjà pris ?** (IIS, Skype…) Mettez `GATEWAY_PORT=8080` dans `.env`,
> relancez `docker compose up -d`, puis remplacez `localhost` par `localhost:8080` partout.

## Étape 4 — Explorer les interfaces

| URL | Ce qu'il faut regarder |
|---|---|
| http://localhost:5001 | **MLflow** → *Experiments* : courbes, matrice de confusion, métriques FP32 vs INT8. *Models* : `eurosat-classifier` v1 avec les alias `champion` et `challenger` |
| http://localhost/api/docs | **Swagger** de l'API. Bouton *Authorize* → collez la clé admin |
| http://localhost | **Interface Streamlit** (clé à saisir à gauche) |
| http://localhost:3000 | **Grafana** (admin / mot de passe de l'étape 2) → tableau de bord *EuroSAT* |
| http://localhost:9090 | Prometheus → *Status → Targets* : les API sont `UP` |

## Étape 5 — Créer un utilisateur et tester la sécurité (niveau 1)

```bash
make create-user NAME=alice QUOTA=120
# sans make :
docker compose exec api-stable python -m app.cli create-user alice --quota 120
```

Notez la clé affichée. Récupérez ensuite des images de test réelles (300
images EuroSAT copiées dans `loadtest/images/`) :

```bash
make sample-images
# sans make (Windows PowerShell : remplacer $(pwd) par ${PWD}) :
docker compose run --rm -v "$(pwd)/loadtest:/workspace/loadtest" -v "$(pwd)/scripts:/workspace/scripts" trainer python scripts/sample_images.py --data-dir /data
```

Testez les trois cas (sous PowerShell, utilisez `curl.exe` au lieu de `curl`) :

```bash
# 1) sans clé -> 401
curl -i -X POST http://localhost/api/v1/predict -F "file=@loadtest/images/Forest_1.jpg"

# 2) avec clé -> 200 + prédiction JSON (adapter le nom d'un fichier existant de loadtest/images)
curl -i -X POST http://localhost/api/v1/predict -H "X-API-Key: <CLE_ALICE>" -F "file=@loadtest/images/Forest_1.jpg"

# 3) consommation d'alice
curl http://localhost/api/v1/me/usage -H "X-API-Key: <CLE_ALICE>"
```

Dans la réponse 200, les headers `X-Model-Version` et `X-Deployment-Track`
indiquent quel modèle a répondu (stable ou canary).

Pour voir l'usage de tous les utilisateurs (droits admin) :
`curl http://localhost/api/admin/usage -H "X-API-Key: <CLE_ADMIN>"`.

Faites aussi un tour dans l'**UI** (http://localhost) : uploadez quelques
images, consultez *Mon usage* et *Monitoring modèle*.

## Étape 6 — Test de charge (niveau 1)

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate     macOS/Linux : source .venv/bin/activate
pip install locust

# Windows PowerShell : $env:EUROSAT_API_KEY="<CLE_ALICE>"
export EUROSAT_API_KEY=<CLE_ALICE>

locust -f loadtest/locustfile.py --host http://localhost/api
```

Ouvrez http://localhost:8089, mettez 50 utilisateurs et un *spawn rate* de 10,
puis lancez. Ouvrez Grafana en parallèle : le trafic, la latence et la
répartition stable/canary évoluent en direct.

> Le quota d'alice (120/min) va renvoyer des 429 : **c'est voulu** et c'est
> la preuve que le rate limiting fonctionne. Pour un test de performance pur,
> créez un utilisateur avec `QUOTA=100000`.

Version sans interface, qui produit les rapports CSV/HTML pour la soutenance :

```bash
make loadtest USERS=50 DURATION=2m
# sans make :
locust -f loadtest/locustfile.py --host http://localhost/api --headless -u 50 -r 10 -t 2m --csv loadtest/results/u50 --html loadtest/results/u50.html
```

## Étape 7 — Data drift (niveau 2)

```bash
pip install requests pillow numpy
python scripts/simulate_drift.py --url http://localhost/api --key <CLE_ADMIN> --perturbation none --n 300
python scripts/simulate_drift.py --url http://localhost/api --key <CLE_ADMIN> --perturbation clouds --n 300
```

Avec `none`, le script doit afficher « pas de drift détecté ». Avec `clouds`
(ou `blur`, `noise`, `dark`), il doit afficher « DRIFT DÉTECTÉ ».

> La fenêtre glissante garde les 1 000 dernières images. Pour une démo
> propre, lancez le contrôle `none` en premier, puis une perturbation avec
> `--n 1000` pour remplir la fenêtre d'images altérées.

Le panneau *Drift* de Grafana et l'onglet *Monitoring modèle* de l'UI passent au rouge.

## Étape 8 — MLflow et canary (niveaux 2 et 3)

```bash
make train EPOCHS=5
# sans make :
docker compose run --rm trainer python -m training.train --epochs 5
```

1. Une **version 2** apparaît dans MLflow avec l'alias `challenger`.
2. Après 30 s au plus, `api-canary` la charge sans redémarrage (`docker compose logs api-canary`).
3. Environ 10 % des réponses ont `X-Model-Version: 2`. On peut forcer le canary avec
   `-H "X-Canary: always"`, ou le sélecteur *Forcer canary* de l'UI.
4. Promotion : `make promote` (ou `docker compose run --rm trainer python -m training.promote promote`).
   `api-stable` passe alors en v2.
5. Retour arrière : `make rollback`.

## Étape 9 — Scaling horizontal (niveau 3)

```bash
make scale N=3
# sans make :
docker compose up -d --no-deps --scale api-stable=3 api-stable
docker compose restart gateway
```

`docker compose ps` montre 3 conteneurs `api-stable`, et Prometheus
(*Targets*) en découvre 3. Relancez le test de charge pour comparer le débit
avec 1 réplica.

## Étape 10 — Tests automatisés

```bash
pip install -r api/requirements.txt pytest httpx onnx
pytest -q
```

Dans VS Code, l'onglet *Testing* (fiole) détecte aussi les tests pytest.

## Étape 11 — Arrêter / repartir de zéro

```bash
docker compose down        # arrête (les données sont conservées)
docker compose down -v     # arrête ET efface les volumes (modèles, base, dataset)
```

---

## Pour aller en production (VM, niveaux 1 et 2)

Il faut un compte AWS. Avec *AWS Academy* ou *Azure for Students*, demandez
d'abord à l'encadrant ce qui est autorisé.

1. `cd infra/terraform`, `cp terraform.tfvars.example terraform.tfvars`, puis mettez vos IP.
2. `terraform init && terraform apply` : la commande affiche `public_ip`.
3. Poussez le dépôt sur GitHub et créez les secrets `VM_HOST`, `VM_USER`,
   `VM_SSH_KEY`, `PROD_ENV` et `SMOKE_API_KEY` (*Settings → Secrets → Actions*).
4. `git tag v1.0.0 && git push --tags` : la pipeline **CD** construit les
   images, les pousse sur GHCR et déploie sur la VM.
5. Refaites les étapes 5 à 7 en remplaçant `localhost` par l'IP de la VM.

## En cas de problème

| Symptôme | Cause probable / solution |
|---|---|
| `/health/ready` reste en `loading` | Le trainer n'a pas fini : `docker compose logs trainer` |
| Le trainer est tué (`exit 137`) | Pas assez de RAM pour Docker : passez à 8 Go, ou `BOOTSTRAP_SUBSET=0.15` dans `.env` |
| `bind: address already in use` sur le port 80 | `GATEWAY_PORT=8080` dans `.env` |
| `bad interpreter` / `\r` dans un script `.sh` | Fins de ligne Windows : `git config core.autocrlf false`, puis reclonez (le `.gitattributes` force LF) |
| Erreur 401 avec une clé valide | Espace ou guillemet en trop dans la clé ; vérifiez le header `X-API-Key` |
| 429 en boucle | Quota atteint : attendez une minute, ou augmentez `QUOTA` |
