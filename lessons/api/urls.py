from django.urls import path

from lessons.api.views import LessonDetailView, ProgressUpsertView

urlpatterns = [
    path(
        "tenants/<int:tenant_id>/users/<int:user_id>/lessons/<int:lesson_id>",
        LessonDetailView.as_view(),
        name="lesson-detail",
    ),
    path(
        "tenants/<int:tenant_id>/users/<int:user_id>/lessons/<int:lesson_id>/progress",
        ProgressUpsertView.as_view(),
        name="progress-upsert",
    ),
]
