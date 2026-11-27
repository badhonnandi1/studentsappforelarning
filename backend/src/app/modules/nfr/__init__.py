"""NFR: Event pipeline (outbox, job queue), idempotency keys, search, security and observability.

Public files: ``outbox.py`` (transactional outbox) and ``jobqueue.py`` (Postgres job
queue consumed by the workers deployable). See v2 §3.5.
"""

CODE = "NFR"
SCHEMA = "platform"
