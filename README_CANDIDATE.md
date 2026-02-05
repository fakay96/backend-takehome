# PAIR Take‑Home Exercise (≈60 minutes): Content assembly + progress

Thanks for taking the time to do this short exercise.

The goal is to get a realistic snapshot of how you design APIs and work with a relational database (Postgres) on a small but representative problem.

**Timebox:** A strong candidate should be able to complete the core requirements in about **1 hour**. If you run out of time, prioritise **correctness and clarity** over extra features.

---

## What you are building

You will build a small HTTP API that reads lesson content from Postgres, _assembles_ it into an ordered response, and records user progress.

The data model is “CMS-like”:

- A **Lesson** contains an ordered list of **Blocks**.
- Each **Block** can have **Variants**.
  - A variant may be a **default** (tenant_id = NULL).
  - Or a **tenant override** (tenant_id = X).
- When returning a lesson for a tenant, you must choose the **best variant** for each block.

We also track user progress per block in a lesson.

---

## Repository contents (provided)

This repository includes:

- `docker-compose.yml` – a Postgres database + optional Adminer UI
- `db/00-schema.sql` – schema
- `db/01-seed.sql` – seed data
- `openapi.yaml` – API contract (what to implement)
- `scripts/verify.py` and `scripts/curl_examples.sh` – quick ways to exercise the API

You will write your solution in your own code folder / language of choice.

---

## Setup: run the database

### 1) Start Postgres

```bash
docker compose up -d
```

Postgres will be available at:

- Host: `localhost`
- Port: `5432`
- Database: `pair_takehome`
- User: `pair`
- Password: `pair`

Connection string:

```
postgresql://pair:pair@localhost:5432/pair_takehome
```

### 2) (Optional) Inspect data via Adminer

Adminer is available at http://localhost:8081

- System: PostgreSQL
- Server: `db` (if accessing from another container) or `host.docker.internal` / `localhost` (from your machine)
- Username: `pair`
- Password: `pair`
- Database: `pair_takehome`

---

## Requirements (core)

Implement **two endpoints**:

1. **Get assembled lesson content + user progress**

`GET /tenants/{tenant_id}/users/{user_id}/lessons/{lesson_id}`

Returns:

- lesson metadata
- blocks in the correct order
- the **selected variant** for each block (tenant override > default)
- the user’s progress per block (if any)
- a summary of progress

2. **Upsert progress for a single block**

`PUT /tenants/{tenant_id}/users/{user_id}/lessons/{lesson_id}/progress`

Body:

```json
{
  "block_id": 200,
  "status": "seen"
}
```

This should be **idempotent**:

- Repeating the same request should not create duplicates.
- Progress is **monotonic**: `completed` should not be downgraded back to `seen`.

---

## Behaviour rules

### Tenant safety / validation

For both endpoints, you must ensure:

- the tenant exists
- the user exists and belongs to the tenant
- the lesson exists and belongs to the tenant

If any of the above is false, return **404**.

For the PUT endpoint, additionally validate:

- `block_id` is part of that lesson

If not, return **400**.

### Block ordering

Blocks must be returned ordered by `lesson_blocks.position` (ascending).

### Variant selection

For each block, select exactly one variant using this rule:

1. If a variant exists for `(block_id, tenant_id = {tenant_id})`, return that.
2. Otherwise return the default variant `(block_id, tenant_id IS NULL)`.

### Progress semantics

Progress is stored per block in `user_block_progress`.

- A block with status `completed` counts as both **seen** and **completed**.
- A block with status `seen` counts as **seen** only.
- Missing row => no progress for that block.

For PUT upsert:

- If the existing status is `completed` and the request is `seen`, keep it as `completed`.
- If the request is `completed`, set it to `completed`.

### Response shapes

Please follow the OpenAPI document (`openapi.yaml`). You do not need to support additional fields.

---

## What we’re looking for

- Clear, consistent API design (HTTP status codes, error responses)
- Solid relational DB usage (correctness > cleverness)
- Tenant isolation in queries (avoid accidental data leaks)
- Pragmatism and simplicity

---

## Constraints / non-requirements

To keep this doable in 1 hour:

- No authentication required (assume tenant_id/user_id are trusted inputs)
- No UI required
- No need to containerise your solution
- No need to add migrations or modify schema

---

## How to test your solution quickly

### Option A: curl

See `scripts/curl_examples.sh`.

### Option B: verification script

If you run your API at `http://localhost:8000`, you can run:

```bash
python3 scripts/verify.py --base-url http://localhost:8000
```

(If your API runs elsewhere, change the base URL.)

---

## What to submit

Please send us:

1. A link to a repo (clone this one as a starting point) with your implementation
2. In addition to your code, A short `NOTES.md` (≈5–15 lines) answering:
   - any trade-offs you made
   - anything you would improve with 2 more hours
3. Clear instructions to run your API locally.

That’s it — please don’t turn this into a big project.

Good luck!
