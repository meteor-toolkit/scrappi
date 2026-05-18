"""scrappi.api - API call handler implementations.

This package contains API-specific call handler classes used by scrappi to
discover, query and download products from different catalogues and services.

Handlers should subclass `BaseAPICallHandler` and implement the required
methods `perform_query` and `download_product`.
"""
