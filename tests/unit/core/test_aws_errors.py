import pytest
from botocore.exceptions import ClientError

from app.core.aws_errors import is_permission_denied


def _error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "Probe")


@pytest.mark.parametrize(
    "code", ["AccessDenied", "AccessDeniedException", "AllAccessDisabled", "Forbidden"]
)
def test_policy_denials_are_permission_denied(code: str) -> None:
    assert is_permission_denied(_error(code)) is True


@pytest.mark.parametrize(
    "code",
    ["NoSuchBucket", "InvalidAccessKeyId", "SignatureDoesNotMatch", "403", "500"],
)
def test_misconfiguration_and_ambiguous_codes_are_not(code: str) -> None:
    assert is_permission_denied(_error(code)) is False


def test_non_aws_errors_are_not() -> None:
    assert is_permission_denied(ConnectionError("refused")) is False
