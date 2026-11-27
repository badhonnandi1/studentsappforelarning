"""EXAM answer intake, served by the exam-ingest deployable (v2 §6.2).

Ingest verifies the exam session token, sends the batch to the answer queue and
acknowledges only after the queue confirms. It touches only Redis and the queue,
never PostgreSQL, so a slow database cannot stop acknowledgements. import-linter
forbids this package and its entry point from importing app.core.db, sqlalchemy,
psycopg or alembic.
"""
