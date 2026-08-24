"""SQLite persistence for resume templates and resume-generation history.

See app/db/models.py for the two tables and app/db/session.py for the
engine/session setup. This is intentionally the only database in the
project (no Alembic migrations) - schema changes at this MVP stage are
made directly to models.py and picked up by init_db()'s create_all() on
next startup.
"""
