"""EXAM: Blueprints, exams, registration, attempts, results and merit.

Subpackages: ``ingest`` (served by the exam-ingest deployable; Redis + SQS only, never
PostgreSQL) and ``consumers`` (served by exam-consumers; SQS -> Postgres, scoring).
"""

CODE = "EXAM"
SCHEMA = "exam"
