"""GAM: XP ledger, levels, streaks and leaderboards.

Ledger and streak writes happen inside the answer transaction; leaderboards live in
Redis (app.core.redis) and are rebuilt from the ledger by Postgres-queue jobs (v2 §3.6).
"""

CODE = "GAM"
SCHEMA = "rewards"
