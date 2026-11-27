from rest_framework.pagination import PageNumberPagination
class StandardPagination(PageNumberPagination):
 page_size=20
 page_size_query_param="page_size"
 max_page_size=50

class LargeListPagination(PageNumberPagination):
    """App 2.0.5: full geographic directory lists (3 zones, 21 LGAs,
    225 wards) must come back in a single page, in the same paginated
    envelope shape as StandardPagination."""
    page_size=500
    page_size_query_param="page_size"
    max_page_size=500
