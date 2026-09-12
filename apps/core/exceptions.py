"""
SRS Section 17 (Error and Exception Handling): 'API errors should return
proper HTTP status codes and readable messages... Show clear user-facing
messages without exposing technical details.'
"""
import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from apps.core.business_rules import BusinessRuleError

logger = logging.getLogger("django.request")


def api_exception_handler(exc, context):
    if isinstance(exc, BusinessRuleError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    response = exception_handler(exc, context)
    if response is not None:
        return response

    # Unhandled exception: never leak internals to the client (SRS 17).
    logger.exception("Unhandled server error")
    return Response(
        {"detail": "Unable to complete the request. Please try again."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
