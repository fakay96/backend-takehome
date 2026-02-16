from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.views import exception_handler

from lessons.api.serializers import ProgressUpsertRequestSerializer
from lessons.services.assembly import (
    assemble_lesson,
    compute_progress_summary,
    get_lesson_structure,
    get_progress_map,
)
from lessons.services.progress import upsert_progress
from lessons.services.validation import (
    validate_block_in_lesson,
    validate_tenant_user_lesson,
)


def custom_exception_handler(exc, context):
    """
    DRF exception handler — formats all errors as:
    {"error": {"code": "...", "message": "..."}}
    """

    response = exception_handler(exc, context)
    if response is None:
        return None

    # DRF exceptions with a single 'detail' string
    if "detail" in response.data:
        response.data = {
            "error": {
                "code": getattr(exc, "default_code", "error"),
                "message": str(response.data["detail"]),
            }
        }
    elif isinstance(response.data, dict):
        # Serializer validation errors: {field: [errors]}
        messages = []
        for field, errors in response.data.items():
            for e in errors if isinstance(errors, list) else [errors]:
                messages.append(f"{field}: {e}")
        response.data = {
            "error": {
                "code": "bad_request",
                "message": "; ".join(messages),
            }
        }

    return response


class LessonDetailView(APIView):
    """GET /tenants/{tenant_id}/users/{user_id}/lessons/{lesson_id}"""

    def get(self, request, tenant_id, user_id, lesson_id):
        _user, lesson = validate_tenant_user_lesson(tenant_id, user_id, lesson_id)
        return Response(assemble_lesson(lesson, tenant_id, user_id))


class ProgressUpsertView(APIView):
    """PUT /tenants/{tenant_id}/users/{user_id}/lessons/{lesson_id}/progress"""

    def put(self, request, tenant_id, user_id, lesson_id):
        _user, lesson = validate_tenant_user_lesson(tenant_id, user_id, lesson_id)

        serializer = ProgressUpsertRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        block_id = serializer.validated_data["block_id"]
        req_status = serializer.validated_data["status"]

        # Fetch structure — used for block validation and summary
        structure = get_lesson_structure(lesson_id, tenant_id)
        validate_block_in_lesson(structure, lesson_id, block_id)

        stored_status = upsert_progress(user_id, lesson_id, block_id, req_status)

        progress_map = get_progress_map(user_id, lesson_id)

        return Response(
            {
                "stored_status": stored_status,
                "progress_summary": compute_progress_summary(structure, progress_map),
            }
        )
