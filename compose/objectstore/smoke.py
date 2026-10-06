#!/usr/bin/env python3
"""CI-only smoke test for the `objectstore` (Garage) service (M3-23, adr/0012 §9; M4-06, adr/0015 §12).

Confirms against the *official* image what adr/0012 could only measure at
self-built binaries: PutObject/GetObject, multipart, presigned URLs and a
GDAL range-read all work. Since M4-06 it also confirms what `earthx.objectstore`
relies on (adr/0015 §12 point 4): the lifecycle rule for `results/` that
`objectstore-init` sets is there, the `api` key can read and sign but neither
write nor delete, a URL signed for the public endpoint works, and one signed
for the internal endpoint does not work over another host.

It only *reads* the lifecycle configuration. Writing one replaces the whole
configuration, and the worker does not start without the `results/` rule.

Runs only in the `compose-topology` CI job, never in a cloud session (no
Docker daemon there, adr/0002 §1) and never as part of `pytest`
(`backend/tests/compose` covers `bootstrap.py` itself, without a running
Garage). Uses `botocore` like the application, not `boto3` (plan M4-06 F1),
installed from `requirements-smoke.lock`.

Throwaway credentials and a throwaway CI-only endpoint only; nothing here
touches a real data source or the `gateway` allowlist. No credential reaches
the output, also not on failure: every line goes through `redact` first.
"""

from __future__ import annotations

import argparse
import io
import os
import secrets
import sys
import time
import urllib.request
from email.message import Message
from urllib.error import HTTPError

import botocore.session
import numpy as np
import rasterio
from botocore.config import Config
from botocore.exceptions import ClientError
from redact import redact

OBJECT_KEY = "smoke/native.tif"
PERSISTED_KEY = "smoke/persisted.txt"


# The address `api` and `worker` reach the store under inside the compose network.
INTERNAL_ENDPOINT = "http://objectstore:3900"
# adr/0015 §7.3, recognised by content as the worker does (plan M4-06 F4).
RESULTS_PREFIX = "results/"


def _client(access_key: str, secret_key: str, endpoint: str):
    """The same settings as `earthx/objectstore/client.py`."""
    return botocore.session.Session().create_client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="garage",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
            proxies={},
        ),
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


def run_full_suite(s3, bucket: str, endpoint: str) -> None:
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

    listing = s3.list_objects_v2(Bucket=bucket, Prefix="smoke/")
    keys = {o["Key"] for o in listing.get("Contents", [])}
    check("ListObjectsV2 sees written objects", "smoke/plain.bin" in keys)

    s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": "smoke/aborted.bin"}]})
    listing = s3.list_objects_v2(Bucket=bucket, Prefix="smoke/aborted.bin")
    check("DeleteObjects removed the key", "Contents" not in listing)

    cog_bytes = _synthetic_cog()
    s3.put_object(Bucket=bucket, Key=OBJECT_KEY, Body=cog_bytes)

    # Read over /vsicurl/ with a presigned URL rather than GDAL's direct S3
    # virtual filesystem with AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY in
    # rasterio.Env: rasterio 1.5.1 refuses those two options outright ("AWS
    # credentials are handled exclusively by boto3", CI failure on this job,
    # 26.09.2026) — GDAL's own AWS handling and boto3's must not both hold
    # credentials at once. This needs no GDAL AWS configuration at all
    # (earthx.gateway.gdal.vsicurl_path builds the same kind of path for a
    # real dataset's tile reads), and is the path M4 uses in the platform
    # itself (adr/0012 F3: signed URLs, no direct S3 credentials in the
    # reading process).
    presigned_get = s3.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": OBJECT_KEY}, ExpiresIn=60
    )
    with rasterio.open(f"/vsicurl/{presigned_get}") as src:
        window = src.read(1, window=rasterio.windows.Window(0, 0, 32, 32))
        check("GDAL /vsicurl/ presigned window read", window.shape == (32, 32))
        check("GDAL /vsicurl/ presigned overview present", src.overviews(1) == [2, 4])


def _status(call) -> int:
    try:
        call()
    except ClientError as exc:
        return exc.response["ResponseMetadata"]["HTTPStatusCode"]
    return 200


def _http_status(request: urllib.request.Request | str) -> tuple[int, Message | None]:
    """Status and headers; the headers as `Message`, which looks names up without
    regard to case (Garage sends them in lower case)."""
    try:
        with urllib.request.urlopen(request) as resp:
            resp.read()
            return resp.status, resp.headers
    except HTTPError as exc:
        return exc.code, None


def _is_results_rule(rule: dict) -> bool:
    filter_ = rule.get("Filter") or {}
    return (
        rule.get("Status") == "Enabled"
        and set(filter_) == {"Prefix"}
        and filter_["Prefix"] == RESULTS_PREFIX
        and (rule.get("Expiration") or {}).get("Days") == 7
        and (rule.get("AbortIncompleteMultipartUpload") or {}).get("DaysAfterInitiation") == 1
    )


def run_service_key_suite(jobs, api, api_internal_signer, bucket: str, endpoint: str) -> None:
    """adr/0015 §12 point 4, with the two keys `objectstore-init` created."""
    rules = api.get_bucket_lifecycle_configuration(Bucket=bucket)["Rules"]
    check("Lifecycle rule for results/ set (read with the api key)", any(_is_results_rule(r) for r in rules))

    key = f"{RESULTS_PREFIX}smoke-{secrets.token_urlsafe(8)}/result.tif"
    body = b"written by the jobs key"
    check("jobs key writes under results/", _status(lambda: jobs.put_object(Bucket=bucket, Key=key, Body=body)) == 200)

    check(
        "api key cannot write (403)",
        _status(lambda: api.put_object(Bucket=bucket, Key=f"{key}.api", Body=b"x")) == 403,
    )
    check("api key cannot delete (403)", _status(lambda: api.delete_object(Bucket=bucket, Key=key)) == 403)
    put_url = api.generate_presigned_url("put_object", Params={"Bucket": bucket, "Key": f"{key}.url"}, ExpiresIn=60)
    status, _ = _http_status(urllib.request.Request(put_url, data=b"x", method="PUT"))
    check("PUT URL signed with the api key rejected (403)", status == 403)

    get_url = api.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ResponseContentDisposition": 'attachment; filename="earthx-smoke.tif"',
        },
        ExpiresIn=60,
    )
    status, headers = _http_status(get_url)
    check("GET URL signed with the api key for the public endpoint -> 200", status == 200)
    check(
        "Content-Disposition carries the file name",
        headers is not None and headers.get("Content-Disposition") == 'attachment; filename="earthx-smoke.tif"',
    )

    internal_url = api_internal_signer.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=60
    )
    status, _ = _http_status(endpoint + internal_url.removeprefix(INTERNAL_ENDPOINT))
    check("URL signed for the internal endpoint rejected over another host (403)", status == 403)

    check("jobs key deletes", _status(lambda: jobs.delete_object(Bucket=bucket, Key=key)) == 200)


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
    credentials = [access_key, secret_key]

    try:
        s3 = _client(access_key, secret_key, endpoint)
        if args.persisted:
            check_persisted_marker(s3, bucket)
            return 0

        jobs_key = (os.environ["S3_JOBS_ACCESS_KEY"], os.environ["S3_JOBS_SECRET_KEY"])
        api_key = (os.environ["S3_API_ACCESS_KEY"], os.environ["S3_API_SECRET_KEY"])
        credentials += [*jobs_key, *api_key]
        run_full_suite(s3, bucket, endpoint)
        run_service_key_suite(
            _client(*jobs_key, endpoint),
            _client(*api_key, endpoint),
            _client(*api_key, INTERNAL_ENDPOINT),
            bucket,
            endpoint,
        )
        if args.write_marker:
            write_persisted_marker(s3, bucket)
        print("object store smoke: all checks passed")
        return 0
    except (Exception, SystemExit) as exc:
        # Last line of defence before a raw traceback would print: S3 error
        # messages never echo back the secret key, but they do sometimes echo
        # the access key id (e.g. `InvalidAccessKeyId`, Garage's `AccessDenied`),
        # and this job's log is public (the repo is public, see redact.py).
        # `SystemExit` from `check` and a missing variable (`KeyError`) go the
        # same way, so nothing unfiltered ever reaches the log.
        print(redact(f"object store smoke failed: {exc}", *credentials), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
