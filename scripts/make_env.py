"""Génère un fichier .env avec des secrets aléatoires (Windows, macOS, Linux).

    python scripts/make_env.py            # crée .env
    python scripts/make_env.py .env.prod  # crée .env.prod
"""
import re
import secrets
import sys
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else ".env")
if out.exists():
    print(f"{out} existe déjà, rien à faire.")
    sys.exit(0)
text = Path(".env.example").read_text(encoding="utf-8")
values = {
    "API_KEY_PEPPER": secrets.token_urlsafe(32),
    "ADMIN_API_KEY": "eus_" + secrets.token_urlsafe(32),
    "GRAFANA_PASSWORD": secrets.token_urlsafe(16),
}
for key, val in values.items():
    text = re.sub(rf"^{key}=.*$", f"{key}={val}", text, flags=re.M)
out.write_text(text, encoding="utf-8", newline="\n")
print(f"{out} créé.\nClé admin : {values['ADMIN_API_KEY']}\nMot de passe Grafana : {values['GRAFANA_PASSWORD']}")
