"""DS-04 plan §4.4, §4.7: the notices of a dataset travel into recipe.json and ATTRIBUTION.txt, never into a hash;
and Sentinel-1 GRD takes the operators of adr/0018 §4.4 only. Synthetic and offline."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from earthx.access.download import build_notice_text
from earthx.api.intake import job_recipe_json, recipe_notices
from earthx.catalog.registry import AcquisitionYears
from earthx.processing.export import Attachments, AttachmentsInvalid
from earthx.processing.recipe import Provenance, RecipeNotice, job_recipe_document
from earthx.runner.output import provenance_document
from tests.catalog.entries import SENTINEL_1_GRD, SENTINEL_2_L2A
from tests.earthx.api.test_intake import Source, band_math, order, refused
from tests.earthx.api.test_intake_checksum import INSIDE, accept, answer, s1_item

NOTICES = [
    ("Approximate geolocation", SENTINEL_1_GRD.notices[0].tooltip),
    ("Uncalibrated (DN)", SENTINEL_1_GRD.notices[1].tooltip),
]
BODY = {"recipe_version": 2, "recipe_id": "r", "inputs": [], "steps": []}
AT = datetime(2026, 11, 8, tzinfo=UTC)
YEARS = AcquisitionYears(2026, 2026)


def provenance_of(document: bytes) -> dict[str, Any]:
    return json.loads(document)["provenance"]


class TestAttributionTxt:
    def test_each_notice_is_a_paragraph_of_its_own_and_nothing_else_changes(self) -> None:
        text = build_notice_text(SENTINEL_1_GRD, item_ids=["S1_A"], years=YEARS, at=AT)
        without = build_notice_text(replace(SENTINEL_1_GRD, notices=()), item_ids=["S1_A"], years=YEARS, at=AT)
        added = [f"{label}: {tooltip}" for label, tooltip in NOTICES]
        assert [paragraph for paragraph in text.split("\n\n") if paragraph not in added] == without.split("\n\n")
        assert all(paragraph in text.split("\n\n") for paragraph in added)

    def test_a_dataset_without_notices_names_none(self) -> None:
        text = build_notice_text(SENTINEL_2_L2A, item_ids=["S2_A"], years=YEARS, at=AT)
        assert not any(label in text for label, _ in NOTICES)


class TestRecipeJson:
    def test_a_job_of_sentinel_1_names_its_notices_in_the_provenance(self) -> None:
        document = job_recipe_json(BODY, config=SENTINEL_1_GRD, result={}, started=None, finished=None, years=YEARS)
        assert [(n["label"], n["tooltip"]) for n in provenance_of(document)["notices"]] == NOTICES
        assert [n["code"] for n in provenance_of(document)["notices"]] == ["approximate_geolocation", "uncalibrated_dn"]

    def test_a_dataset_without_notices_writes_no_field(self) -> None:
        """Every recipe.json of the datasets before DS-04b stays byte for byte what it was."""
        document = job_recipe_json(BODY, config=SENTINEL_2_L2A, result={}, started=None, finished=None, years=YEARS)
        assert "notices" not in provenance_of(document)
        assert document == job_recipe_document(BODY, attribution=provenance_of(document)["attribution"], result={}, started=None, finished=None)

    def test_notices_stay_out_of_the_recipe_itself(self) -> None:
        """Auslegung A1: a consequence of the dataset, not of the order, so the recipe and its hash do not change."""
        with_notices = json.loads(
            job_recipe_json(BODY, config=SENTINEL_1_GRD, result={}, started=None, finished=None, years=YEARS)
        )
        without = json.loads(
            job_recipe_json(
                BODY, config=replace(SENTINEL_1_GRD, notices=()), result={}, started=None, finished=None, years=YEARS
            )
        )
        assert {k: v for k, v in with_notices.items() if k != "provenance"} == {
            k: v for k, v in without.items() if k != "provenance"
        }

    def test_an_old_recipe_without_notices_still_reads(self) -> None:
        document = job_recipe_document(BODY, attribution=[], result={}, started=None, finished=None)
        assert Provenance.model_validate(provenance_of(document)).notices == []

    @pytest.mark.parametrize("bad", [{"code": "x"}, {"code": "x", "label": "y", "tooltip": "z", "more": 1}, "text"])
    def test_a_malformed_notice_in_a_recipe_is_refused(self, bad: object) -> None:
        provenance = provenance_of(job_recipe_document(BODY, attribution=[], result={}, started=None, finished=None))
        with pytest.raises(ValueError):
            Provenance.model_validate({**provenance, "notices": [bad]})


class TestExportAndRunner:
    def test_the_attachments_of_an_export_carry_the_notices_there_and_back(self) -> None:
        files = {name: "x" for name in ("aoi.geojson", "citation.bib", "ATTRIBUTION.txt")}
        attachments = Attachments(files, ("a",), notices=recipe_notices(SENTINEL_1_GRD))
        assert Attachments.from_json(json.loads(json.dumps(attachments.to_json()))) == attachments
        assert "notices" not in Attachments(files, ("a",)).to_json()

    def test_malformed_notices_in_the_attachments_are_refused(self) -> None:
        files = {name: "x" for name in ("aoi.geojson", "citation.bib", "ATTRIBUTION.txt")}
        with pytest.raises(AttachmentsInvalid):
            Attachments.from_json({"files": files, "attribution": [], "notices": [{"code": "x"}]})

    def test_the_runner_keeps_the_notices_of_the_cloud_run(self) -> None:
        source = Provenance.model_validate(
            provenance_of(job_recipe_json(BODY, config=SENTINEL_1_GRD, result={}, started=None, finished=None, years=YEARS))
        )
        result = SimpleNamespace(engine={}, scaling=(), properties={})
        local = provenance_document(result, source=source, started=AT, finished=AT)  # type: ignore[arg-type]
        assert [RecipeNotice.model_validate(n) for n in local["notices"]] == source.notices


@pytest.mark.anyio
class TestOperatorsOnGrd:
    """adr/0018 §4.4, DS-04 plan F4: band math within one scene goes, masks do not."""

    async def test_band_math_on_vv_and_vh_of_one_scene_is_accepted(self) -> None:
        document = order(
            "sentinel-1-grd", (("S1_VVVH",),), ("vv", "vh"), aoi=INSIDE, steps=[band_math("vv / vh", "ratio")],
            output={"kind": "raster", "format": "cog", "dtype": "float32", "bands": ["ratio"]},
        )
        accepted = await accept(document, Source((SENTINEL_1_GRD, s1_item())), answer())
        assert [step.op for step in accepted.recipe.steps] == ["band_math"]

    @pytest.mark.parametrize(
        "step",
        [
            {"op": "mask_values", "op_version": 1, "params": {"band": "vv", "condition": "lt", "values": [50.0]}},
            {"op": "mask", "op_version": 2, "params": {"source": "scl", "classes": [3]}},
        ],
        ids=["mask by value", "mask by class"],
    )
    async def test_a_mask_is_refused(self, step: dict[str, Any]) -> None:
        document = order("sentinel-1-grd", (("S1_VVVH",),), ("vv", "vh"), aoi=INSIDE, steps=[step])
        error = await refused(document, Source((SENTINEL_1_GRD, s1_item())))
        assert error.status_code == 422
