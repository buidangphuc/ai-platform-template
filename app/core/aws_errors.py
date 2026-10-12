"""Classify AWS errors raised by the boot-time reachability probes."""

from __future__ import annotations

# The caller is authenticated and the resource is addressable, but the policy
# does not allow the probe call itself (least-privilege policies often omit
# s3:ListBucket / sqs:GetQueueAttributes). Not a misconfiguration.
_PERMISSION_DENIED_CODES = frozenset(
    {"AccessDenied", "AccessDeniedException", "AllAccessDisabled", "Forbidden"}
)


def is_permission_denied(exc: BaseException) -> bool:
    try:
        from botocore.exceptions import ClientError
    except ImportError:  # the [aws] extra is not installed: not an AWS error
        return False
    if not isinstance(exc, ClientError):
        return False
    return exc.response.get("Error", {}).get("Code") in _PERMISSION_DENIED_CODES
