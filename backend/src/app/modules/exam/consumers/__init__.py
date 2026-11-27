"""EXAM queue consumers and scorer, served by the exam-consumers deployable (v2 §6.2, §6.3).

Reads answer batches from SQS, and in one transaction per 500 messages appends to
``exam.exam_answer_batches`` (primary key attempt_id, seq) and upserts
``exam.exam_answers_latest`` (highest seq wins). Also runs the two-phase close,
contiguity check, scoring and the precomputed results in Redis.
"""
