"""AI: AI tutor, retrieval, OCR, model routing, cache and evals.

The tutor SSE route (POST /v1/tutor/messages, v2 §3.2) is served by the ai-gateway
deployable, not by api, so slow provider calls cannot exhaust api workers (NFR-03).
"""

CODE = "AI"
SCHEMA = "ai"
