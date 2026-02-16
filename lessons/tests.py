"""
Tests for the PAIR take-home API.

These tests run against the seeded Postgres database (models are unmanaged).
Django's TestCase wraps each test in a transaction that rolls back, so seed
data is never permanently altered.
"""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from lessons.models import UserBlockProgress
from lessons.services.assembly import (
    compute_progress_summary,
    fetch_lesson_structure,
    get_progress_map,
)
from lessons.services.progress import upsert_progress
from lessons.services.validation import (
    validate_block_in_lesson,
    validate_tenant_user_lesson,
)


ACME_TENANT = 1
GLOBEX_TENANT = 2

ALICE = 10  # tenant 1
BOB = 11  # tenant 1
CHARLIE = 20  # tenant 2

ACME_LESSON = 100  # tenant 1, blocks: 200(pos1), 201(pos2), 202(pos3)
GLOBEX_LESSON = 200  # tenant 2, blocks: 200(pos1), 202(pos2), 201(pos3)


class BaseTestCase(TestCase):
    """Clear cache before each test to avoid cross-test pollution."""

    def setUp(self):
        cache.clear()


class GetLessonTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _url(self, tenant_id, user_id, lesson_id):
        return f"/tenants/{tenant_id}/users/{user_id}/lessons/{lesson_id}"


    def test_get_acme_lesson_for_alice(self):
        """Full response structure check for Acme tenant."""
        resp = self.client.get(self._url(ACME_TENANT, ALICE, ACME_LESSON))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Lesson metadata
        lesson = data["lesson"]
        self.assertEqual(lesson["id"], ACME_LESSON)
        self.assertEqual(lesson["slug"], "ai-basics")
        self.assertEqual(lesson["title"], "AI Basics")

        # Blocks ordered by position
        blocks = data["blocks"]
        self.assertEqual(len(blocks), 3)
        self.assertEqual([b["id"] for b in blocks], [200, 201, 202])
        self.assertEqual([b["position"] for b in blocks], [1, 2, 3])

        # Variant selection: block 200 should have Acme override (id=1100)
        self.assertEqual(blocks[0]["variant"]["id"], 1100)
        self.assertEqual(blocks[0]["variant"]["tenant_id"], ACME_TENANT)

        # Block 201: no Acme override → default variant (id=1001)
        self.assertEqual(blocks[1]["variant"]["id"], 1001)
        self.assertIsNone(blocks[1]["variant"]["tenant_id"])

        # Block 202: no Acme override → default variant (id=1002)
        self.assertEqual(blocks[2]["variant"]["id"], 1002)
        self.assertIsNone(blocks[2]["variant"]["tenant_id"])

        # Progress for Alice: block 200=completed, 201=seen, 202=none
        self.assertEqual(blocks[0]["user_progress"], "completed")
        self.assertEqual(blocks[1]["user_progress"], "seen")
        self.assertIsNone(blocks[2]["user_progress"])

        # Progress summary
        summary = data["progress_summary"]
        self.assertEqual(summary["total_blocks"], 3)
        self.assertEqual(summary["seen_blocks"], 2)
        self.assertEqual(summary["completed_blocks"], 1)
        self.assertFalse(summary["completed"])

    def test_get_globex_lesson_different_block_order(self):
        """Globex lesson has same blocks but different order (200,202,201)."""
        resp = self.client.get(self._url(GLOBEX_TENANT, CHARLIE, GLOBEX_LESSON))
        self.assertEqual(resp.status_code, 200)
        blocks = resp.json()["blocks"]

        self.assertEqual([b["id"] for b in blocks], [200, 202, 201])
        self.assertEqual([b["position"] for b in blocks], [1, 2, 3])

    def test_get_globex_lesson_variant_selection(self):
        """Globex has override for block 202 (id=1200), default for others."""
        resp = self.client.get(self._url(GLOBEX_TENANT, CHARLIE, GLOBEX_LESSON))
        blocks = resp.json()["blocks"]

        # Block 200: no Globex override → default (id=1000)
        self.assertEqual(blocks[0]["variant"]["id"], 1000)
        self.assertIsNone(blocks[0]["variant"]["tenant_id"])

        # Block 202 (position 2): Globex override (id=1200)
        self.assertEqual(blocks[1]["variant"]["id"], 1200)
        self.assertEqual(blocks[1]["variant"]["tenant_id"], GLOBEX_TENANT)

    def test_get_lesson_no_progress(self):
        """Bob has no progress — all user_progress should be null."""
        resp = self.client.get(self._url(ACME_TENANT, BOB, ACME_LESSON))
        self.assertEqual(resp.status_code, 200)

        blocks = resp.json()["blocks"]
        for block in blocks:
            self.assertIsNone(block["user_progress"])

        summary = resp.json()["progress_summary"]
        self.assertEqual(summary["seen_blocks"], 0)
        self.assertEqual(summary["completed_blocks"], 0)
        self.assertIsNone(summary["last_seen_block_id"])
        self.assertFalse(summary["completed"])


    def test_user_not_in_tenant_returns_404(self):
        """Charlie (tenant 2) accessing tenant 1 → 404."""
        resp = self.client.get(self._url(ACME_TENANT, CHARLIE, ACME_LESSON))
        self.assertEqual(resp.status_code, 404)

    def test_lesson_not_in_tenant_returns_404(self):
        """Acme lesson (100) accessed via Globex tenant → 404."""
        resp = self.client.get(self._url(GLOBEX_TENANT, CHARLIE, ACME_LESSON))
        self.assertEqual(resp.status_code, 404)

    def test_nonexistent_tenant_returns_404(self):
        resp = self.client.get(self._url(999, ALICE, ACME_LESSON))
        self.assertEqual(resp.status_code, 404)

    def test_nonexistent_user_returns_404(self):
        resp = self.client.get(self._url(ACME_TENANT, 999, ACME_LESSON))
        self.assertEqual(resp.status_code, 404)

    def test_nonexistent_lesson_returns_404(self):
        resp = self.client.get(self._url(ACME_TENANT, ALICE, 999))
        self.assertEqual(resp.status_code, 404)

    def test_404_response_has_error_format(self):
        """Error responses follow the {error: {code, message}} schema."""
        resp = self.client.get(self._url(999, 999, 999))
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertIn("message", data["error"])


class PutProgressTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _url(self, tenant_id, user_id, lesson_id):
        return f"/tenants/{tenant_id}/users/{user_id}/lessons/{lesson_id}/progress"


    def test_mark_block_as_seen(self):
        """Mark an unseen block as seen."""
        resp = self.client.put(
            self._url(ACME_TENANT, BOB, ACME_LESSON),
            {"block_id": 200, "status": "seen"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["stored_status"], "seen")
        self.assertIn("progress_summary", data)

    def test_mark_block_as_completed(self):
        """Mark an unseen block directly as completed."""
        resp = self.client.put(
            self._url(ACME_TENANT, BOB, ACME_LESSON),
            {"block_id": 200, "status": "completed"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["stored_status"], "completed")


    def test_completed_does_not_downgrade_to_seen(self):
        """Alice's block 200 is completed — trying 'seen' should keep 'completed'."""
        resp = self.client.put(
            self._url(ACME_TENANT, ALICE, ACME_LESSON),
            {"block_id": 200, "status": "seen"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["stored_status"], "completed")

    def test_seen_upgrades_to_completed(self):
        """Alice's block 201 is 'seen' — upgrading to 'completed' should work."""
        resp = self.client.put(
            self._url(ACME_TENANT, ALICE, ACME_LESSON),
            {"block_id": 201, "status": "completed"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["stored_status"], "completed")


    def test_idempotent_seen(self):
        """Repeating 'seen' on an already-seen block returns same result."""
        resp = self.client.put(
            self._url(ACME_TENANT, ALICE, ACME_LESSON),
            {"block_id": 201, "status": "seen"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["stored_status"], "seen")

    def test_idempotent_completed(self):
        """Repeating 'completed' on an already-completed block returns same."""
        resp = self.client.put(
            self._url(ACME_TENANT, ALICE, ACME_LESSON),
            {"block_id": 200, "status": "completed"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["stored_status"], "completed")


    def test_progress_summary_updates_after_upsert(self):
        """Completing all blocks should set completed=true."""
        url = self._url(ACME_TENANT, ALICE, ACME_LESSON)
        # Alice: 200=completed, 201=seen. Complete 201 and 202.
        self.client.put(url, {"block_id": 201, "status": "completed"}, format="json")
        resp = self.client.put(
            url, {"block_id": 202, "status": "completed"}, format="json"
        )
        summary = resp.json()["progress_summary"]
        self.assertEqual(summary["total_blocks"], 3)
        self.assertEqual(summary["completed_blocks"], 3)
        self.assertEqual(summary["seen_blocks"], 3)
        self.assertTrue(summary["completed"])


    def test_block_not_in_lesson_returns_400(self):
        """Block 999 doesn't exist in lesson 100 → 400."""
        resp = self.client.put(
            self._url(ACME_TENANT, ALICE, ACME_LESSON),
            {"block_id": 999, "status": "seen"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_status_returns_400(self):
        resp = self.client.put(
            self._url(ACME_TENANT, ALICE, ACME_LESSON),
            {"block_id": 200, "status": "invalid"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_block_id_returns_400(self):
        resp = self.client.put(
            self._url(ACME_TENANT, ALICE, ACME_LESSON),
            {"status": "seen"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_status_returns_400(self):
        resp = self.client.put(
            self._url(ACME_TENANT, ALICE, ACME_LESSON),
            {"block_id": 200},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_empty_body_returns_400(self):
        resp = self.client.put(
            self._url(ACME_TENANT, ALICE, ACME_LESSON),
            {},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


    def test_cross_tenant_user_returns_404(self):
        resp = self.client.put(
            self._url(ACME_TENANT, CHARLIE, ACME_LESSON),
            {"block_id": 200, "status": "seen"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_cross_tenant_lesson_returns_404(self):
        resp = self.client.put(
            self._url(GLOBEX_TENANT, CHARLIE, ACME_LESSON),
            {"block_id": 200, "status": "seen"},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_400_response_has_error_format(self):
        """Validation errors follow the {error: {code, message}} schema."""
        resp = self.client.put(
            self._url(ACME_TENANT, ALICE, ACME_LESSON),
            {"block_id": 200, "status": "invalid"},
            format="json",
        )
        data = resp.json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertIn("message", data["error"])


class ValidationServiceTests(BaseTestCase):
    def test_valid_tenant_user_lesson(self):
        user, lesson = validate_tenant_user_lesson(ACME_TENANT, ALICE, ACME_LESSON)
        self.assertEqual(user.id, ALICE)
        self.assertEqual(lesson.id, ACME_LESSON)

    def test_invalid_user_raises_not_found(self):
        from rest_framework.exceptions import NotFound

        with self.assertRaises(NotFound):
            validate_tenant_user_lesson(ACME_TENANT, 999, ACME_LESSON)

    def test_user_wrong_tenant_raises_not_found(self):
        from rest_framework.exceptions import NotFound

        with self.assertRaises(NotFound):
            validate_tenant_user_lesson(ACME_TENANT, CHARLIE, ACME_LESSON)

    def test_lesson_wrong_tenant_raises_not_found(self):
        from rest_framework.exceptions import NotFound

        with self.assertRaises(NotFound):
            validate_tenant_user_lesson(GLOBEX_TENANT, CHARLIE, ACME_LESSON)

    def test_block_in_lesson_valid(self):
        structure = fetch_lesson_structure(ACME_LESSON, ACME_TENANT)
        # Should not raise
        validate_block_in_lesson(structure, ACME_LESSON, 200)

    def test_block_not_in_lesson_raises(self):
        from rest_framework.exceptions import ValidationError

        structure = fetch_lesson_structure(ACME_LESSON, ACME_TENANT)
        with self.assertRaises(ValidationError):
            validate_block_in_lesson(structure, ACME_LESSON, 999)


class AssemblyServiceTests(BaseTestCase):
    def test_fetch_lesson_structure_block_order(self):
        """Acme lesson blocks ordered by position: 200, 201, 202."""
        structure = fetch_lesson_structure(ACME_LESSON, ACME_TENANT)
        self.assertEqual(len(structure), 3)
        self.assertEqual([s["block_id"] for s in structure], [200, 201, 202])
        self.assertEqual([s["position"] for s in structure], [1, 2, 3])

    def test_fetch_lesson_structure_globex_order(self):
        """Globex lesson blocks: 200, 202, 201 (different order)."""
        structure = fetch_lesson_structure(GLOBEX_LESSON, GLOBEX_TENANT)
        self.assertEqual([s["block_id"] for s in structure], [200, 202, 201])

    def test_variant_selection_tenant_override(self):
        """Acme has override for block 200 → variant 1100."""
        structure = fetch_lesson_structure(ACME_LESSON, ACME_TENANT)
        block_200 = structure[0]
        self.assertEqual(block_200["variant_id"], 1100)
        self.assertEqual(block_200["variant_tenant_id"], ACME_TENANT)

    def test_variant_selection_falls_back_to_default(self):
        """Acme has no override for block 201 → default variant 1001."""
        structure = fetch_lesson_structure(ACME_LESSON, ACME_TENANT)
        block_201 = structure[1]
        self.assertEqual(block_201["variant_id"], 1001)
        self.assertIsNone(block_201["variant_tenant_id"])

    def test_get_progress_map(self):
        """Alice has progress on blocks 200 and 201 in Acme lesson."""
        pm = get_progress_map(ALICE, ACME_LESSON)
        self.assertEqual(pm[200], "completed")
        self.assertEqual(pm[201], "seen")
        self.assertNotIn(202, pm)

    def test_get_progress_map_empty(self):
        """Bob has no progress."""
        pm = get_progress_map(BOB, ACME_LESSON)
        self.assertEqual(pm, {})

    def test_compute_progress_summary_partial(self):
        structure = fetch_lesson_structure(ACME_LESSON, ACME_TENANT)
        progress_map = {200: "completed", 201: "seen"}
        summary = compute_progress_summary(structure, progress_map)

        self.assertEqual(summary["total_blocks"], 3)
        self.assertEqual(summary["seen_blocks"], 2)
        self.assertEqual(summary["completed_blocks"], 1)
        self.assertEqual(summary["last_seen_block_id"], 201)
        self.assertFalse(summary["completed"])

    def test_compute_progress_summary_all_completed(self):
        structure = fetch_lesson_structure(ACME_LESSON, ACME_TENANT)
        progress_map = {200: "completed", 201: "completed", 202: "completed"}
        summary = compute_progress_summary(structure, progress_map)

        self.assertEqual(summary["completed_blocks"], 3)
        self.assertEqual(summary["seen_blocks"], 3)
        self.assertTrue(summary["completed"])

    def test_compute_progress_summary_empty(self):
        structure = fetch_lesson_structure(ACME_LESSON, ACME_TENANT)
        summary = compute_progress_summary(structure, {})

        self.assertEqual(summary["seen_blocks"], 0)
        self.assertEqual(summary["completed_blocks"], 0)
        self.assertIsNone(summary["last_seen_block_id"])
        self.assertFalse(summary["completed"])

    def test_compute_progress_summary_last_seen_follows_position_order(self):
        """last_seen_block_id should be the last block (by position) with progress."""
        structure = fetch_lesson_structure(ACME_LESSON, ACME_TENANT)
        # Only block 200 (position 1) has progress
        summary = compute_progress_summary(structure, {200: "seen"})
        self.assertEqual(summary["last_seen_block_id"], 200)

        # Blocks 200 and 202 (positions 1 and 3) have progress
        summary = compute_progress_summary(structure, {200: "seen", 202: "seen"})
        self.assertEqual(summary["last_seen_block_id"], 202)


class ProgressUpsertServiceTests(BaseTestCase):
    def test_insert_new_progress(self):
        """Bob has no progress — insert 'seen' for block 200."""
        result = upsert_progress(BOB, ACME_LESSON, 200, "seen")
        self.assertEqual(result, "seen")

        row = UserBlockProgress.objects.get(
            user_id=BOB, lesson_id=ACME_LESSON, block_id=200
        )
        self.assertEqual(row.status, "seen")

    def test_insert_completed_directly(self):
        result = upsert_progress(BOB, ACME_LESSON, 200, "completed")
        self.assertEqual(result, "completed")

    def test_upgrade_seen_to_completed(self):
        """Alice's block 201 is 'seen' — upgrade to 'completed'."""
        result = upsert_progress(ALICE, ACME_LESSON, 201, "completed")
        self.assertEqual(result, "completed")

    def test_no_downgrade_completed_to_seen(self):
        """Alice's block 200 is 'completed' — should stay 'completed'."""
        result = upsert_progress(ALICE, ACME_LESSON, 200, "seen")
        self.assertEqual(result, "completed")

    def test_idempotent_same_status(self):
        """Repeating 'completed' on already-completed returns 'completed'."""
        result = upsert_progress(ALICE, ACME_LESSON, 200, "completed")
        self.assertEqual(result, "completed")

    def test_idempotent_seen_on_seen(self):
        result = upsert_progress(ALICE, ACME_LESSON, 201, "seen")
        self.assertEqual(result, "seen")
