from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from lessons.models import BlockVariant, LessonBlock


def _invalidate_lesson_cache(lesson_id, tenant_id):
    """Delete the cached structure for a specific lesson+tenant."""
    cache.delete(f"lesson:{tenant_id}:{lesson_id}")


@receiver([post_save, post_delete], sender=LessonBlock)
def invalidate_on_lesson_block_change(sender, instance, **kwargs):
    """A block was added/removed/reordered in a lesson — invalidate that lesson's cache."""
    _invalidate_lesson_cache(instance.lesson_id, instance.lesson.tenant_id)


@receiver([post_save, post_delete], sender=BlockVariant)
def invalidate_on_variant_change(sender, instance, **kwargs):
    """
    A variant changed — invalidate cache for every lesson containing this block.

    A default variant (tenant_id=NULL) could affect any tenant, so we invalidate
    all lessons containing the block. A tenant-specific variant only affects that
    tenant's cache entries.
    """
    lesson_blocks = LessonBlock.objects.filter(
        block_id=instance.block_id,
    ).select_related("lesson")

    for lb in lesson_blocks:
        if instance.tenant_id is not None:
            _invalidate_lesson_cache(lb.lesson_id, instance.tenant_id)
        else:
            # Default variant — invalidate for ALL tenants viewing this lesson.
            # Since a lesson belongs to exactly one tenant, this is just one key.
            _invalidate_lesson_cache(lb.lesson_id, lb.lesson.tenant_id)
