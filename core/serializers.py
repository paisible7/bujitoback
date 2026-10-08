"""Mixins DRF pour exposer l'UUID public comme `id`."""
from __future__ import annotations

import uuid as uuid_lib


class PublicUUIDSerializerMixin:
    """
    Remplace `id` numérique par l'UUID public dans la réponse API.
    Conserve `pk` (entier interne) pour debug / admin si besoin.
    """

    public_id_field = 'uuid'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        public = getattr(instance, self.public_id_field, None)
        if public is not None:
            data['id'] = str(public)
            data['pk'] = instance.pk
        return data


def resolve_uuid_or_pk(queryset, value):
    """
    Résout un objet par UUID public ou, en secours, par PK entière.
    Compatible clients anciens pendant la transition.
    """
    text = str(value).strip()
    if not text:
        raise queryset.model.DoesNotExist()
    try:
        uid = uuid_lib.UUID(text)
        return queryset.get(uuid=uid)
    except (ValueError, TypeError, AttributeError):
        pass
    except queryset.model.DoesNotExist:
        pass

    # Image models with UUID PK
    try:
        uid = uuid_lib.UUID(text)
        return queryset.get(pk=uid)
    except (ValueError, TypeError, AttributeError, queryset.model.DoesNotExist):
        pass

    return queryset.get(pk=text)


class UUIDLookupMixin:
    """À mixer dans les APIView/GenericAPIView pour lookup uuid|pk."""

    lookup_url_kwarg = 'pk'

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        lookup = self.kwargs.get(self.lookup_url_kwarg) or self.kwargs.get('pk')
        obj = resolve_uuid_or_pk(queryset, lookup)
        self.check_object_permissions(self.request, obj)
        return obj
