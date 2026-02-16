from django.core.cache import cache
from django.db.models import F, Q

from lessons.models import BlockVariant, LessonBlock, UserBlockProgress

STRUCTURE_CACHE_TTL = 300  # 5 minutes


def fetch_lesson_structure(lesson_id, tenant_id):
    """
    Fetch lesson structure: ordered blocks with their best variant.


      1. LessonBlock rows with block_type (via FK join), ordered by position
      2. All relevant BlockVariants for these blocks (tenant-specific + defaults)

    Then merge in Python: for each block pick tenant override if exists, else default.
    """
    blocks = list(
        LessonBlock.objects.filter(lesson_id=lesson_id)
        .annotate(block_type=F("block__block_type"))
        .order_by("position")
        .values("block_id", "block_type", "position")
    )

    if not blocks:
        return []

    block_ids = [b["block_id"] for b in blocks]

    variants = list(
        BlockVariant.objects.filter(block_id__in=block_ids)
        .filter(Q(tenant_id=tenant_id) | Q(tenant_id__isnull=True))
        .values("id", "block_id", "tenant_id", "data")
    )

    # Build lookup: tenant override wins over default
    variant_map = {}
    for v in variants:
        bid = v["block_id"]
        if v["tenant_id"] is None:
            variant_map.setdefault(bid, v)
        else:
            variant_map[bid] = v

    structure = []
    for b in blocks:
        v = variant_map.get(b["block_id"], {})
        structure.append(
            {
                "block_id": b["block_id"],
                "block_type": b["block_type"],
                "position": b["position"],
                "variant_id": v.get("id"),
                "variant_tenant_id": v.get("tenant_id"),
                "variant_data": v.get("data"),
            }
        )

    return structure


def get_lesson_structure(lesson_id, tenant_id):
    """
    Return lesson structure, served from cache when available.

    Lesson structure (blocks + variants) is shared across all users in a
    tenant and rarely changes, so caching avoids redundant DB hits when
    multiple users view the same lesson.
    """
    cache_key = f"lesson:{tenant_id}:{lesson_id}"
    structure = cache.get(cache_key)
    if structure is None:
        structure = fetch_lesson_structure(lesson_id, tenant_id)
        cache.set(cache_key, structure, STRUCTURE_CACHE_TTL)
    return structure


def get_progress_map(user_id, lesson_id):
    """Fetch user progress as {block_id: status} dict. Single query."""
    return dict(
        UserBlockProgress.objects.filter(
            user_id=user_id,
            lesson_id=lesson_id,
        ).values_list("block_id", "status")
    )


def compute_progress_summary(structure, progress_map):
    """
    Compute progress_summary from structure and progress map.

    structure: list of dicts with 'block_id' key, ordered by position.
    progress_map: {block_id: status}
    """
    total = len(structure)
    seen = 0
    completed = 0
    last_seen_block_id = None

    for block in structure:
        status = progress_map.get(block["block_id"])
        if status is not None:
            seen += 1
            last_seen_block_id = block["block_id"]
            if status == "completed":
                completed += 1

    return {
        "total_blocks": total,
        "seen_blocks": seen,
        "completed_blocks": completed,
        "last_seen_block_id": last_seen_block_id,
        "completed": total > 0 and completed == total,
    }


def assemble_lesson(lesson, tenant_id, user_id):
    """
    Assemble the full lesson response.
    Cache hit: 1 query (progress).  Cache miss: 3 queries.
    """
    structure = get_lesson_structure(lesson.id, tenant_id)
    progress_map = get_progress_map(user_id, lesson.id)

    block_list = []
    for row in structure:
        block_list.append(
            {
                "id": row["block_id"],
                "type": row["block_type"],
                "position": row["position"],
                "variant": {
                    "id": row["variant_id"],
                    "tenant_id": row["variant_tenant_id"],
                    "data": row["variant_data"],
                },
                "user_progress": progress_map.get(row["block_id"]),
            }
        )

    return {
        "lesson": {
            "id": lesson.id,
            "slug": lesson.slug,
            "title": lesson.title,
        },
        "blocks": block_list,
        "progress_summary": compute_progress_summary(structure, progress_map),
    }
