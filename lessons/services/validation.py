from rest_framework.exceptions import NotFound, ValidationError

from lessons.models import Lesson, User


def validate_tenant_user_lesson(tenant_id, user_id, lesson_id):
    """
    Validate that tenant, user, and lesson exist and are properly related.

    Returns (user, lesson) tuple — tenant existence is proven implicitly
    by the user belonging to it.

    2 queries total:
      1. User by (pk, tenant_id) — proves both user and tenant exist
      2. Lesson by (pk, tenant_id) — proves lesson belongs to tenant

    Raises DRF NotFound (handled by custom_exception_handler).
    """
    try:
        user = User.objects.get(pk=user_id, tenant_id=tenant_id)
    except User.DoesNotExist:
        raise NotFound("Tenant, user, or relationship not found")

    try:
        lesson = Lesson.objects.get(pk=lesson_id, tenant_id=tenant_id)
    except Lesson.DoesNotExist:
        raise NotFound("Lesson not found in this tenant")

    return user, lesson


def validate_block_in_lesson(structure, lesson_id, block_id):
    """
    Check that block_id belongs to the lesson using the cached structure.
    Zero queries — uses the already-fetched block list.
    """
    if not any(b["block_id"] == block_id for b in structure):
        raise ValidationError(
            {"block_id": f"Block {block_id} is not part of lesson {lesson_id}"}
        )
