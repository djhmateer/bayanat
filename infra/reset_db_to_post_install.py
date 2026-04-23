#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
infra/reset_db_to_post_install.py
==================================
Reset database to the state it was in immediately after running flask create-db
and flask import-data (post-setup wizard completion).

Clears all content data (bulletins, actors, incidents, etc.) and removes test users,
but preserves reference data (event types, violations, countries, etc.).

USAGE
─────
    uv run python infra/reset_db_to_post_install.py

Must be run from the project root with the virtual environment active.
"""

if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))

    from enferno.app import create_app
    from sample_data.sample_data_minimal_reset import clear_all_content
    from enferno.user.models import User
    from enferno.extensions import db

    app = create_app()
    with app.app_context():
        # Clear all content data (bulletins, actors, incidents, media, etc.)
        clear_all_content()

        # Delete test users (keep admin user id=1)
        test_user_ids = [362, 363, 364]
        for uid in test_user_ids:
            user = db.session.get(User, uid)
            if user:
                db.session.delete(user)
                print(f"  Deleted user {uid}: {user.username}")
        db.session.commit()

        print("✓ Database reset to post-install state (reference data preserved).")
