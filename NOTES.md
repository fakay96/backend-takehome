# Notes

## How to run

```bash
docker compose up -d
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver 8000
```

API is at `http://localhost:8000`. To verify:

```bash
python3 scripts/verify.py --base-url http://localhost:8000
```

To run unit and integration tests (47 tests, transaction-safe — no DB reset needed):

```bash
python manage.py test lessons.tests -v 2 --keepdb
```

To run functional tests against the live server (requires server running and clean seed data):

```bash
python3 scripts/verify.py --base-url http://localhost:8000
bash scripts/curl_examples.sh
```

## Trade-offs

- Used Django's LocMemCache for lesson structure caching — fine for single-process dev, would need Redis for multi-worker production.
- Stayed within the ORM rather than raw SQL for the progress upsert (`SELECT FOR UPDATE` + `IntegrityError` retry instead of `INSERT ... ON CONFLICT`). More readable, slightly less optimal.
- Variant resolution happens in Python after fetching all candidates (tenant + default) in one query. Simpler SQL, works well at current scale.
- Django lacks native composite PK support, so `LessonBlock` and `UserBlockProgress` use `primary_key=True` on one FK and always filter explicitly.

## What I'd improve

- Switch to Redis cache for multi-process deployments.
- Use `INSERT ... ON CONFLICT` raw SQL to reduce the progress upsert to a single round-trip.
- Add request-level logging and structured error tracing for observability.
- Load-test the concurrent upsert path to validate the retry logic under contention.
- Introduce per-tenant database routing as the service scales — reduces blast radius and allows independent scaling of high-traffic tenants.
