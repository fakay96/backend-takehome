from django.db import models


class Tenant(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.TextField()

    class Meta:
        managed = False
        db_table = "tenants"

    def __str__(self):
        return self.name


class User(models.Model):
    id = models.IntegerField(primary_key=True)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        db_column="tenant_id",
        related_name="users",
    )
    email = models.TextField()
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "users"

    def __str__(self):
        return self.email


class Lesson(models.Model):
    id = models.IntegerField(primary_key=True)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        db_column="tenant_id",
        related_name="lessons",
    )
    slug = models.TextField()
    title = models.TextField()
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "lessons"

    def __str__(self):
        return self.title


class Block(models.Model):
    id = models.IntegerField(primary_key=True)
    block_type = models.TextField()
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "blocks"

    def __str__(self):
        return f"Block {self.id} ({self.block_type})"


class LessonBlock(models.Model):
    """
    Maps to lesson_blocks table with composite PK (lesson_id, block_id).
    We declare block as primary_key to suppress Django's auto id field.
    Always filter by lesson_id — block_id is unique within a lesson.
    """

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        db_column="lesson_id",
        related_name="lesson_blocks",
    )
    block = models.ForeignKey(
        Block,
        on_delete=models.CASCADE,
        db_column="block_id",
        primary_key=True,
        related_name="lesson_blocks",
    )
    position = models.IntegerField()

    class Meta:
        managed = False
        db_table = "lesson_blocks"
        ordering = ["position"]


class BlockVariant(models.Model):
    id = models.IntegerField(primary_key=True)
    block = models.ForeignKey(
        Block,
        on_delete=models.CASCADE,
        db_column="block_id",
        related_name="variants",
    )
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        db_column="tenant_id",
        null=True,
        blank=True,
        related_name="block_variants",
    )
    data = models.JSONField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "block_variants"


class UserBlockProgress(models.Model):
    """
    Maps to user_block_progress table with composite PK (user_id, lesson_id, block_id).
    We declare block as primary_key to suppress Django's auto id field.
    Always filter by (user_id, lesson_id) — block_id is unique within that scope.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="progress",
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        db_column="lesson_id",
        related_name="progress",
    )
    block = models.ForeignKey(
        Block,
        on_delete=models.CASCADE,
        db_column="block_id",
        primary_key=True,
        related_name="progress",
    )
    status = models.TextField()  # 'seen' or 'completed'
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "user_block_progress"
