"""Seed script — สร้าง admin ตั้งต้น + symbol XAUUSD (ห้าม hardcode password ใน code).

Usage: python -m app.db.seed --admin-email you@example.com --admin-password ...
Password ควรผ่าน env ADMIN_INITIAL_PASSWORD หรือ prompt แทน argument ใน production.
"""

import argparse
import asyncio
import getpass
import logging

from sqlalchemy import select

from app.core.event_loop import new_event_loop
from app.db.session import dispose_engine, get_session_factory
from app.models import Role, Symbol, User
from app.services.users import create_user

logger = logging.getLogger(__name__)

XAUUSD_DEFAULTS = {
    "name": "XAUUSD",
    "asset_class": "METAL",
    "digits": 2,
    "contract_size": 100,
    "tick_value": 1,
    "min_stop_distance": 0.30,
    "session_hours": {
        "asian": ["01:00", "09:00"],
        "london": ["08:00", "16:30"],
        "new_york": ["13:30", "21:00"],
    },
}


async def seed_admin(email: str, password: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            logger.info("admin %s already exists", email)
            return
        await create_user(session, email=email, password=password, role=Role.ADMIN)
        await session.commit()
        logger.info("created admin user %s", email)


async def seed_symbols() -> None:
    factory = get_session_factory()
    async with factory() as session:
        existing = await session.execute(select(Symbol).where(Symbol.name == "XAUUSD"))
        if existing.scalar_one_or_none() is not None:
            logger.info("symbol XAUUSD already exists")
            return
        session.add(Symbol(**XAUUSD_DEFAULTS))
        await session.commit()
        logger.info("seeded symbol XAUUSD")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed database")
    parser.add_argument("--admin-email", default=None)
    parser.add_argument("--admin-password", default=None)
    parser.add_argument("--skip-admin", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    async def _run() -> None:
        await seed_symbols()
        if not args.skip_admin:
            email = args.admin_email or input("Admin email: ")
            password = args.admin_password or getpass.getpass("Admin password (min 8 chars): ")
            await seed_admin(email, password)
        await dispose_engine()

    asyncio.run(_run(), loop_factory=new_event_loop)


if __name__ == "__main__":
    main()
