"""An in-process S3 for the objectstore tests (`moto`, adr/0015 §12 point 5).

`moto` answers inside botocore, before a socket is opened, so `no_network`
stays in force. It does not check signatures or per-key rights; those are
checked against the real image in `compose/objectstore/smoke.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from moto import mock_aws

from earthx.objectstore.results import Store

ENDPOINT = "http://objectstore:3900"
PUBLIC_ENDPOINT = "http://localhost:3900"
BUCKET = "earthx"
REGION = "garage"
ACCESS_KEY = "GKtestaccesskey0001"
SECRET_KEY = "test-secret-key-0000000000000000"


@pytest.fixture
def store_env(tmp_path: Path) -> dict[str, str]:
    """The environment compose gives `worker`, with the keys as files."""
    (tmp_path / "access_key").write_text(ACCESS_KEY + "\n")
    (tmp_path / "secret_key").write_text(SECRET_KEY + "\n")
    return {
        "S3_ENDPOINT": ENDPOINT,
        "S3_PUBLIC_ENDPOINT": PUBLIC_ENDPOINT,
        "S3_REGION": REGION,
        "S3_BUCKET": BUCKET,
        "S3_ACCESS_KEY_FILE": str(tmp_path / "access_key"),
        "S3_SECRET_KEY_FILE": str(tmp_path / "secret_key"),
    }


@pytest.fixture
def store(store_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Iterator[Store]:
    monkeypatch.setenv("MOTO_S3_CUSTOM_ENDPOINTS", ENDPOINT)
    with mock_aws():
        built = Store.from_environ(store_env)
        built.s3._internal.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
        yield built


def put_rules(store: Store, rules: list[dict]) -> None:
    store.s3._internal.put_bucket_lifecycle_configuration(Bucket=BUCKET, LifecycleConfiguration={"Rules": rules})


RESULTS_RULE = {
    "ID": "results-7d",
    "Status": "Enabled",
    "Filter": {"Prefix": "results/"},
    "Expiration": {"Days": 7},
    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
}
