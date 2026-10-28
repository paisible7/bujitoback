from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPageNumberPagination(PageNumberPagination):
    """Pagination toujours active — page_size 20 (max 100)."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# Alias rétrocompat (imports existants).
OptionalPageNumberPagination = StandardPageNumberPagination


def paginate_queryset_response(queryset, request, serializer_class, *, context=None):
    """Helper pour APIView.get — même shape DRF {count, next, previous, results}."""
    paginator = StandardPageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)
    ctx = context or {}
    if page is not None:
        serializer = serializer_class(page, many=True, context=ctx)
        return paginator.get_paginated_response(serializer.data)
    serializer = serializer_class(queryset, many=True, context=ctx)
    return Response(serializer.data)
