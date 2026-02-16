from django.db import IntegrityError, transaction
from django.utils import timezone

from lessons.models import UserBlockProgress

STATUS_RANK = {"seen": 1, "completed": 2}


def upsert_progress(user_id, lesson_id, block_id, status):
    """
    Upsert user progress for a block.

    - Idempotent
    - Monotonic: 'completed' never downgrades to 'seen'
    - Concurrency-safe: select_for_update on existing rows,
      IntegrityError retry on concurrent inserts

    Returns the stored_status after upsert.
    """
    with transaction.atomic():
        existing = (
            UserBlockProgress.objects.select_for_update()
            .filter(user_id=user_id, lesson_id=lesson_id, block_id=block_id)
            .first()
        )

        if existing is not None:
            if STATUS_RANK.get(status, 0) <= STATUS_RANK.get(existing.status, 0):
                return existing.status

            UserBlockProgress.objects.filter(
                user_id=user_id, lesson_id=lesson_id, block_id=block_id
            ).update(status=status, updated_at=timezone.now())
            return status

    # Row doesn't exist — insert outside the lock to keep the txn short.
    # Handle race: if another request inserts first, retry as update.
    try:
        with transaction.atomic():
            UserBlockProgress.objects.create(
                user_id=user_id,
                lesson_id=lesson_id,
                block_id=block_id,
                status=status,
                updated_at=timezone.now(),
            )
            return status
    except IntegrityError:
        # Concurrent insert won — fall through to update path
        return upsert_progress(user_id, lesson_id, block_id, status)
