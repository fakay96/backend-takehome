from rest_framework import serializers


class ProgressUpsertRequestSerializer(serializers.Serializer):
    block_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["seen", "completed"])
