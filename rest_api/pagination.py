"""Shared pagination policies for KPN REST APIs."""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Stable mobile pagination with a bounded client-selectable page size."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
