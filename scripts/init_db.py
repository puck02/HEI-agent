#!/usr/bin/env python3
"""
Initialize database — create tables and optionally seed with test data.

Usage:
    python scripts/init_db.py [--seed]
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true", help="Seed with test data")
    args = parser.parse_args()

    from app.database import init_db, async_session_factory
    from app.models.user import User  # noqa — ensure model is loaded

    print("🔧 Creating database tables...")
    await init_db()
    print("✅ Tables created successfully!")

    if args.seed:
        print("🌱 Seeding test data...")
        from app.auth.service import create_user

        async with async_session_factory() as session:
            try:
                user = await create_user(
                    session,
                    username="testuser",
                    email="test@heldairy.app",
                    password="Test123456",
                    display_name="测试用户",
                )
                await session.commit()
                print(f"   ✅ Test user created: {user.username} (id: {user.id})")
            except Exception as e:
                print(f"   ⚠️ Seed skipped: {e}")

    print("\n🎉 Database initialization complete!")


if __name__ == "__main__":
    asyncio.run(main())
