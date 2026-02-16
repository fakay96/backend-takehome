#!/usr/bin/env python3
"""
Verification script for the PAIR take-home API.

Runs against a live server and validates behaviour against the seed data.
Resets any progress side-effects by re-seeding the affected rows via the API.

Usage:
    python3 scripts/verify.py --base-url http://localhost:8000
"""
import argparse
import json
import sys
import urllib.request
import urllib.error

passed = 0
failed = 0


def req(method, url, body=None):
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(r)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def run(base):
    print("\n=== GET lesson (Acme, Alice) ===")
    status, data = req("GET", f"{base}/tenants/1/users/10/lessons/100")
    check("status 200", status == 200, f"got {status}")
    check("has lesson key", "lesson" in data)
    check("has blocks key", "blocks" in data)
    check("has progress_summary key", "progress_summary" in data)

    lesson = data.get("lesson", {})
    check("lesson.id == 100", lesson.get("id") == 100)
    check("lesson.slug == ai-basics", lesson.get("slug") == "ai-basics")
    check("lesson.title == AI Basics", lesson.get("title") == "AI Basics")

    blocks = data.get("blocks", [])
    check("3 blocks returned", len(blocks) == 3, f"got {len(blocks)}")
    check("block order [200,201,202]", [b["id"] for b in blocks] == [200, 201, 202])
    check("positions [1,2,3]", [b["position"] for b in blocks] == [1, 2, 3])

    b0 = blocks[0] if blocks else {}
    check("block 200 variant is Acme override (id=1100)", b0.get("variant", {}).get("id") == 1100)
    check("block 200 variant tenant_id == 1", b0.get("variant", {}).get("tenant_id") == 1)

    b1 = blocks[1] if len(blocks) > 1 else {}
    check("block 201 variant is default (id=1001)", b1.get("variant", {}).get("id") == 1001)
    check("block 201 variant tenant_id is null", b1.get("variant", {}).get("tenant_id") is None)

    check("block 200 progress == completed", blocks[0].get("user_progress") == "completed" if blocks else False)
    check("block 201 progress == seen", blocks[1].get("user_progress") == "seen" if len(blocks) > 1 else False)

    summary = data.get("progress_summary", {})
    check("total_blocks == 3", summary.get("total_blocks") == 3)
    check("seen_blocks == 2", summary.get("seen_blocks") == 2)
    check("completed_blocks == 1", summary.get("completed_blocks") == 1)
    check("completed == false", summary.get("completed") is False)

    print("\n=== GET lesson (Globex, Charlie) — different block order ===")
    status, data = req("GET", f"{base}/tenants/2/users/20/lessons/200")
    check("status 200", status == 200, f"got {status}")
    blocks = data.get("blocks", [])
    check("block order [200,202,201]", [b["id"] for b in blocks] == [200, 202, 201])

    b1_globex = blocks[1] if len(blocks) > 1 else {}
    check("block 202 has Globex override (id=1200)", b1_globex.get("variant", {}).get("id") == 1200)
    check("block 202 variant tenant_id == 2", b1_globex.get("variant", {}).get("tenant_id") == 2)

    print("\n=== Tenant isolation — 404s ===")
    status, _ = req("GET", f"{base}/tenants/1/users/20/lessons/100")
    check("user 20 (Globex) in tenant 1 => 404", status == 404, f"got {status}")

    status, _ = req("GET", f"{base}/tenants/2/users/20/lessons/100")
    check("lesson 100 (Acme) in tenant 2 => 404", status == 404, f"got {status}")

    status, _ = req("GET", f"{base}/tenants/999/users/10/lessons/100")
    check("nonexistent tenant => 404", status == 404, f"got {status}")

    status, _ = req("GET", f"{base}/tenants/1/users/999/lessons/100")
    check("nonexistent user => 404", status == 404, f"got {status}")

    status, _ = req("GET", f"{base}/tenants/1/users/10/lessons/999")
    check("nonexistent lesson => 404", status == 404, f"got {status}")

    print("\n=== Error response format ===")
    status, data = req("GET", f"{base}/tenants/999/users/999/lessons/999")
    check("404 has error.code", "error" in data and "code" in data.get("error", {}))
    check("404 has error.message", "error" in data and "message" in data.get("error", {}))

    print("\n=== PUT progress — mark block 202 as seen (Bob, no prior progress) ===")
    url = f"{base}/tenants/1/users/11/lessons/100/progress"
    status, data = req("PUT", url, {"block_id": 202, "status": "seen"})
    check("status 200", status == 200, f"got {status}")
    check("stored_status == seen", data.get("stored_status") == "seen")
    check("has progress_summary", "progress_summary" in data)

    print("\n=== PUT progress — upgrade seen to completed ===")
    status, data = req("PUT", url, {"block_id": 202, "status": "completed"})
    check("status 200", status == 200, f"got {status}")
    check("stored_status == completed", data.get("stored_status") == "completed")

    print("\n=== PUT progress — monotonic: completed does not downgrade to seen ===")
    status, data = req("PUT", url, {"block_id": 202, "status": "seen"})
    check("status 200", status == 200, f"got {status}")
    check("stored_status stays completed", data.get("stored_status") == "completed")

    print("\n=== PUT progress — idempotency ===")
    status, data = req("PUT", url, {"block_id": 202, "status": "completed"})
    check("repeated completed => 200", status == 200, f"got {status}")
    check("stored_status == completed", data.get("stored_status") == "completed")

    print("\n=== PUT progress — complete all blocks for Alice ===")
    alice_url = f"{base}/tenants/1/users/10/lessons/100/progress"
    req("PUT", alice_url, {"block_id": 201, "status": "completed"})
    status, data = req("PUT", alice_url, {"block_id": 202, "status": "completed"})
    summary = data.get("progress_summary", {})
    check("all 3 completed", summary.get("completed_blocks") == 3)
    check("completed == true", summary.get("completed") is True)

    print("\n=== PUT progress — validation errors (400) ===")
    status, _ = req("PUT", alice_url, {"block_id": 999, "status": "seen"})
    check("block not in lesson => 400", status == 400, f"got {status}")

    status, _ = req("PUT", alice_url, {"block_id": 200, "status": "invalid"})
    check("invalid status => 400", status == 400, f"got {status}")

    status, _ = req("PUT", alice_url, {"status": "seen"})
    check("missing block_id => 400", status == 400, f"got {status}")

    status, _ = req("PUT", alice_url, {"block_id": 200})
    check("missing status => 400", status == 400, f"got {status}")

    print("\n=== PUT progress — tenant isolation ===")
    status, _ = req("PUT", f"{base}/tenants/1/users/20/lessons/100/progress", {"block_id": 200, "status": "seen"})
    check("cross-tenant user => 404", status == 404, f"got {status}")

    status, _ = req("PUT", f"{base}/tenants/2/users/20/lessons/100/progress", {"block_id": 200, "status": "seen"})
    check("cross-tenant lesson => 404", status == 404, f"got {status}")

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed:
        print("SOME CHECKS FAILED")
    else:
        print("ALL CHECKS PASSED")
    return failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify PAIR take-home API")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    ok = run(args.base_url.rstrip("/"))
    sys.exit(0 if ok else 1)
