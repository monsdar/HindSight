from django.http import HttpRequest, HttpResponse


def health(_request: HttpRequest) -> HttpResponse:
    """Simple health check endpoint."""
    return HttpResponse(status=200)
