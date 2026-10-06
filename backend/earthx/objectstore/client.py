"""The only module in `earthx` that imports `botocore` (adr/0015 §4.2, F2, F3).

`.importlinter` allows exactly the import `earthx.objectstore.client ->
botocore` and nothing else; a second module importing it breaks the contract.

Two clients come out of one :class:`StoreConfig`: one for the internal endpoint
(upload, delete, read the lifecycle rule) and one that only signs, for the
endpoint a browser reaches (§6.3). Signing opens no connection (§3.2).

Every `botocore` exception is translated here, because no other module may name
it. The translated message keeps the operation, the S3 error code and the HTTP
status, and drops the original text (it can name the access key id or the
endpoint, §3.2, §9.2).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, BinaryIO, TypeVar

import botocore.loaders
import botocore.session
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from earthx.objectstore.config import StoreConfig
from earthx.objectstore.errors import ResultNotFound, StoreDenied, StoreUnavailable, redact

# Plan M4-06 F6: the store sits in the same network, so a connection that does not
# come up in 5 s will not; a read gets botocore's own default of 60 s
# (`botocore/endpoint.py` DEFAULT_TIMEOUT). Three attempts in all, in standard mode
# (§5) — `total_max_attempts`, because botocore's `max_attempts` leaves out the first.
CONNECT_TIMEOUT_S = 5
READ_TIMEOUT_S = 60
MAX_ATTEMPTS = 3

_DENIED_CODES = frozenset({"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "Forbidden"})
_MISSING_CODES = frozenset({"NoSuchKey", "NotFound", "NoSuchUpload"})
_NO_LIFECYCLE = "NoSuchLifecycleConfiguration"

T = TypeVar("T")


def _botocore_config(config: StoreConfig) -> Config:
    return Config(
        signature_version="s3v4",
        s3={"addressing_style": config.addressing_style},
        # botocore sends checksums by default since 1.36, which not every S3
        # service understands; the whole measurement in adr/0015 ran with this (§5).
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
        connect_timeout=CONNECT_TIMEOUT_S,
        read_timeout=READ_TIMEOUT_S,
        retries={"mode": "standard", "total_max_attempts": MAX_ATTEMPTS},
        # Without this botocore takes HTTP(S)_PROXY from the environment, for the
        # internal endpoint too (measured, adr/0015 §3.2).
        proxies={},
    )


# One loader for every session: it caches the S3 service model, which costs a
# tenth of a second to read for each client otherwise. Sessions stay separate.
_LOADER = botocore.loaders.create_loader()


def _create(config: StoreConfig, endpoint: str) -> Any:
    # A bare session: no profile, no shared config file; the keys are passed
    # explicitly, so no credential resolver runs (adr/0015 §3.2).
    session = botocore.session.Session()
    session.register_component("data_loader", _LOADER)
    return session.create_client(
        "s3",
        endpoint_url=endpoint,
        region_name=config.region,
        aws_access_key_id=config.access_key,
        aws_secret_access_key=config.secret_key,
        config=_botocore_config(config),
    )


@dataclass(frozen=True)
class S3:
    """The few S3 operations the platform needs, against the one configured bucket."""

    _config: StoreConfig
    _internal: Any
    _signer: Any

    def _call(self, operation: str, call: Callable[[], T], absent_on: str | None = None) -> T | None:
        """Run `call`; `None` if the store answers with the error code `absent_on`."""
        try:
            return call()
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = str(error.get("Code", "unknown"))
            if code == absent_on:
                return None
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            message = self._redact(f"object store {operation} failed ({code}, HTTP {status})")
            if code in _DENIED_CODES or status == 403:
                raise StoreDenied(message) from None
            if code in _MISSING_CODES or status == 404:
                raise ResultNotFound(message) from None
            raise StoreUnavailable(message) from None
        except BotoCoreError as exc:
            raise StoreUnavailable(f"object store {operation} failed ({type(exc).__name__})") from None

    def _redact(self, text: str) -> str:
        return redact(text, self._config.secret_key, self._config.access_key)

    def put_object(self, key: str, body: BinaryIO, content_type: str) -> None:
        self._call(
            "PutObject",
            lambda: self._internal.put_object(Bucket=self._config.bucket, Key=key, Body=body, ContentType=content_type),
        )

    def create_multipart_upload(self, key: str, content_type: str) -> str:
        response = self._call(
            "CreateMultipartUpload",
            lambda: self._internal.create_multipart_upload(
                Bucket=self._config.bucket, Key=key, ContentType=content_type
            ),
        )
        return response["UploadId"]

    def upload_part(self, key: str, upload_id: str, number: int, body: bytes) -> str:
        response = self._call(
            "UploadPart",
            lambda: self._internal.upload_part(
                Bucket=self._config.bucket, Key=key, UploadId=upload_id, PartNumber=number, Body=body
            ),
        )
        return response["ETag"]

    def complete_multipart_upload(self, key: str, upload_id: str, etags: list[str]) -> None:
        parts = [{"PartNumber": number, "ETag": etag} for number, etag in enumerate(etags, start=1)]
        self._call(
            "CompleteMultipartUpload",
            lambda: self._internal.complete_multipart_upload(
                Bucket=self._config.bucket, Key=key, UploadId=upload_id, MultipartUpload={"Parts": parts}
            ),
        )

    def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        self._call(
            "AbortMultipartUpload",
            lambda: self._internal.abort_multipart_upload(Bucket=self._config.bucket, Key=key, UploadId=upload_id),
        )

    def list_keys(self, prefix: str) -> Iterator[str]:
        token: str | None = None
        while True:
            kwargs = {"Bucket": self._config.bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            page = self._call("ListObjectsV2", lambda kwargs=kwargs: self._internal.list_objects_v2(**kwargs))
            yield from (item["Key"] for item in page.get("Contents", []))
            token = page.get("NextContinuationToken")
            if not page.get("IsTruncated") or not token:
                return

    def list_multipart_uploads(self, prefix: str) -> list[tuple[str, str]]:
        page = self._call(
            "ListMultipartUploads",
            lambda: self._internal.list_multipart_uploads(Bucket=self._config.bucket, Prefix=prefix),
        )
        return [(upload["Key"], upload["UploadId"]) for upload in page.get("Uploads", [])]

    def delete_objects(self, keys: list[str]) -> None:
        response = self._call(
            "DeleteObjects",
            lambda: self._internal.delete_objects(
                Bucket=self._config.bucket,
                Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
            ),
        )
        errors = response.get("Errors", [])
        if errors:
            codes = sorted({str(error.get("Code", "unknown")) for error in errors})
            raise StoreUnavailable(
                self._redact(f"object store DeleteObjects failed for {len(errors)} keys ({', '.join(codes)})")
            )

    def lifecycle_rules(self) -> list[dict[str, Any]]:
        response = self._call(
            "GetBucketLifecycleConfiguration",
            lambda: self._internal.get_bucket_lifecycle_configuration(Bucket=self._config.bucket),
            absent_on=_NO_LIFECYCLE,
        )
        return [] if response is None else list(response.get("Rules", []))

    def presign_get(self, key: str, expires_in: int, content_disposition: str) -> str:
        return self._call(
            "PresignGetObject",
            lambda: self._signer.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._config.bucket,
                    "Key": key,
                    "ResponseContentDisposition": content_disposition,
                },
                ExpiresIn=expires_in,
            ),
        )


def build_clients(config: StoreConfig) -> S3:
    """Both clients for one configuration. Called only by `Store.from_environ`."""
    return S3(config, _create(config, config.endpoint), _create(config, config.public_endpoint))
