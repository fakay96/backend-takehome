#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "1) GET assembled lesson for tenant=1 user=10 lesson=100"
curl -sS "$BASE_URL/tenants/1/users/10/lessons/100" | jq .

echo
echo "2) PUT progress: mark block 202 as seen"
curl -sS -X PUT "$BASE_URL/tenants/1/users/10/lessons/100/progress" \
  -H "Content-Type: application/json" \
  -d '{"block_id":202,"status":"seen"}' | jq .

echo
echo "3) PUT progress: mark block 202 as completed"
curl -sS -X PUT "$BASE_URL/tenants/1/users/10/lessons/100/progress" \
  -H "Content-Type: application/json" \
  -d '{"block_id":202,"status":"completed"}' | jq .

echo
echo "4) Idempotency / monotonicity check: try to downgrade completed -> seen (should stay completed)"
curl -sS -X PUT "$BASE_URL/tenants/1/users/10/lessons/100/progress" \
  -H "Content-Type: application/json" \
  -d '{"block_id":202,"status":"seen"}' | jq .

echo
echo "5) Cross-tenant safety check: tenant=1 user=20 (belongs to tenant=2) should 404"
curl -i -sS "$BASE_URL/tenants/1/users/20/lessons/100"

echo
echo "Done."
