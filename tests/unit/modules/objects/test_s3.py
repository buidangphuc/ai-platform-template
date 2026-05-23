from app.modules.platform.objects.adapters.s3 import S3ObjectGateway


class _Body:
    def __init__(self, value: bytes) -> None:
        self.value = value

    async def read(self) -> bytes:
        return self.value


class _FakeS3Client:
    def __init__(self) -> None:
        self.put_calls: list[dict[str, object]] = []
        self.get_calls: list[dict[str, object]] = []
        self.delete_calls: list[dict[str, object]] = []
        self.head_calls: list[dict[str, object]] = []

    async def put_object(self, **kwargs: object) -> None:
        self.put_calls.append(kwargs)

    async def get_object(self, **kwargs: object) -> dict[str, object]:
        self.get_calls.append(kwargs)
        return {"Body": _Body(b"value")}

    async def delete_object(self, **kwargs: object) -> None:
        self.delete_calls.append(kwargs)

    async def head_object(self, **kwargs: object) -> None:
        self.head_calls.append(kwargs)

    def generate_presigned_url(
        self,
        operation: str,
        *,
        Params: dict[str, object],
        ExpiresIn: int,
    ) -> str:
        return f"https://signed.test/{operation}/{Params['Key']}?ttl={ExpiresIn}"


class _ClientContextManager:
    def __init__(self, client: _FakeS3Client) -> None:
        self.client = client
        self.exited = False

    async def __aenter__(self) -> _FakeS3Client:
        return self.client

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.exited = True


class _FakeSession:
    def __init__(self, client: _FakeS3Client) -> None:
        self.s3_client = client
        self.context = _ClientContextManager(client)
        self.client_calls: list[tuple[str, dict[str, object]]] = []

    def client(self, service_name: str, **kwargs: object) -> _ClientContextManager:
        self.client_calls.append((service_name, kwargs))
        return self.context


async def test_s3_object_gateway_uses_injected_session_and_custom_endpoint():
    client = _FakeS3Client()
    session = _FakeSession(client)
    gateway = S3ObjectGateway(
        bucket="bucket",
        region_name="ap-southeast-1",
        prefix="artifacts",
        endpoint_url="http://localstack:4566",
        session_factory=lambda: session,
    )

    await gateway.put("reports/output.json", b"{}", content_type="application/json")
    value = await gateway.get("reports/output.json")
    exists = await gateway.exists("reports/output.json")
    signed_url = await gateway.presign_get("reports/output.json", expires_seconds=60)
    await gateway.delete("reports/output.json")
    await gateway.close()

    assert session.client_calls == [
        (
            "s3",
            {
                "region_name": "ap-southeast-1",
                "endpoint_url": "http://localstack:4566",
            },
        )
    ]
    assert client.put_calls[0] == {
        "Bucket": "bucket",
        "Key": "artifacts/reports/output.json",
        "Body": b"{}",
        "ContentType": "application/json",
    }
    assert client.get_calls[0] == {
        "Bucket": "bucket",
        "Key": "artifacts/reports/output.json",
    }
    assert client.head_calls[0] == {
        "Bucket": "bucket",
        "Key": "artifacts/reports/output.json",
    }
    assert client.delete_calls[0] == {
        "Bucket": "bucket",
        "Key": "artifacts/reports/output.json",
    }
    assert value == b"value"
    assert exists is True
    assert (
        signed_url
        == "https://signed.test/get_object/artifacts/reports/output.json?ttl=60"
    )
    assert session.context.exited is True
