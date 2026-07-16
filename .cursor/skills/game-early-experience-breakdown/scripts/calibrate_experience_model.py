#!/usr/bin/env python3
"""Calibrate the progression/repetition model against the three references."""

from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Callable, Iterable

try:
    from .experience_adjustment import (
        ExperienceParameters,
        calculate_effective_experience,
    )
    from .runtime_utils import atomic_write_text, emit_json_error
except ImportError:
    from experience_adjustment import (
        ExperienceParameters,
        calculate_effective_experience,
    )
    from runtime_utils import atomic_write_text, emit_json_error


REFERENCE_NAMES = ("frost", "sanbing", "dark-war")
PROGRESSION_WEIGHTS = (0.4, 0.5, 0.6, 0.7, 0.8)
PENALTY_STEPS = (0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4)
PENALTY_CAPS = (0.8, 1.0, 1.2, 1.4, 1.6)
PARTIAL_RECOVERIES = (1, 2, 3)
MAX_REFERENCE_DRIFT = 0.2
REGULARIZATION_WEIGHT = 0.1
CONSERVATIVE_PRIOR = ExperienceParameters(0.6, 0.2, 1.2, 2)
PARAMETER_GRID_STEPS = ExperienceParameters(0.1, 0.05, 0.2, 1)


class CalibrationError(ValueError):
    """Raised when no candidate satisfies the reference constraints."""


@dataclass(frozen=True)
class TrendResult:
    delta: float
    direction: str
    base_scores_unchanged: bool = True


@dataclass(frozen=True)
class CalibrationReference:
    name: str
    old_delta: float
    evaluate: Callable[[ExperienceParameters], TrendResult]


@dataclass(frozen=True)
class ReferenceResult:
    name: str
    old_delta: float
    new_delta: float
    direction: str
    base_scores_unchanged: bool


@dataclass(frozen=True)
class CalibrationSelection:
    parameters: ExperienceParameters
    reference_names: tuple[str, ...]
    results: tuple[ReferenceResult, ...]
    loss: float


def parameter_grid() -> list[ExperienceParameters]:
    """Return the immutable design grid in deterministic order."""
    return [
        ExperienceParameters(*values)
        for values in product(
            PROGRESSION_WEIGHTS,
            PENALTY_STEPS,
            PENALTY_CAPS,
            PARTIAL_RECOVERIES,
        )
    ]


def _candidate_results(
    candidate: ExperienceParameters,
    references: Iterable[CalibrationReference],
) -> tuple[ReferenceResult, ...]:
    results = []
    for reference in references:
        trend = reference.evaluate(candidate)
        results.append(ReferenceResult(
            name=reference.name,
            old_delta=float(reference.old_delta),
            new_delta=float(trend.delta),
            direction=trend.direction,
            base_scores_unchanged=trend.base_scores_unchanged,
        ))
    return tuple(results)


def _constraint_error(results: tuple[ReferenceResult, ...]) -> str:
    failures = []
    for result in results:
        drift = abs(result.new_delta - result.old_delta)
        if result.direction != "rising":
            failures.append(f"{result.name} direction={result.direction}")
        if drift > MAX_REFERENCE_DRIFT + 1e-12:
            failures.append(
                f"{result.name} delta drift {drift:.3f} exceeds 0.2"
            )
        if not result.base_scores_unchanged:
            failures.append(f"{result.name} base scores changed")
    return "; ".join(failures)


def choose_parameters(
    candidates: Iterable[ExperienceParameters],
    references: Iterable[CalibrationReference],
) -> CalibrationSelection:
    """Choose the lowest regularized-loss candidate from approved references."""
    allowed = {
        reference.name: reference
        for reference in references
        if reference.name in REFERENCE_NAMES
    }
    ordered = tuple(allowed[name] for name in REFERENCE_NAMES if name in allowed)
    viable = []
    first_failure = ""
    for candidate in candidates:
        results = _candidate_results(candidate, ordered)
        failure = _constraint_error(results)
        if failure:
            if not first_failure:
                first_failure = failure
            continue
        if tuple(reference.name for reference in ordered) != REFERENCE_NAMES:
            missing = [name for name in REFERENCE_NAMES if name not in allowed]
            raise CalibrationError(
                "calibration references missing: " + ", ".join(missing)
            )
        drift_loss = sum(
            (result.new_delta - result.old_delta) ** 2
            for result in results
        )
        prior_loss = sum(
            (
                (getattr(candidate, field) - getattr(CONSERVATIVE_PRIOR, field))
                / getattr(PARAMETER_GRID_STEPS, field)
            ) ** 2
            for field in (
                "progression_weight",
                "penalty_step",
                "penalty_cap",
                "partial_recovery",
            )
        )
        loss = drift_loss + REGULARIZATION_WEIGHT * prior_loss
        viable.append((loss, candidate, results))
    if not viable:
        raise CalibrationError(
            "no calibration candidate satisfies rising and 0.2 drift constraints"
            + (f": {first_failure}" if first_failure else "")
        )
    loss, parameters, results = min(
        viable,
        key=lambda item: (
            item[0],
            item[1].progression_weight,
            item[1].penalty_step,
            item[1].penalty_cap,
            item[1].partial_recovery,
        ),
    )
    return CalibrationSelection(
        parameters=parameters,
        reference_names=REFERENCE_NAMES,
        results=results,
        loss=loss,
    )


def _linear_trend(observations, prediction_times) -> tuple[float, str]:
    if not observations:
        return 0.0, "flat"
    mean_time = sum(item[0] for item in observations) / len(observations)
    mean_score = sum(item[1] for item in observations) / len(observations)
    variance = sum((item[0] - mean_time) ** 2 for item in observations)
    covariance = sum(
        (item[0] - mean_time) * (item[1] - mean_score)
        for item in observations
    )
    slope = covariance / variance if variance else 0.0
    intercept = mean_score - slope * mean_time

    def predict(time):
        return min(5.0, max(0.0, slope * time + intercept))

    delta = predict(prediction_times[-1]) - predict(prediction_times[0])
    direction = "rising" if delta >= 0.5 else "falling" if delta <= -0.5 else "flat"
    return delta, direction


def evaluate_reference(
    analysis: dict,
    context: dict,
    parameters: ExperienceParameters,
) -> TrendResult:
    slices = analysis["slices"]
    source_points = analysis["global_curves"]["points"]
    context_points = context.get("points")
    if not isinstance(context_points, list):
        raise CalibrationError("context.points must be an array")
    indices = [
        item.get("slice_index") if isinstance(item, dict) else None
        for item in context_points
    ]
    if indices != list(range(len(slices))) or len(source_points) != len(slices):
        raise CalibrationError(
            "context points must continuously cover every analysis slice"
        )

    points = copy.deepcopy(source_points)
    base_scores = [point["experience"]["score"] for point in points]
    for point, annotation in zip(points, context_points):
        experience = point["experience"]
        experience["progression_pull"] = copy.deepcopy(
            annotation["progression_pull"]
        )
        experience["repetition_context"] = copy.deepcopy(
            annotation["repetition_context"]
        )
    derived = calculate_effective_experience(points, parameters)

    slg_entry = next(
        (
            item
            for item in analysis.get("timeline_milestones", [])
            if item.get("type") == "slg_entry"
        ),
        None,
    )
    end_index = int(slg_entry["slice_index"]) if slg_entry else len(slices) - 1
    end_time = (
        float(slg_entry["timestamp"])
        if slg_entry
        else float(analysis["video"]["duration_seconds"])
    )
    stages = {}
    for index in range(end_index + 1):
        stage = slices[index]["stage_range"]
        stage_id = str(stage["stage_id"])
        if stage_id not in stages:
            stages[stage_id] = {
                "time": (
                    float(stage["start"])
                    + min(float(stage["end"]), end_time)
                ) / 2,
                "scores": [],
            }
        stages[stage_id]["scores"].append(derived[index]["effective_score"])
    observations = [
        (stage["time"], sum(stage["scores"]) / len(stage["scores"]))
        for stage in stages.values()
    ]
    first_time = (
        float(source_points[0]["start"]) + float(source_points[0]["end"])
    ) / 2
    delta, direction = _linear_trend(observations, (first_time, end_time))
    unchanged = base_scores == [
        point["experience"]["score"] for point in points
    ]
    return TrendResult(delta, direction, unchanged)


def load_reference(spec: str) -> CalibrationReference:
    try:
        name, payload = spec.split("=", 1)
        analysis_name, context_name, old_delta_text = payload.rsplit(",", 2)
        analysis = json.loads(Path(analysis_name).read_text(encoding="utf-8"))
        context = json.loads(Path(context_name).read_text(encoding="utf-8"))
        old_delta = float(old_delta_text)
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"invalid --reference {spec!r}: {exc}") from exc
    return CalibrationReference(
        name=name,
        old_delta=old_delta,
        evaluate=lambda parameters: evaluate_reference(
            analysis, context, parameters
        ),
    )


def load_calibration_references(
    specs: Iterable[str],
) -> list[CalibrationReference]:
    """Load only the three approved references, before touching any paths."""
    approved_specs = [
        spec
        for spec in specs
        if spec.partition("=")[0] in REFERENCE_NAMES
    ]
    return [load_reference(spec) for spec in approved_specs]


def selection_payload(selection: CalibrationSelection) -> dict:
    parameters = selection.parameters
    return {
        "version": "progression-repetition-v1",
        "status": "locked",
        "reference_names": list(selection.reference_names),
        "constraints_passed": True,
        "loss": selection.loss,
        "parameters": {
            "progression_weight": parameters.progression_weight,
            "penalty_step": parameters.penalty_step,
            "penalty_cap": parameters.penalty_cap,
            "partial_recovery": parameters.partial_recovery,
        },
        "references": [
            {
                "name": result.name,
                "old_delta": result.old_delta,
                "new_delta": result.new_delta,
                "direction": result.direction,
                "base_scores_unchanged": result.base_scores_unchanged,
            }
            for result in selection.results
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Calibrate and lock the effective experience model"
    )
    parser.add_argument("--reference", action="append", default=[])
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        references = load_calibration_references(args.reference)
        selection = choose_parameters(parameter_grid(), references)
        text = json.dumps(
            selection_payload(selection), ensure_ascii=False, indent=2
        ) + "\n"
        atomic_write_text(args.output, text)
        return 0
    except (CalibrationError, OSError, TypeError, KeyError) as exc:
        emit_json_error(exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
