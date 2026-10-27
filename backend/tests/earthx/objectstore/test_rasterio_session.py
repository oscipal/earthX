"""rasterio without an AWS session in the test process, `moto` untouched (NM4-23).

`backend/tests/conftest.py` clears `rasterio.session.boto3`, so rasterio takes the
path it takes in the image, where `boto3` is missing. These tests hold the two
halves of that apart: rasterio builds no `AWSSession`, and `boto3`, `botocore`
and the `moto` bucket behind the store are exactly as before.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import rasterio
import rasterio.session
from rasterio.session import DummySession, Session

from earthx.objectstore.results import Store


def test_rasterio_opens_no_aws_session_in_the_test_process() -> None:
    assert rasterio.session.boto3 is None
    assert type(Session.from_environ()) is DummySession
    with rasterio.Env() as env:
        assert type(env.session) is DummySession


def test_boto3_and_botocore_are_still_importable_for_moto() -> None:
    import boto3
    import botocore.session

    assert sys.modules["boto3"] is boto3 and boto3.__spec__ is not None
    assert botocore.session.get_session() is not None


def test_the_store_still_reaches_the_moto_bucket_inside_a_rasterio_env(store: Store, tmp_path: Path) -> None:
    body = tmp_path / "body.txt"
    body.write_bytes(b"synthetic")
    with rasterio.Env(), body.open("rb") as handle:
        store.s3.put_object("results/probe/body.txt", handle, "text/plain")
        assert list(store.s3.list_keys("results/")) == ["results/probe/body.txt"]


def test_without_the_conftest_this_environment_would_open_an_aws_session() -> None:
    """The counter-check: a plain process on the same interpreter still finds `boto3`."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("AWS_")}
    env["AWS_EC2_METADATA_DISABLED"] = "true"
    code = "from rasterio.session import Session; print(type(Session.from_environ()).__name__)"
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "AWSSession"
