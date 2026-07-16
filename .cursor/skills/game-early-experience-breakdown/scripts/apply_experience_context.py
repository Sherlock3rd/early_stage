#!/usr/bin/env python3
"""Apply progression and repetition context to an analysis atomically."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

try:
    from . import analysis_model
    from .experience_adjustment import (
        expected_experience_fields,
        load_locked_parameters,
    )
    from .runtime_utils import atomic_write_text, emit_json_error
except ImportError:
    import analysis_model
    from experience_adjustment import expected_experience_fields, load_locked_parameters
    from runtime_utils import atomic_write_text, emit_json_error


def _locked_model() -> dict[str, Any]:
    parameters = load_locked_parameters()
    return {
        "version": analysis_model.EXPERIENCE_MODEL_VERSION,
        "parameters": {
            "progression_weight": parameters.progression_weight,
            "penalty_step": parameters.penalty_step,
            "penalty_cap": parameters.penalty_cap,
            "partial_recovery": parameters.partial_recovery,
        },
    }


def apply_context(analysis: Any, context: Any) -> dict[str, Any]:
    """Return a validated deep copy with derived experience fields applied."""
    if not isinstance(analysis, dict):
        raise analysis_model.AnalysisValidationError("analysis 必须是对象")
    if not isinstance(context, dict) or not isinstance(context.get("points"), list):
        raise analysis_model.AnalysisValidationError("context.points 必须是数组")
    slices = analysis.get("slices")
    curves = analysis.get("global_curves")
    points = curves.get("points") if isinstance(curves, dict) else None
    if not isinstance(slices, list) or not isinstance(points, list):
        raise analysis_model.AnalysisValidationError(
            "analysis 必须包含 slices 与 global_curves.points 数组"
        )
    if len(points) != len(slices):
        raise analysis_model.AnalysisValidationError(
            "global_curves.points 数量必须与时间片数量一致"
        )

    context_points = context["points"]
    actual_indices = [
        item.get("slice_index") if isinstance(item, dict) else None
        for item in context_points
    ]
    expected_indices = list(range(len(slices)))
    if actual_indices != expected_indices:
        raise analysis_model.AnalysisValidationError(
            "context.points.slice_index 必须从 0 连续覆盖全部时间片"
        )

    migrated = copy.deepcopy(analysis)
    migrated_points = migrated["global_curves"]["points"]
    for index, context_point in enumerate(context_points):
        if not isinstance(context_point.get("progression_pull"), dict):
            raise analysis_model.AnalysisValidationError(
                f"context.points[{index}].progression_pull 必须是对象"
            )
        if not isinstance(context_point.get("repetition_context"), dict):
            raise analysis_model.AnalysisValidationError(
                f"context.points[{index}].repetition_context 必须是对象"
            )
        experience = migrated_points[index].get("experience")
        if not isinstance(experience, dict) or "score" not in experience:
            raise analysis_model.AnalysisValidationError(
                f"global_curves.points[{index}].experience.score 缺失"
            )
        experience["progression_pull"] = copy.deepcopy(
            context_point["progression_pull"]
        )
        experience["repetition_context"] = copy.deepcopy(
            context_point["repetition_context"]
        )

    expected = expected_experience_fields(
        migrated_points, load_locked_parameters()
    )
    for point, derived in zip(migrated_points, expected):
        point["experience"]["effective_score"] = derived["effective_score"]
        point["experience"]["adjustments"] = {
            key: derived[key]
            for key in (
                "progression_bonus",
                "repetition_penalty",
                "effective_repeat_count",
            )
        }
    migrated["global_curves"]["experience_model"] = _locked_model()
    analysis_model.validate_analysis(migrated)
    return migrated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="将渐进牵引与重复语境写入 analysis.json"
    )
    parser.add_argument("analysis", help="待迁移的 analysis.json")
    parser.add_argument("context", help="逐时间片体验上下文 JSON")
    parser.add_argument("--output", required=True, help="迁移后的输出路径")
    args = parser.parse_args(argv)
    try:
        analysis_path = Path(args.analysis)
        context_path = Path(args.context)
        if not analysis_path.is_file():
            raise FileNotFoundError(f"analysis.json 不存在: {analysis_path}")
        if not context_path.is_file():
            raise FileNotFoundError(f"context JSON 不存在: {context_path}")
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        context = json.loads(context_path.read_text(encoding="utf-8"))
        migrated = apply_context(analysis, context)
        text = json.dumps(migrated, ensure_ascii=False, indent=2) + "\n"
        atomic_write_text(args.output, text)
        return 0
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        analysis_model.AnalysisValidationError,
        ValueError,
        TypeError,
        KeyError,
    ) as exc:
        emit_json_error(exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
