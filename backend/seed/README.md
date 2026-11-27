# Reference data

`scripts/seed_reference.py` loads these files with an upsert, so it is safe to rerun. Migrations
never hold bulk data (05 §B).

| File | Rows | Source | Status |
|---|---|---|---|
| `districts.csv` | 64 | `id` is the BBS district geocode | complete; check against the current BBS list before launch |
| `upazilas.csv` | ~495 | BBS; `id` is a stable integer code (for example the BBS district and upazila geocodes combined) | header only: the data owner supplies it |
| `institutions.csv` | — | BANBEIS institution list with EIIN | header only: the data owner supplies it |
| `moderation_terms.csv` | — | content team (05 §C.3) | header only: the content team supplies it |

Columns:
- `institutions.csv`: `kind` is one of `school`, `college`, `school_college`, `madrasah`, `technical`, `university`, `coaching`, `other`. `upazila_id` may be empty. Each row's id is derived from its EIIN, so reruns update the row instead of duplicating it.
- `moderation_terms.csv`: `lang` is `bn`, `en` or `banglish`; `severity` is 1–3; `category` is one of `profanity`, `sexual`, `hate`, `self_harm`, `contact_info`, `spam`. Terms are stored folded.
