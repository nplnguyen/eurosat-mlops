"""Outil d'administration en ligne de commande (à lancer dans le conteneur).

    docker compose exec api-stable python -m app.cli create-user alice --quota 120
    docker compose exec api-stable python -m app.cli list-users
    docker compose exec api-stable python -m app.cli revoke alice
"""
from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db import SessionLocal, User, init_db
from app.routers.admin import create_user


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-user")
    c.add_argument("name")
    c.add_argument("--email")
    c.add_argument("--admin", action="store_true")
    c.add_argument("--quota", type=int)
    sub.add_parser("list-users")
    r = sub.add_parser("revoke")
    r.add_argument("name")
    args = ap.parse_args()

    init_db()
    if args.cmd == "create-user":
        user, key = create_user(args.name, args.email, args.admin, args.quota)
        print(f"Utilisateur '{user.name}' créé (id={user.id}).")
        print(f"Clé d'API (conservez-la, elle ne sera plus affichée) :\n{key}")
    elif args.cmd == "list-users":
        with SessionLocal() as db:
            for u in db.scalars(select(User).order_by(User.id)):
                print(f"{u.id:>3} {u.name:<20} {u.key_prefix}…  admin={u.is_admin} actif={u.is_active} "
                      f"quota={u.quota_per_minute}/min")
    elif args.cmd == "revoke":
        with SessionLocal() as db:
            u = db.scalar(select(User).where(User.name == args.name))
            if not u:
                raise SystemExit("Utilisateur introuvable")
            u.is_active = False
            db.commit()
        print(f"'{args.name}' révoqué.")


if __name__ == "__main__":
    main()
