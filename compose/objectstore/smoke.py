#!/usr/bin/env python3
"""CI-only smoke test for the `objectstore` (Garage) service (M3-23, adr/0012 §9).

Confirms against the *official* image what adr/0012 could only measure at
self-built binaries: PutObject/GetObject, multipart, presigned URLs,
lifecycle rules and a GDAL range-read all work. Runs only in the
`compose-topology` CI job, never in a cloud session (no Docker daemon there,
adr/0002 §1) and never as part of `pytest` (`backend/tests/compose` covers
`bootstrap.py` itself, without a running Garage).

Throwaway credentials and a throwaway CI-only endpoint only; nothing here
touches a real data source or the `gateway` allowlist.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
import urllib.request
from urllib.error import HTTPError

import boto3
import numpy as np
import rasterio
from botocore.client import Config
from botocore.exceptions import ClientError

OBJECT_KEY = "smoke/native.tif"
PERSISTED_KEY = "smoke/persisted.txt"


def _client(access_key: str, secret_key: str, endpoint: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="garage",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _synthetic_cog() -> bytes:
    """A tiny, tiled, two-overview COG (adr/0012 §12.4)."""
    data = np.arange(256 * 256, dtype="uint16").reshape(256, 256)
    buf = io.BytesIO()
    with rasterio.io.MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=256,
            width=256,
            count=1,
            dtype="uint16",
            crs="EPSG:4326",
            transform=rasterio.transform.from_bounds(0, 0, 1, 1, 256, 256),
            tiled=True,
            blockxsize=64,
            blockysize=64,
            compress="deflate",
        ) as dst:
            dst.write(data, 1)
            dst.build_overviews([2, 4], rasterio.enums.Resampling.nearest)
        buf.write(mem.read())
    return buf.getvalue()


def check(label: str, condition: bool) -> None:
    print(f"[{'ok' if condition else 'FAIL'}] {label}")
    if not condition:
        raise SystemExit(f"smoke check failed: {label}")


def run_full_suite(s3, bucket: str, access_key: str, secret_key: str, endpoint: str) -> None:
    payload = os.urandom(1024 * 1024)
    s3.put_object(Bucket=bucket, Key="smoke/plain.bin", Body=payload)
    check("PutObject", True)

    mp = s3.create_multipart_upload(Bucket=bucket, Key="smoke/multipart.bin")
    upload_id = mp["UploadId"]
    parts = []
    for i, size in enumerate((5 * 1024 * 1024, 5 * 1024 * 1024, 4000), start=1):
        part = s3.upload_part(
            Bucket=bucket, Key="smoke/multipart.bin", UploadId=upload_id,
            PartNumber=i, Body=os.urandom(size),
        )
        parts.append({"PartNumber": i, "ETag": part["ETag"]})
    s3.complete_multipart_upload(
        Bucket=bucket, Key="smoke/multipart.bin", UploadId=upload_id,
        MultipartUpload={"Parts": parts},
    )
    size = s3.head_object(Bucket=bucket, Key="smoke/multipart.bin")["ContentLength"]
    check("Multipart upload (three parts)", size == 5 * 1024 * 1024 * 2 + 4000)

    mp2 = s3.create_multipart_upload(Bucket=bucket, Key="smoke/aborted.bin")
    s3.abort_multipart_upload(Bucket=bucket, Key="smoke/aborted.bin", UploadId=mp2["UploadId"])
    check("Multipart abort", True)

    resp = s3.get_object(Bucket=bucket, Key="smoke/plain.bin", Range="bytes=100-199")
    check("Range GetObject -> 206", resp["ResponseMetadata"]["HTTPStatusCode"] == 206)
    check("Range content matches", resp["Body"].read() == payload[100:200])

    get_url = s3.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": "smoke/plain.bin"}, ExpiresIn=60
    )
    req = urllib.request.Request(get_url, headers={"Range": "bytes=0-9"})
    with urllib.request.urlopen(req) as resp:
        check("Presigned GET with Range", resp.read() == payload[:10])

    put_url = s3.generate_presigned_url(
        "put_object", Params={"Bucket": bucket, "Key": "smoke/presigned-put.bin"}, ExpiresIn=60
    )
    body = b"presigned put payload"
    urllib.request.urlopen(urllib.request.Request(put_url, data=body, method="PUT"))
    check(
        "Presigned PUT",
        s3.get_object(Bucket=bucket, Key="smoke/presigned-put.bin")["Body"].read() == body,
    )

    expiring_url = s3.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": "smoke/plain.bin"}, ExpiresIn=1
    )
    time.sleep(2.5)
    try:
        urllib.request.urlopen(expiring_url)
        rejected = False
    except HTTPError as exc:
        rejected = exc.code in (400, 403)
    check("Expired presigned URL rejected (400 or 403, adr/0012 §4.1)", rejected)

    other_key_s3 = _client("wrong-access-key-00", "wrong-secret-key-0000000000000", endpoint)
    try:
        other_key_s3.head_object(Bucket=bucket, Key="smoke/plain.bin")
        forbidden = False
    except ClientError as exc:
        forbidden = exc.response["ResponseMetadata"]["HTTPStatusCode"] == 403
    check("Unknown key rejected with 403", forbidden)

    try:
        urllib.request.urlopen(f"{endpoint}/{bucket}/smoke/plain.bin")
        anon_rejected = False
    except HTTPError as exc:
        anon_rejected = exc.code in (401, 403)
    check("Anonymous GET without a policy rejected", anon_rejected)

    s3.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "expire-results",
                    "Status": "Enabled",
                    "Filter": {"Prefix": "smoke/"},
                    "Expiration": {"Days": 1},
                    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
                }
            ]
        },
    )
    rules = s3.get_bucket_lifecycle_configuration(Bucket=bucket)["Rules"]
    check("Lifecycle rule accepted and read back", any(r["ID"] == "expire-results" for r in rules))

    listing = s3.list_objects_v2(Bucket=bucket, Prefix="smoke/")
    keys = {o["Key"] for o in listing.get("Contents", [])}
    check("ListObjectsV2 sees written objects", "smoke/plain.bin" in keys)

    s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": "smoke/aborted.bin"}]})
    listing = s3.list_objects_v2(Bucket=bucket, Prefix="smoke/aborted.bin")
    check("DeleteObjects removed the key", "Contents" not in listing)

    cog_bytes = _synthetic_cog()
    s3.put_object(Bucket=bucket, Key=OBJECT_KEY, Body=cog_bytes)
    with rasterio.Env(
        AWS_ACCESS_KEY_ID=access_key,
        AWS_SECRET_ACCESS_KEY=secret_key,
        AWS_S3_ENDPOINT=endpoint.split("://", 1)[1],
        AWS_HTTPS="NO",
        AWS_VIRTUAL_HOSTING="FALSE",
    ):
        with rasterio.open(f"/vsis3/{bucket}/{OBJECT_KEY}") as src:
            window = src.read(1, window=rasterio.windows.Window(0, 0, 32, 32))
            check("GDAL /vsis3/ window read", window.shape == (32, 32))
            check("GDAL /vsis3/ overview present", src.overviews(1) == [2, 4])

    presigned_get = s3.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": OBJECT_KEY}, ExpiresIn=60
    )
    with rasterio.open(f"/vsicurl/{presigned_get}") as src:
        window = src.read(1, window=rasterio.windows.Window(0, 0, 16, 16))
        check("GDAL /vsicurl/ presigned window read", window.shape == (16, 16))


def write_persisted_marker(s3, bucket: str) -> None:
    s3.put_object(Bucket=bucket, Key=PERSISTED_KEY, Body=b"written on the first compose start")


def check_persisted_marker(s3, bucket: str) -> None:
    body = s3.get_object(Bucket=bucket, Key=PERSISTED_KEY)["Body"].read()
    check(
        "Object written before the restart is still there",
        body == b"written on the first compose start",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--persisted", action="store_true",
        help="Only check that a volume survived a restart; run after `--write-marker`.",
    )
    parser.add_argument("--write-marker", action="store_true", help="Write the persistence marker.")
    args = parser.parse_args()

    endpoint = os.environ.get("OBJECTSTORE_ENDPOINT", "http://localhost:3900")
    access_key = os.environ["S3_ACCESS_KEY"]
    secret_key = os.environ["S3_SECRET_KEY"]
    bucket = os.environ["S3_BUCKET"]
    s3 = _client(access_key, secret_key, endpoint)

    if args.persisted:
        check_persisted_marker(s3, bucket)
        return 0

    run_full_suite(s3, bucket, access_key, secret_key, endpoint)
    if args.write_marker:
        write_persisted_marker(s3, bucket)
    print("object store smoke: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
