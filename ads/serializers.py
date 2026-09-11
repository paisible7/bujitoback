import json
from datetime import datetime

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers

from parcels.media_urls import absolute_media_url
from .models import AD_SCREEN_KEYS, Advertisement


def parse_screens(value):
    if value is None or value == '':
        return ['home']
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return ['home']
        try:
            decoded = json.loads(text)
            raw = decoded if isinstance(decoded, list) else [text]
        except json.JSONDecodeError:
            raw = [s.strip() for s in text.split(',') if s.strip()]
    else:
        raw = [value]
    cleaned = []
    for item in raw:
        key = str(item).strip().lower()
        if key in AD_SCREEN_KEYS and key not in cleaned:
            cleaned.append(key)
    return cleaned or ['home']


def parse_optional_datetime(value):
    if value in (None, '', 'null'):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        dt = parse_datetime(text)
        if dt is None:
            # Accepte "YYYY-MM-DD HH:MM" / "YYYY-MM-DD"
            for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
        if dt is None:
            raise serializers.ValidationError('Date/heure invalide.')
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


class AdvertisementSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    screens = serializers.JSONField(required=False)
    starts_at = serializers.DateTimeField(
        required=False, allow_null=True, input_formats=[
            'iso-8601',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
        ],
    )
    ends_at = serializers.DateTimeField(
        required=False, allow_null=True, input_formats=[
            'iso-8601',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
        ],
    )

    class Meta:
        model = Advertisement
        fields = (
            'id', 'title', 'image', 'image_url', 'sort_order',
            'is_active', 'screens', 'starts_at', 'ends_at',
            'created_at', 'updated_at',
        )
        read_only_fields = ('created_at', 'updated_at', 'image_url')
        extra_kwargs = {
            'image': {'write_only': True, 'required': False},
        }

    def get_image_url(self, obj):
        return absolute_media_url(
            obj.image,
            self.context.get('request'),
            label=f'Ad #{obj.pk}',
        )

    def validate_screens(self, value):
        return parse_screens(value)

    def validate(self, attrs):
        starts = attrs.get(
            'starts_at',
            getattr(self.instance, 'starts_at', None) if self.instance else None,
        )
        ends = attrs.get(
            'ends_at',
            getattr(self.instance, 'ends_at', None) if self.instance else None,
        )
        if starts and ends and ends < starts:
            raise serializers.ValidationError(
                {'ends_at': 'La fin doit être après le début.'}
            )
        return attrs

    def to_internal_value(self, data):
        mutable = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'starts_at' in mutable:
            mutable['starts_at'] = parse_optional_datetime(mutable.get('starts_at'))
        if 'ends_at' in mutable:
            mutable['ends_at'] = parse_optional_datetime(mutable.get('ends_at'))
        return super().to_internal_value(mutable)

    def create(self, validated_data):
        validated_data['screens'] = parse_screens(validated_data.get('screens'))
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'screens' in validated_data:
            validated_data['screens'] = parse_screens(validated_data.get('screens'))
        return super().update(instance, validated_data)
