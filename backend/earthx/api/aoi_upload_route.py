"""``POST /aoi/upload``: an uploaded AOI file, checked and returned as EPSG:4326
GeoJSON (M3-06a, docs/plans/m3-06a-aoi-upload-backend.md).

Lives in `api`, not `tiler`: unlike the download route
(:func:`earthx.api.tiler.download_crop`), nothing here reads `readers`, a dataset, or
a real source through `gateway` (plan §5) — it only reads the bytes the caller sent.

**No `multipart/form-data`.** The plan's F3 recommended `UploadFile`, capped at
Starlette's own 1 MiB spool threshold, on the assumption that the threshold would
then guard file uploads too. Measured while implementing this (plan §6 Nachtrag):
Starlette's `MultiPartParser.on_part_data` only checks `max_part_size` for a part
that is *not* a file (``self._current_part.file is None``) — a file part is written
to its `SpooledTemporaryFile` with no size check of its own, so it can still spill to
a real temp file on disk regardless of any `max_part_size` we pass. Reading the raw
request body ourselves, in capped chunks, sidesteps that machinery entirely: nothing
between the socket and this function's own ``bytearray`` can write to disk.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Query, Request

from earthx.access.aoi_upload import MAX_UPLOAD_BYTES, AoiTooLarge, AoiUploadError, parse_aoi_upload

LOGGER = logging.getLogger("earthx.api.aoi_upload")

router = APIRouter()


@router.post("/aoi/upload")
async def upload_aoi(
    request: Request,
    filename: str = Query(..., description="the original file name; only its extension is read"),
) -> dict:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    started = time.monotonic()

    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_UPLOAD_BYTES:
            LOGGER.info("aoi upload rejected", extra={"reason": "too_large", "extension": extension})
            raise HTTPException(status_code=413, detail=f"upload is over the {MAX_UPLOAD_BYTES} byte cap")

    try:
        geometry = parse_aoi_upload(filename, bytes(content))
    except AoiTooLarge as error:
        LOGGER.info(
            "aoi upload rejected",
            extra={"reason": "too_large", "extension": extension, "duration_s": time.monotonic() - started},
        )
        raise HTTPException(status_code=413, detail=str(error)) from None
    except AoiUploadError as error:
        LOGGER.info(
            "aoi upload rejected",
            extra={"reason": "invalid", "extension": extension, "duration_s": time.monotonic() - started},
        )
        raise HTTPException(status_code=400, detail=str(error)) from None

    LOGGER.info(
        "aoi upload accepted",
        extra={
            "extension": extension,
            "geometry_type": geometry["type"],
            "duration_s": time.monotonic() - started,
        },
    )
    return geometry


__all__ = ["router", "upload_aoi"]
