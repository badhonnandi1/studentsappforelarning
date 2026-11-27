# 17 · Scalability and performance

**Date:** 2026-11-27 · **Status: nothing in this document has been measured.** Every rate, instance count and capacity is a planning figure marked **[Assumption]** or **[Needs evidence]**. The system is not claimed to support 100,000 concurrent users until the Stage 4 load test in §8 passes. Database growth and hot paths: [`01`](01_database_design.md) §5.10–§5.12. Exam design: [`system-design-v2.md`](../system-design-v2.md) §6.

---

## 1. Terms

| Term | Definition here | Year-1 figure (v2 §0.1) | Stage 4 target |
|---|---|---|---|
| Registered users | Accounts that exist | 500,000 | ~8,000,000 **[Assumption]** |
| Daily active users (DAU) | Users with ≥ 1 authenticated request in a Dhaka day | 60,000 | ~1,000,000 |
| Concurrent users | Users with a request in the last 5 minutes, at the busiest 5 minutes of the day (19:00–22:00 Dhaka) | 6,000 (10% of DAU) | **100,000** |
| Concurrent HTTP requests | Requests in flight at an instant (= RPS × mean latency) | ~25 | ~500–750 |
| Requests per second (RPS) | Completed HTTP requests per second at the origin (after CDN) | ~250 | ~5,000 sustained, ~7,500 peak minute |
| Persistent connections | Open SSE tutor streams (B4) and WebSockets (B9 duels) | ~40 | ~700–2,000 SSE |
| Simultaneous AI requests | Provider calls in flight | ~25 | ~400–1,200 |
| Live-exam concurrency | Candidates in one live exam; a separate workload (§3) | Capped at 20,000 at launch (C17) | 200,000 design ceiling |

The ratio of 10 DAU per concurrent user comes from v2's year-1 figures; it is replaced by measured pilot data at week 16.

## 2. Learner workload model (outside live exams)

### 2.1 Activity mix of a concurrent user **[Assumption]**

| Activity | Share of concurrent users | Requests per minute | Writes among them |
|---|---|---|---|
| In a practice session (Learn or Test) | 60% | 1.5 answers + 0.13 session start/complete + 0.6 reads + 0.2 telemetry = **2.4** | 1.5 answers + 0.13 + 0.2 |
| Browsing (home, dashboard, boards, inbox) | 15% | **4.0** reads | 0.1 |
| Tutor conversation | 10% | 0.5 messages + 1.0 reads = **1.5** | 0.5 |
| Mock or model test via API | 10% | 1.2 answers + 0.3 reads = **1.5** | 1.2 |
| Other (bookmarks, notes, profile) | 5% | **2.0** | 0.5 |
| **Weighted** | 100% | **≈ 2.6 per minute ≈ 0.043/s** (plan with **0.05/s** for headroom) | ≈ 1.2 per minute |

Read/write ratio ≈ **55:45** by request count. Writes are dominated by answer saves, which are also the heaviest database transaction.

### 2.2 Derived rates

| Quantity | Formula | Stage 1 (1k) | Stage 2 (10k) | Stage 3 (50k) | Stage 4 (100k) |
|---|---|---|---|---|---|
| Origin RPS (sustained) | concurrent × 0.05 | 50 | 500 | 2,500 | 5,000 |
| Origin RPS (peak minute, ×1.5) | | 75 | 750 | 3,750 | 7,500 |
| Answer transactions/s | concurrent × (0.6 × 1.5 + 0.1 × 1.2) / 60 = concurrent × 0.017 | 17 | 170 | 850 | 1,700 (peak ~2,500) |
| Row writes/s in answer path | answer tx × ~8 rows ([`01`](01_database_design.md) §5.1) | 140 | 1,400 | 6,800 | 13,600 (peak ~20,000) |
| Outbox events/s | answer tx × 1.3 + other writes × 0.3 | 25 | 250 | 1,250 | 2,500 |
| Background jobs created/s | relay batches events per consumer: ≈ events / 500 + scheduled jobs | < 1 | ~2 | ~8 | ~15 |
| `processed_events` rows/s | one row per (consumer, relay batch), not per event (01 §5.3) | < 1 | ~2 | ~8 | ~15 |
| Leaderboard updates/s (Redis) | reward rows/s × 9–12 boards, applied by Lua with a per-board marker (01 §5.2 R20) | ~300 | ~3k | ~15k | ~30k (peak ~45k) |
| WAL generated (sustained) **[Assumption]** | row writes/s × ~1.2 KB (heap + 3–4 index entries + amortised full-page writes) + outbox | ~0.2 MB/s | ~2 MB/s | ~9 MB/s | ~18 MB/s (peak ~27 MB/s) |
| Session starts/s | 0.6 × concurrent × 0.13 / 60 | 1.3 | 13 | 65 | 130 |
| Tutor messages/s | 0.10 × concurrent × 0.5 / 60 | 0.8 | 8 | 42 | 83 |
| Open SSE streams | messages/s × 8 s mean stream | 7 | 70 | 340 | 670 (2,000 if tutor share is 30%) |
| Provider calls/s after 40% canonical-cache hits | 0.6 × messages/s | 0.5 | 5 | 25 | 50 (150 at 30% share) |
| Tokens/s to the provider | calls/s × ~3,180 (80% cheap at 2,850, 20% strong at 4,500; v2 §8.6) | 1.6k | 16k | 80k | 160k (≈ 9.5M tokens/min) |

This table is the **single source** for learner-path rates. Other documents ([`01`](01_database_design.md) §4.1, §5.11) refer to it. The WAL figure drives replica lag, backup volume (about 1.5 TB/day at Stage 4 peak if sustained, so WAL compression is on) and the Stage-3 instance choice. All rows are first measured in the Build 3 synthetic benchmark ([`07_build_03.md`](07_build_03.md) §F), which records the measured capacity as evidence. It is not a pass or fail on 100k.

**Job queue finding.** If the outbox relay created one job per event per consumer, Stage 4 would need ~5,000 jobs/s, five times the Postgres job-queue limit in v2 §0.2 (~1,000 jobs/s). **[Decision]** The relay therefore creates **batched consumer jobs** (one `gam.leaderboard.apply` job per ≤ 500 reward events, one Parquet flush per partition-minute), keeping job creation near 15/s at Stage 4. This is a Build 1 requirement for the relay ([`05_build_01.md`](05_build_01.md)).

**AI provider finding.** ~9.5M tokens/min at Stage 4 is above typical default provider rate limits **[Needs evidence: current Anthropic tier limits for the account]**. It needs a negotiated limit, the second provider allowed by v2 §0.4 after launch, or tighter quotas. The gateway enforces a global concurrency budget (§5.6) so overload degrades to the fallback responses in v2 §4.4 rather than failing.

**AI cost at Stage 4 [Assumption].** 83 messages/s × 3,600 × $0.0027 ≈ **$800 per peak hour**. This is the largest variable cost driver and is controlled by the per-user ceiling and the global daily budget breaker (v2 §4.6).

### 2.3 Bandwidth and caching

| Item | Estimate | Note |
|---|---|---|
| Session payload | ≤ 30 KB compressed for 10 questions in lite mode (NFR-02 gate 2) | Session starts at Stage 4: 130/s × 30 KB ≈ 31 Mbit/s |
| Other API JSON | ~2 KB mean × 5,000 RPS ≈ 80 Mbit/s | brotli at the edge |
| Media | Served by Cloudflare from R2 via signed URLs | Origin egress excludes media |
| Origin egress at Stage 4 | ~150 Mbit/s | Well within one ALB |

| Cache | Hit target | Working set |
|---|---|---|
| Question version payloads (Redis, immutable key) | ≥ 99% | 150,000 questions × 2 languages × ~3 KB ≈ 0.9 GB |
| Canonical tutor answers (Postgres, read through gateway memory LRU) | ≥ 40% of tutor messages (v2 §8.6) | grows with bank × actions |
| Entitlements (Redis `pay:access:{user_id}`, 30 s, deleted on `entitlement.changed`) | ≥ 95% | per active user |
| Taxonomy trees, tracks, catalogue (edge cache) | ≥ 99% | small |
| Leaderboards | 100% Redis (no DB on read) | ~ boards × top 100 |
| Runtime config (`cfg:runtime`) | ≥ 99.9% (30 s) | tiny |

## 3. Live-exam workload

Taken from v2 §6.1 (100 MCQ, 60 min, 130 answer events per candidate, 15 s flush at a random phase). Exams run on the isolated `exam-ingest` and `exam-consumers` deployables but write to the same Postgres primary.

| Quantity | 20,000 (launch cap) | 50,000 | 200,000 (ceiling) |
|---|---|---|---|
| Key release at the edge (5 s jitter) | 4,000 req/s | 10,000 req/s | 40,000 req/s |
| Autosave hard ceiling | 1,333 req/s | 3,333 req/s | 13,333 req/s |
| Autosave expected | 560 req/s | 1,400 req/s | 5,600 req/s |
| Ingest provisioned (2 × ceiling) | 3,000 req/s → 2–3 instances at 1,500/s **[Needs evidence]** | 7,000 → 5 | 30,000 → 20 (60 if 500/s) |
| Consumer upserts into Postgres | ~800 rows/s, 1,900 at ceiling | ~2,000 / 4,800 | ~8,000 / 19,000 (architecture review §4.4) |
| Final flush at end | 840 req/s | 2,100 req/s | 8,400 req/s |
| Result reads at publish (precomputed in Redis) | 1,000 req/s | 2,500 req/s | 10,000 req/s |
| Merit computation | seconds | < 30 s | < 2 min |

**Interaction with learner traffic.** At Stage 3–4 the exam consumer writes (up to 19,000 rows/s) and the learner answer path (up to 20,000 rows/s) compete for the same primary. **[Decision]** National exams (≥ 50,000) are scheduled outside the 19:00–22:00 learner peak, or the exam tables move to a dedicated instance (trigger in §6). The 250,000 rehearsal measures the combined load.

## 4. Performance targets

| Target | Value | Measured where | Source |
|---|---|---|---|
| API latency, all endpoints | p95 < 300 ms at the origin at 6,000 concurrent (v2 §8.2); same at each stage's load test | ALB + OpenTelemetry | v2 §8.2 |
| Answer save (server time) | p95 < 150 ms, p99 < 400 ms | Route histogram | [Rule] |
| Answer transaction DB time | p95 < 25 ms | DB span | [`01`](01_database_design.md) §5.1 |
| Question load on BD-3G | p95 < 300 ms tap to render (local) | Client lab | NFR-02 gate 1 |
| Session start on BD-3G | p95 < 2.5 s; payload < 30 KB / 10 questions in lite mode | Client lab + payload test | NFR-02 gate 2 |
| Result after submit | p95 < 5 s at 2,000 concurrent submits; provisional live-exam score within 5 s | Load test | NFR-02, C3 |
| Tutor first **verified** text (R-10 release policy: buffered for minors and free-form answers, per-sentence moderated for adult cheap-tier) | Adult sentence mode p50 1.5 s, p95 4 s (the v2 §4.8 targets now measure the first verified sentence); buffered cheap tier p95 ≤ 6 s; buffered strong tier p95 ≤ 12 s; cache hit p95 500 ms; photo solve p95 20 s. The buffered targets diverge from v2 §4.8 because no unmoderated text reaches minors; this needs supervisor acceptance. | Gateway spans `first_verified_text` | v2 §4.8, review R-10 |
| Tutor unavailable response when provider is down | < 2 s | Breaker test | v2 §4.5 |
| Exam acknowledgement | p99 < 500 ms; 99.95% of batches acknowledged within 2 s in exam windows | Ingest histogram | v2 §6.4, architecture review §5.1 |
| Leaderboard and notification lag after an answer | p95 ≤ 5 s (relay polls every 250 ms while there is work, 1 s when idle; R-17) | Outbox-to-apply metric; first measured in the B3 Stage-4 benchmark | [`01`](01_database_design.md) §5.4 |
| Event log lag to S3 | p95 < 5 min | Relay checkpoint age | NFR-09 |
| Search | p95 < 300 ms; top-10 recall ≥ 90% | Search test set | v2 §7.1 |
| Availability | 99.9% monthly for the four journeys | Edge SLI | NFR-03 |

## 5. Capability evaluation

| Capability | Verdict | Detail |
|---|---|---|
| Horizontal scaling | **Now** | All deployables stateless; ECS services autoscale on CPU (api), open streams (ai-gateway), queue depth and age (workers, consumers), pre-scaled (exam-ingest). |
| Stateless application servers | **Now** | No in-process session state. Caches are bounded: entitlements 30 s in Redis, config 30 s, immutable payloads. Sticky sessions are never required; SSE reconnects carry `Last-Event-ID` and the message id. |
| Async FastAPI | **Now** | Uvicorn with uvloop, 1 process per vCPU, behind the ALB (no Gunicorn needed on ECS; one container per 2 vCPU running 2 workers). All I/O async: asyncpg, redis-py asyncio, HTTPX. CPU-heavy work (Parquet writing, KaTeX, image re-encoding, SymPy, merit sort) runs in workers, never in `api`. |
| Load balancing | **Now** | Cloudflare → ALB per deployable path group. ALB pre-warming requested from AWS before large exams (v2 §6.2). |
| Redis | **Now: two deployments (R-09).**<br>• **General Redis:** caches, quotas, leaderboards, telemetry stream, rate limits. A single primary + replica (ElastiCache) at Stages 1–2; **cluster mode** at Stage 3 when CPU > 60% or memory > 70%.<br>• **Exam Redis:** a separate replication group, Multi-AZ with automatic failover, `noeviction`, AOF everysec. It holds only `exam:*` and `exam_lock:*`: the ack ledger, epoch, in-flight marker, status, paper manifest and precomputed results. It is sized for 200k attempts (~1 GB, plus 10k result reads/s) and scaled up before each major exam. A general-Redis failover or eviction therefore never affects exam acknowledgements. On an exam-Redis failover, ingest returns 503 for the few seconds of promotion; clients retry. If the ledger is lost, the `resync` path and fallback contiguity evidence apply ([`09`](09_build_05.md) §C.1 step 10, 13). Key names in [`01`](01_database_design.md) §3.17 use hash tags (`{user}`) only where multi-key Lua needs co-location (rate limits per user). Leaderboard keys are per board, so they distribute across shards. |
| Distributed caching | **Now, narrow** | Redis caches only immutable or short-TTL data. No cache-aside for mutable learning state (the answer response returns fresh values). |
| PgBouncer pooling | **Now** | Transaction mode. Little's law: active server connections ≈ tx/s × mean tx time. Stage 4: 2,500 answer tx/s × 15 ms ≈ 38 + 5,000 reads/s × 3 ms ≈ 15 + workers ≈ 30 → ~85 active; `default_pool_size` 120 per database across 3 PgBouncer tasks, RDS `max_connections` 1,000 leaves headroom for migrations and replicas. Client side: ~50 api tasks × 2 workers × pool 10 = 1,000 client connections to PgBouncer (cheap). |
| Background queue | **Postgres job queue now** | Batched consumer jobs keep it near 15 jobs/s at Stage 4 (§2.2). **Move a job kind to SQS** if its claim latency p95 > 5 s or the queue exceeds ~1,000 jobs/s (v2 §0.2). |
| Independent worker scaling | **Now** | Job kinds are grouped into the canonical queues from `core/jobs/queues.py` (`default`, `relay`, `notify`, `sms`, `gam`, `rescoring`, `imports`, `ai`, `exam`, `campaign`, `payments`, `maintenance`; R-04). Each worker service subscribes to a set of queues and scales on its queues' depth. The relay is its own loop, polling every 250 ms while there is work and every 1 s when idle, on a direct connection (R-17). |
| Read replicas | **One replica now** for search and reporting; **routing at Stage 3** ([`01`](01_database_design.md) §5.9). |
| Partitioning | **Now** for the tables in [`01`](01_database_design.md) §1.2, because retrofitting is the costly part. |
| Object storage | **Now** | S3 for uploads and the event log; R2 for papers and media behind Cloudflare. |
| CDN | **Now** | Cloudflare for static, media, paper bundles, edge-cached reads (tracks, trees, catalogue), WAF and IP rate limits. |
| Rate limiting | **Now** | Tiers in [`14`](14_api_contracts.md) §1.7; Redis sliding window via one Lua script; edge limits per IP. |
| Distributed locking | **Avoided by design** | Correctness uses database constraints and row locks ([`01`](01_database_design.md) §5.2). Redis locks are used only for best-effort singleton jobs (partition maintenance, settlement scheduler) with leases, and the job is still idempotent if two run. |
| Idempotency | **Now** | [`01`](01_database_design.md) §5.3. |
| Retries with jitter | **Now** | Clients: exponential backoff with full jitter for answers and batches. Jobs: 8 tries, backoff `min(2^n × 5 s, 1 h) × U(0.5, 1.5)`. Provider calls: at most 1 retry, only for idempotent requests. |
| Circuit breakers | **Now** (B4 for AI; B1 helper) | `core.resilience.Breaker` per provider: opens at 50% errors over 30 s with ≥ 20 calls, half-open probe every 10 s. |
| Backpressure | **Now** | ai-gateway: per-user 1 concurrent stream; global in-flight budget from `runtime_config` (`ai.max_inflight`); over budget → `unavailable` fallback quickly. Workers: bounded batch sizes. Ingest: 503 + client retry when SQS throttles. Relay: pauses consumers' enqueue if job queue age > 60 s. |
| Graceful degradation | **Now** | AI down ≠ practice down (v2 §4.5); leaderboards stale but readable if workers lag; notifications delayed, inbox authoritative; search falls back to lexical if embedding service is down; kill switches for tutor, photo solve, registrations, payments. |
| Failure isolation | **Now** | Separate deployables for AI and exams; separate DB pools; bulkheads (separate HTTPX clients and breakers per provider); worker queues separated so a rescoring backlog cannot delay OTP SMS or payments. |

## 6. Phased scaling strategy

Instance sizes are **estimates** to be replaced by the stage's load-test results.

| | Stage 1: 1,000 concurrent | Stage 2: 10,000 | Stage 3: 50,000 | Stage 4: 100,000+ |
|---|---|---|---|---|
| Matches | Pilot (week 16) | Year 1 peak and above | Growth | Target |
| `api` | 2 tasks × 2 vCPU | 6–8 tasks | 25–30 tasks | 50–60 tasks |
| `workers` | 2 tasks | 4 | 10 | 16–20 (relay ×4 by partition) |
| `ai-gateway` | 2 tasks | 3 | 8–10 | 15–25 |
| PgBouncer | 2 tasks | 2 | 3 | 3–4 |
| Postgres | RDS db.r7g.large Multi-AZ | db.r7g.2xlarge + 1 replica | db.r7g.8xlarge + 2 replicas, replica routing | db.r7g.16xlarge, or `practice`+`rewards` on their own cluster; exam tables optionally separate |
| Redis (general) | cache.r7g.large primary + replica | cache.r7g.xlarge | Cluster mode, 3 shards | Cluster mode, 6 shards |
| Redis (exam, `noeviction`, AOF, Multi-AZ) | cache.r7g.large primary + replica | cache.r7g.large | cache.r7g.xlarge (scaled up before exams) | cache.r7g.2xlarge for a 200k exam |
| Expected bottlenecks | AI cost, SMS cost, content volume | Outbox relay lag; `jobs` autovacuum; OTP SMS gateway throughput **[Needs evidence]**; provider TPM | Primary write throughput and WAL; Redis CPU on boards; leaderboard rebuild time; search on one replica | Answer-path writes (~20k rows/s peak); provider token limits; relay throughput; exam + learner overlap |
| Capabilities required | Everything marked "Now" in §5 | Relay batching proven; queue separation; replica for search | Replica routing; Redis cluster; second relay partitioning; search p95 check (OpenSearch trigger) | DB split by module pair; second AI provider or negotiated limits; SQS for hot job kinds if needed; multi-AZ capacity reservations |
| Scaling triggers | — | p95 API > 200 ms for 3 days; primary CPU > 50% at peak | Primary CPU > 60% at peak for 2 weeks; Redis CPU > 60%; search p95 > 300 ms | Any Stage 3 trigger after Stage 3 actions; job claim p95 > 5 s; provider 429 rate > 1% |
| Operational complexity | Low: one region, one primary | Low–medium | Medium: replica lag monitoring, Redis cluster | High: multiple DB clusters, capacity planning per exam |
| Cost drivers | AI ($640 of ~$1,675/month, v2 §8.6), SMS | AI, RDS size | AI, RDS + replicas, Redis cluster | AI (~$800 per peak hour), RDS, compute |
| Load test before entering | 2× Stage 1 profile (2,000 concurrent) | 15,000 concurrent profile | 60,000 | 125,000 (1.25×) |

**Implemented now vs. deferred.**

| Now (B1–B6) | Deferred until a trigger fires |
|---|---|
| Stateless services, async I/O, per-deployable autoscaling | Read-replica routing for app reads (Stage 3) |
| PgBouncer, statement timeouts, separate pools | Redis cluster mode (Stage 3) |
| Partitioned high-volume tables, partition maintenance | Splitting `practice`+`rewards` to their own cluster (Stage 4) |
| Outbox with batched consumer jobs | Moving job kinds to SQS (> 1,000 jobs/s) |
| Redis rate limits, quotas, leaderboards; immutable payload cache | OpenSearch (search p95 > 300 ms or > 5M docs, v2 §0.2) |
| Circuit breakers, kill switches, AI admission control | ClickHouse (dashboard latency, v2 §8.4) |
| Exam path isolated (ingest, SQS, consumers), precomputed results | Second AI provider (after it passes the eval) |
| One replica for search | Multi-region active-passive (beyond NFR-10 backups) |

## 7. Exam scale staging

Unchanged from v2 C17: launch cap 20,000; raise to 50,000 and 200,000 only after a passing rehearsal at 1.25× the new size (25,000, 62,500, 250,000), with the fault injection of v2 §6.4. The first rehearsal (B5) runs at 25,000 on staging.

## 8. Load-testing strategy

| Item | Choice |
|---|---|
| Tool | **k6** (Go engine; one generator drives ~30–50k virtual users; scripts in `backend/tests/load/*.js`, each ≤ 200 lines). `xk6-sse` extension for tutor streams. |
| Environment | `perf` environment: a copy of staging sized to the target stage, seeded with synthetic data: 1M users (Stage 4 seed 8M), 150,000 questions × 2 languages, 12 months of synthetic attempts so partitions and indexes have realistic size. Never production. |
| Generators | Run from AWS ap-south-1 plus a small share from Bangladeshi networks for latency realism; Cloudflare in the path. |
| Scenarios | `learner_mix` (§2.1 mix, think times from pilot telemetry once available), `answer_burst` (all users answer within 10 s), `tutor_streams` (SSE with the fake provider at real latency, and a short live-provider run within budget), `exam_<size>` (v2 §6.4 sequence with fault injection), `result_rush` (publish-time reads), `otp_storm` (rate-limit correctness, SMS sandbox). |
| Duration | 10 min ramp, 30 min steady at target, 10 min at 1.5× peak, 10 min ramp down; soak test of 4 h at Stage target monthly. |
| Pass criteria | §4 targets met at steady state; error rate < 0.1% (excluding intentional 429s); no unbounded queue growth (queue age stable); primary CPU < 70%; PgBouncer wait p95 < 5 ms; zero data-integrity failures in a post-run replay check (projections match a rebuild for a 1% sample); for exams, the v2 §6.4 pass conditions. |
| Cadence | **Early evidence, not deferred to B9 (R-12):** at the end of **Build 3**, a Stage-4 synthetic benchmark of the answer transaction (target 2,500 tx/s), the relay, `processed_events` and WAL, and the 9–12-board leaderboard fan-out, on a production-sized staging database ([`07_build_03.md`](07_build_03.md) §F.1 item 11). It records measured capacity as evidence; shortfalls revise [`01`](01_database_design.md) §5 and this document before Build 4. After that: each stage entry (§6); before every exam above 20,000; and after any change touching the answer path, outbox, ingest or consumers (a 15-minute `answer_burst` in staging). |
| Reporting | Results recorded in `docs/perf/` with the commit SHA, environment sizes and dashboards; a stage is "supported" only with a passing report. |

Until those reports exist, the supported scale is **whatever the most recent passing test demonstrated**. At the time of writing that is **none**.
