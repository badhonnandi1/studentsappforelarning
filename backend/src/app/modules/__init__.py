"""Feature modules of the modular monolith (v2 §2.4).

Each package owns one PostgreSQL schema. Its package root (and named public files
such as ``contracts.py``) is the public interface; ``internal/`` is private and
must not be imported by another module (enforced by import-linter).
"""
