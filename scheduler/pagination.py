"""
Custom pagination classes for the scheduler app.
"""
from rest_framework.pagination import PageNumberPagination


class FlexiblePageNumberPagination(PageNumberPagination):
    """
    Pagination class that allows clients to specify page size via query parameter.
    This enables faster data loading for admin/data management pages that need 
    to display large datasets.
    
    Usage:
        /api/rigs/?page_size=500  - Load 500 rigs per page
        /api/wells/?page_size=1000 - Load 1000 wells per page
    """
    page_size = 100  # Default page size
    page_size_query_param = 'page_size'  # Allow client to set page size
    max_page_size = 2000  # Maximum allowed page size to prevent abuse
