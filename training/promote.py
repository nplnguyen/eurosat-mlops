"""Gestion du cycle de vie des modèles dans le Model Registry MLflow.

Les services lisent des *alias* et non des numéros de version :
  - `champion`   : servi à ~90 % du trafic (api-stable)
  - `challenger` : servi à ~10 % du trafic (api-canary)

Les API rechargent automatiquement le modèle quand un alias change
(polling périodique), ce qui permet une mise à jour sans redéploiement.

    python -m training.promote status
    python -m training.promote promote          # challenger -> champion
    python -m training.promote rollback         # champion -> version précédente
    python -m training.promote set challenger 4 # alias manuel
"""
from __future__ import annotations

import argparse

from mlflow.tracking import MlflowClient

from training.config import REGISTERED_MODEL_NAME as NAME


def _alias(client: MlflowClient, alias: str):
    try:
        return client.get_model_version_by_alias(NAME, alias)
    except Exception:
        return None


def status(client: MlflowClient) -> None:
    versions = sorted(client.search_model_versions(f"name='{NAME}'"), key=lambda v: int(v.version))
    for v in versions:
        full = client.get_model_version(NAME, v.version)
        aliases = ",".join(full.aliases) or "-"
        print(f"v{v.version:>3}  run={v.run_id[:8]}  f1={v.tags.get('test_f1_macro', '?'):>6}  aliases={aliases}")


def promote(client: MlflowClient) -> None:
    ch = _alias(client, "challenger")
    if ch is None:
        raise SystemExit("Aucun challenger à promouvoir.")
    old = _alias(client, "champion")
    if old is not None:
        client.set_registered_model_alias(NAME, "previous-champion", old.version)
    client.set_registered_model_alias(NAME, "champion", ch.version)
    print(f"Promotion : v{ch.version} est maintenant champion (ancien : v{old.version if old else '-'})")


def rollback(client: MlflowClient) -> None:
    prev = _alias(client, "previous-champion")
    if prev is None:
        raise SystemExit("Pas de version précédente connue.")
    client.set_registered_model_alias(NAME, "champion", prev.version)
    client.set_registered_model_alias(NAME, "challenger", prev.version)
    print(f"Rollback : champion et challenger -> v{prev.version}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("promote")
    sub.add_parser("rollback")
    s = sub.add_parser("set")
    s.add_argument("alias")
    s.add_argument("version")
    args = ap.parse_args()
    client = MlflowClient()
    if args.cmd == "status":
        status(client)
    elif args.cmd == "promote":
        promote(client)
    elif args.cmd == "rollback":
        rollback(client)
    else:
        client.set_registered_model_alias(NAME, args.alias, args.version)
        print(f"Alias {args.alias} -> v{args.version}")


if __name__ == "__main__":
    main()
