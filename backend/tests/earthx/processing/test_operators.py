"""Operator registry, schemas and applicability (adr/0014 §5.1–§5.3, K7, K8)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import BaseModel, ConfigDict

from earthx.catalog.datasets import REGISTRY as DATASETS
from earthx.catalog.registry import DataClass, LicenseTier
from earthx.processing.errors import UnknownOperator
from earthx.processing.operators import (
    JSON_SCHEMA_DIALECT,
    REGISTRY,
    Requirement,
    Tier,
    applicable,
)
from tests.earthx.processing.testops import COARSEN, SCALE, CoarsenParams, ScaleParams
from tests.earthx.processing.testops import OPERATORS as TEST_REGISTRY


class TestRegistry:
    def test_the_platform_registry_is_empty_until_m4_09_and_m4_10(self) -> None:
        assert len(REGISTRY) == 0

    def test_adding_operators_leaves_the_original_alone(self) -> None:
        assert set(TEST_REGISTRY) == {("scale", 1), ("coarsen", 1)}
        assert ("scale", 1) not in REGISTRY

    def test_it_cannot_be_changed_in_place(self) -> None:
        with pytest.raises(TypeError):
            TEST_REGISTRY[("other", 1)] = SCALE  # type: ignore[index]

    def test_the_same_operator_and_version_twice_is_refused(self) -> None:
        with pytest.raises(ValueError, match="twice"):
            TEST_REGISTRY.with_operators(SCALE)

    def test_a_new_version_is_a_new_entry(self) -> None:
        registry = TEST_REGISTRY.with_operators(replace(SCALE, op_version=2))
        assert registry.operator("scale", 2).op_version == 2
        assert registry.operator("scale", 1) is SCALE

    def test_unknown_operator_or_version_is_named(self) -> None:
        for op, version in (("nope", 1), ("scale", 3)):
            with pytest.raises(UnknownOperator):
                TEST_REGISTRY.operator(op, version)
            with pytest.raises(LookupError):
                TEST_REGISTRY.params_model(op, version)


class TestOperatorDefinition:
    @pytest.mark.parametrize(
        "change",
        [
            {"op": "Band-Math"},
            {"op": ""},
            {"op_version": 0},
            {"tiers": frozenset()},
            {"kind": "grid"},
        ],
    )
    def test_a_malformed_definition_is_refused(self, change: dict) -> None:
        with pytest.raises(ValueError):
            replace(SCALE, **change)

    def test_a_lax_parameter_model_is_refused(self) -> None:
        class Lax(BaseModel):
            factor: float

        class Open(BaseModel):
            model_config = ConfigDict(strict=True)
            factor: float

        for model in (Lax, Open):
            with pytest.raises(ValueError, match="strict"):
                replace(SCALE, params=model)

    def test_an_unknown_capability_flag_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown capability"):
            Requirement(
                capabilities=frozenset({"teleport"}), data_classes=frozenset(), license_tier=LicenseTier.PROCESSING
            )


class TestSchema:
    def test_the_schema_is_2020_12_and_closed(self) -> None:
        schema = TEST_REGISTRY.params_schema("scale", 1)
        assert schema["$schema"] == JSON_SCHEMA_DIALECT
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["factor"]
        assert schema["properties"]["factor"]["type"] == "number"

    def test_bounds_of_a_parameter_reach_the_schema(self) -> None:
        factor = TEST_REGISTRY.params_schema("coarsen", 1)["properties"]["factor"]
        assert (factor["minimum"], factor["maximum"]) == (2, 16)


class TestApplicable:
    @pytest.mark.parametrize("config", list(DATASETS), ids=lambda config: config.dataset_id)
    def test_both_test_operators_apply_to_every_registry_entry(self, config) -> None:
        assert applicable(SCALE, config, ScaleParams(factor=1.0)) == []
        assert applicable(COARSEN, config, CoarsenParams(factor=2)) == []

    def test_a_flag_the_entry_does_not_set(self) -> None:
        config = next(iter(DATASETS))
        config = replace(config, capabilities=replace(config.capabilities, reprojection=False))
        assert applicable(COARSEN, config) == [f"{config.dataset_id} does not allow reprojection"]
        assert applicable(SCALE, config) == []

    def test_a_flag_the_parameters_add(self) -> None:
        config = next(iter(DATASETS))
        config = replace(config, capabilities=replace(config.capabilities, interpolation=False))
        needs_interpolation = replace(SCALE, extra_requirements=lambda params: frozenset({"interpolation"}))
        assert applicable(needs_interpolation, config) == []
        assert applicable(needs_interpolation, config, ScaleParams(factor=1.0)) == [
            f"{config.dataset_id} does not allow interpolation"
        ]

    def test_another_data_class(self) -> None:
        config = next(iter(DATASETS))
        other = (
            DataClass.RASTER_STATIC
            if config.data_class is DataClass.RASTER_TIME_SERIES
            else DataClass.RASTER_TIME_SERIES
        )
        static_only = replace(SCALE, requires=replace(SCALE.requires, data_classes=frozenset({other})))
        assert len(applicable(static_only, config)) == 1

    @pytest.mark.parametrize("tier", [LicenseTier.CATALOG, LicenseTier.DISPLAY])
    def test_a_licence_below_processing(self, tier: LicenseTier) -> None:
        config = next(iter(DATASETS))
        # A catalogue-only entry is never displayed, so it carries no viewer (B11).
        shown = {} if tier is LicenseTier.DISPLAY else {"viewer": None, "default_render": None}
        config = replace(config, license=replace(config.license, tier=tier), **shown)
        assert applicable(SCALE, config) == [f"the licence of {config.dataset_id} does not allow processing"]


def test_tiers_are_t1_and_t2_only() -> None:
    assert {tier.value for tier in Tier} == {"T1", "T2"}
