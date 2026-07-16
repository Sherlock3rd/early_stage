#!/usr/bin/env python3
"""Validation and UTF-8 serialization for the unified analysis.json format."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

try:
    from .runtime_utils import atomic_write_text, emit_json_error
    from .video_timeline import generate_timeline
except ImportError:
    from runtime_utils import atomic_write_text, emit_json_error
    from video_timeline import generate_timeline


DIMENSION_KEYS = (
    "阶段目标",
    "任务链",
    "核心循环",
    "渐进体验",
    "地图体验",
    "经济体验",
    "剧情轴",
)
NARRATIVE_JUDGEMENTS = ("none", "climax", "low")
FLOW_JUDGEMENTS = ("none", "flow_peak")
CURVE_SCORE_MIN = 0.0
CURVE_SCORE_MAX = 5.0
EMOTION_VALENCES = ("positive", "negative", "mixed", "neutral")
EMOTION_DRIVERS = (
    "narrative",
    "environment_pressure",
    "urgency",
    "combat",
    "progression_reward",
    "relief",
)
EXPERIENCE_BASIS_KEYS = (
    "gameplay_concentration",
    "feedback_density",
    "goal_challenge",
    "interruption",
)
GLOBAL_LOOP_NODE_TYPES = ("micro_loop", "transition", "end", "outside_exit")
GLOBAL_LOOP_STATUSES = ("confirmed", "pending_confirmation")
GLOBAL_LOOP_ACCENTS = ("settlement", "expedition", "hero_growth")
GLOBAL_LOOP_FAMILY_ACCENTS = (
    "building_growth",
    "building_production",
    "expedition_progression",
    "hero_growth",
    "law_system",
    "heating_boost",
)
GLOBAL_LOOP_EDGE_KINDS = (
    "primary",
    "macro_return",
    "cross_macro",
    "conditional",
)
TIMELINE_MILESTONE_TYPES = ("slg_entry", "map_entry", "cg_end")


class AnalysisValidationError(ValueError):
    """Raised when analysis data does not match the required schema."""


def _fail(message: str) -> None:
    raise AnalysisValidationError(message)


def _require_object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{location} 必须是对象")
    return value


def _require_keys(value: dict[str, Any], keys: tuple[str, ...], location: str) -> None:
    missing = [key for key in keys if key not in value]
    if missing:
        _fail(f"{location} 缺少字段: {', '.join(missing)}")


def _number(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{location} 必须是数字")
    result = float(value)
    if not math.isfinite(result):
        _fail(f"{location} 必须是有限数")
    return result


def _nonempty_text(value: Any, location: str) -> None:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{location} 必须是非空文本；无内容请填写“未观察到”")


def _validate_frame(
    frame: Any,
    location: str,
    slice_start: float,
    slice_end: float,
    duration: float,
) -> None:
    frame = _require_object(frame, location)
    _require_keys(frame, ("path", "timestamp"), location)
    _nonempty_text(frame["path"], f"{location}.path")
    timestamp = _number(frame["timestamp"], f"{location}.timestamp")
    if not (slice_start <= timestamp < slice_end):
        _fail(
            f"{location}.timestamp 必须位于左闭右开时间片 "
            f"[{slice_start}, {slice_end})"
        )
    if not (0 <= timestamp < duration):
        _fail(f"{location}.timestamp 超出视频范围")


def _curve_score(value: Any, location: str) -> float:
    score = _number(value, location)
    if not CURVE_SCORE_MIN <= score <= CURVE_SCORE_MAX:
        _fail(f"{location} 必须在 0 到 5 之间")
    return score


def expected_emotion_intensity(
    narrative_score: float, supporting_score: float
) -> float:
    """Return the one-decimal narrative-dominant emotion intensity."""
    raw = 0.7 * narrative_score + 0.3 * max(
        narrative_score, supporting_score
    )
    return math.floor(raw * 10 + 0.5) / 10


def _validate_global_curves(value: Any, slices: list[Any]) -> None:
    curves = _require_object(value, "global_curves")
    _require_keys(curves, ("scale", "points"), "global_curves")
    scale = _require_object(curves["scale"], "global_curves.scale")
    _require_keys(scale, ("min", "max"), "global_curves.scale")
    actual_scale = (
        _number(scale["min"], "global_curves.scale.min"),
        _number(scale["max"], "global_curves.scale.max"),
    )
    if actual_scale != (CURVE_SCORE_MIN, CURVE_SCORE_MAX):
        _fail("global_curves.scale 必须固定为 min=0、max=5")

    points = curves["points"]
    if not isinstance(points, list):
        _fail("global_curves.points 必须是数组")
    if len(points) != len(slices):
        _fail("global_curves.points 数量必须与时间片数量一致")
    for index, (raw_point, raw_slice) in enumerate(zip(points, slices)):
        location = f"global_curves.points[{index}]"
        point = _require_object(raw_point, location)
        _require_keys(point, ("start", "end", "emotion", "experience"), location)
        start = _number(point["start"], f"{location}.start")
        end = _number(point["end"], f"{location}.end")
        if start != float(raw_slice["start"]) or end != float(raw_slice["end"]):
            _fail(f"{location} 边界必须与对应时间片完全一致")

        emotion_location = f"{location}.emotion"
        emotion = _require_object(point["emotion"], emotion_location)
        _require_keys(
            emotion,
            (
                "narrative_score",
                "supporting_score",
                "intensity",
                "valence",
                "drivers",
                "event",
                "reason",
            ),
            emotion_location,
        )
        narrative_score = _curve_score(
            emotion["narrative_score"],
            f"{emotion_location}.narrative_score",
        )
        supporting_score = _curve_score(
            emotion["supporting_score"],
            f"{emotion_location}.supporting_score",
        )
        intensity = _curve_score(
            emotion["intensity"], f"{emotion_location}.intensity"
        )
        expected_intensity = expected_emotion_intensity(
            narrative_score, supporting_score
        )
        if intensity != expected_intensity:
            _fail(
                f"{emotion_location}.intensity 必须按剧情主体公式计算为 "
                f"{expected_intensity:g}"
            )
        if emotion["valence"] not in EMOTION_VALENCES:
            _fail(
                f"{emotion_location}.valence 只允许: "
                f"{', '.join(EMOTION_VALENCES)}"
            )
        drivers = emotion["drivers"]
        if not isinstance(drivers, list):
            _fail(f"{emotion_location}.drivers 必须是数组")
        if any(
            not isinstance(driver, str) or driver not in EMOTION_DRIVERS
            for driver in drivers
        ):
            _fail(
                f"{emotion_location}.drivers 只允许: "
                f"{', '.join(EMOTION_DRIVERS)}"
            )
        if len(drivers) != len(set(drivers)):
            _fail(f"{emotion_location}.drivers 不允许重复")
        if narrative_score > 0 and "narrative" not in drivers:
            _fail(
                f"{emotion_location}.drivers 在剧情分大于 0 时必须包含 narrative"
            )
        if narrative_score == 0 and "narrative" in drivers:
            _fail(
                f"{emotion_location}.drivers 在剧情分为 0 时不得包含 narrative"
            )
        non_narrative_drivers = [
            driver for driver in drivers if driver != "narrative"
        ]
        if supporting_score > 0 and not non_narrative_drivers:
            _fail(
                f"{emotion_location}.drivers 在其他刺激分大于 0 时"
                "必须包含非剧情来源"
            )
        if supporting_score == 0 and non_narrative_drivers:
            _fail(
                f"{emotion_location}.drivers 在其他刺激分为 0 时"
                "不得包含非剧情来源"
            )
        if narrative_score == 0 and supporting_score == 0 and drivers:
            _fail(
                f"{emotion_location}.drivers 在两项子分为零时必须为空"
            )
        for field in ("event", "reason"):
            if not isinstance(emotion[field], str):
                _fail(f"{emotion_location}.{field} 必须是文本")
            if intensity > 0:
                _nonempty_text(emotion[field], f"{emotion_location}.{field}")

        experience_location = f"{location}.experience"
        experience = _require_object(point["experience"], experience_location)
        _require_keys(
            experience, ("score", "basis", "summary"), experience_location
        )
        _curve_score(experience["score"], f"{experience_location}.score")
        basis = _require_object(
            experience["basis"], f"{experience_location}.basis"
        )
        _require_keys(
            basis, EXPERIENCE_BASIS_KEYS, f"{experience_location}.basis"
        )
        for field in EXPERIENCE_BASIS_KEYS:
            _nonempty_text(
                basis[field], f"{experience_location}.basis.{field}"
            )
        _nonempty_text(
            experience["summary"], f"{experience_location}.summary"
        )


def _validate_loop_families(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        _fail("global_loops.loop_families 必须是非空数组")
    family_by_id: dict[str, dict[str, Any]] = {}
    used_accents: set[str] = set()
    for index, raw_family in enumerate(value):
        location = f"global_loops.loop_families[{index}]"
        family = _require_object(raw_family, location)
        _require_keys(family, ("id", "title", "summary", "accent"), location)
        for field in ("id", "title", "summary"):
            _nonempty_text(family[field], f"{location}.{field}")
        family_id = family["id"]
        if family_id in family_by_id:
            _fail(f"{location}.id 不允许重复")
        accent = family["accent"]
        if accent not in GLOBAL_LOOP_FAMILY_ACCENTS:
            _fail(
                f"{location}.accent 只允许: "
                f"{', '.join(GLOBAL_LOOP_FAMILY_ACCENTS)}"
            )
        if accent in used_accents:
            _fail(f"{location}.accent 不允许重复")
        family_by_id[family_id] = family
        used_accents.add(accent)
    return family_by_id


def _validate_global_loops(
    value: Any, slices: list[Any], duration: float
) -> None:
    graph = _require_object(value, "global_loops")
    _require_keys(
        graph,
        ("scope", "macro_loops", "loop_families", "nodes", "edges"),
        "global_loops",
    )
    scope = _require_object(graph["scope"], "global_loops.scope")
    _require_keys(
        scope,
        ("start", "end", "end_label", "outside_exit_label"),
        "global_loops.scope",
    )
    scope_start = _number(scope["start"], "global_loops.scope.start")
    scope_end = _number(scope["end"], "global_loops.scope.end")
    if scope_start < 0 or scope_end <= scope_start or scope_end > duration:
        _fail("global_loops.scope 必须位于视频内且 end 大于 start")
    _nonempty_text(scope["end_label"], "global_loops.scope.end_label")
    _nonempty_text(
        scope["outside_exit_label"], "global_loops.scope.outside_exit_label"
    )

    macros = graph["macro_loops"]
    if not isinstance(macros, list) or not macros:
        _fail("global_loops.macro_loops 必须是非空数组")
    macro_by_id: dict[str, dict[str, Any]] = {}
    used_accents: set[str] = set()
    for index, raw_macro in enumerate(macros):
        location = f"global_loops.macro_loops[{index}]"
        macro = _require_object(raw_macro, location)
        _require_keys(macro, ("id", "title", "accent", "summary"), location)
        for field in ("id", "title", "summary"):
            _nonempty_text(macro[field], f"{location}.{field}")
        macro_id = macro["id"]
        if macro_id in macro_by_id:
            _fail(f"{location}.id 不允许重复")
        accent = macro["accent"]
        if accent not in GLOBAL_LOOP_ACCENTS:
            _fail(
                f"{location}.accent 只允许: {', '.join(GLOBAL_LOOP_ACCENTS)}"
            )
        if accent in used_accents:
            _fail(f"{location}.accent 不允许重复")
        macro_by_id[macro_id] = macro
        used_accents.add(accent)
    family_by_id = _validate_loop_families(graph["loop_families"])

    nodes = graph["nodes"]
    if not isinstance(nodes, list) or not nodes:
        _fail("global_loops.nodes 必须是非空数组")
    node_by_id: dict[str, dict[str, Any]] = {}
    micro_fields = (
        "loop_family_id",
        "motivation",
        "behaviors",
        "reward",
        "next_motivation",
        "confidence",
    )
    node_positions: dict[str, int] = {}
    earliest_slice_index: dict[str, int] = {}
    used_family_ids: set[str] = set()
    previous_earliest = -1
    for index, raw_node in enumerate(nodes):
        location = f"global_loops.nodes[{index}]"
        node = _require_object(raw_node, location)
        _require_keys(
            node,
            (
                "id",
                "type",
                "title",
                "summary",
                "macro_loop_id",
                "slice_indices",
                "evidence_frames",
                "status",
            ),
            location,
        )
        for field in ("id", "title", "summary"):
            _nonempty_text(node[field], f"{location}.{field}")
        node_id = node["id"]
        if node_id in node_by_id:
            _fail(f"{location}.id 不允许重复")
        node_by_id[node_id] = node
        node_positions[node_id] = index
        node_type = node["type"]
        if node_type not in GLOBAL_LOOP_NODE_TYPES:
            _fail(
                f"{location}.type 只允许: {', '.join(GLOBAL_LOOP_NODE_TYPES)}"
            )
        if node["status"] not in GLOBAL_LOOP_STATUSES:
            _fail(
                f"{location}.status 只允许: {', '.join(GLOBAL_LOOP_STATUSES)}"
            )
        macro_loop_id = node["macro_loop_id"]
        if not isinstance(macro_loop_id, str):
            _fail(f"{location}.macro_loop_id 必须是文本")

        slice_indices = node["slice_indices"]
        if (
            not isinstance(slice_indices, list)
            or not slice_indices
            or any(
                isinstance(item, bool)
                or not isinstance(item, int)
                or item < 0
                or item >= len(slices)
                for item in slice_indices
            )
        ):
            _fail(f"{location}.slice_indices 必须是有效的非空时间片索引数组")
        if len(slice_indices) != len(set(slice_indices)):
            _fail(f"{location}.slice_indices 不允许重复")
        if slice_indices != sorted(slice_indices):
            _fail(f"{location}.slice_indices 必须按时间递增")
        earliest = min(slice_indices)
        if earliest < previous_earliest:
            _fail("global_loops.nodes 必须按最早关联时间片排序")
        previous_earliest = earliest
        earliest_slice_index[node_id] = earliest
        referenced_slices = [slices[item] for item in slice_indices]
        if node_type == "outside_exit":
            if not any(float(item["start"]) >= scope_end for item in referenced_slices):
                _fail(f"{location} 图外出口必须引用 scope 结束后的时间片")
        elif any(
            float(item["start"]) < scope_start
            or float(item["end"]) > scope_end
            for item in referenced_slices
        ):
            overrunning_slices = [
                item
                for item in referenced_slices
                if float(item["end"]) > scope_end
            ]
            exact_end_inside_final_slice = (
                all(float(item["start"]) >= scope_start for item in referenced_slices)
                and len(overrunning_slices) == 1
                and overrunning_slices[0] is referenced_slices[-1]
                and float(overrunning_slices[0]["start"]) < scope_end
                <= float(overrunning_slices[0]["end"])
            )
            if not exact_end_inside_final_slice:
                _fail(f"{location} 主体节点的时间片不得越过 global_loops.scope")

        evidence_frames = node["evidence_frames"]
        if not isinstance(evidence_frames, list) or not evidence_frames:
            _fail(f"{location}.evidence_frames 必须是非空数组")
        allowed_frames = {
            frame["path"]
            for item in referenced_slices
            for frame in [item["main_frame"], *item["evidence_frames"]]
        }
        for frame_index, frame in enumerate(evidence_frames):
            _nonempty_text(frame, f"{location}.evidence_frames[{frame_index}]")
            if frame not in allowed_frames:
                _fail(f"{location}.evidence_frames 证据必须属于关联时间片")

        if node_type == "micro_loop":
            if macro_loop_id not in macro_by_id:
                _fail(f"{location}.macro_loop_id 必须引用现有大 LOOP")
            _require_keys(node, micro_fields, location)
            loop_family_id = node["loop_family_id"]
            if loop_family_id not in family_by_id:
                _fail(f"{location}.loop_family_id 必须引用现有小 LOOP 类型")
            used_family_ids.add(loop_family_id)
            for field in ("motivation", "reward", "next_motivation"):
                _nonempty_text(node[field], f"{location}.{field}")
            behaviors = node["behaviors"]
            if not isinstance(behaviors, list) or not behaviors:
                _fail(f"{location}.behaviors 必须是非空行为数组")
            for behavior_index, behavior in enumerate(behaviors):
                _nonempty_text(
                    behavior, f"{location}.behaviors[{behavior_index}]"
                )
            confidence = _number(node["confidence"], f"{location}.confidence")
            if not 0 <= confidence <= 1:
                _fail(f"{location}.confidence 必须在 0 到 1 之间")
            minimum_slice_confidence = min(
                float(item["confidence"]) for item in referenced_slices
            )
            if abs(confidence - minimum_slice_confidence) > 1e-9:
                _fail(
                    f"{location}.confidence 必须等于关联时间片中的最低置信度 "
                    f"{minimum_slice_confidence:g}"
                )
        else:
            if macro_loop_id:
                _fail(f"{location} 非 micro_loop 节点的 macro_loop_id 必须为空")
            if any(field in node for field in micro_fields):
                _fail(f"{location} 只有 micro_loop 节点允许闭环字段")

    unused_family_ids = set(family_by_id) - used_family_ids
    if unused_family_ids:
        _fail(
            "global_loops.loop_families 不允许未被小 LOOP 引用的类型: "
            + ", ".join(sorted(unused_family_ids))
        )

    ends = [node["id"] for node in nodes if node["type"] == "end"]
    outside_exits = [
        node["id"] for node in nodes if node["type"] == "outside_exit"
    ]
    subject_nodes = [node for node in nodes if node["type"] != "outside_exit"]
    if not subject_nodes or len(ends) != 1:
        _fail("global_loops 必须包含主体节点且恰好包含一个主体终点")
    if subject_nodes[-1]["type"] != "end":
        _fail("global_loops 主体终点必须是最后一个主体节点")
    if len(outside_exits) > 1:
        _fail("global_loops 最多允许一个 outside_exit 图外出口")
    if outside_exits:
        first_outside_index = next(
            (
                index
                for index, item in enumerate(slices)
                if float(item["start"]) >= scope_end
            ),
            None,
        )
        outside_node = node_by_id[outside_exits[0]]
        if (
            first_outside_index is None
            or outside_node["slice_indices"] != [first_outside_index]
        ):
            _fail("outside_exit 必须只引用 scope 结束后的首个时间片")

    edges = graph["edges"]
    if not isinstance(edges, list):
        _fail("global_loops.edges 必须是数组")
    edge_keys: set[tuple[str, str, str]] = set()
    primary_pairs: set[tuple[str, str]] = set()
    for index, raw_edge in enumerate(edges):
        location = f"global_loops.edges[{index}]"
        edge = _require_object(raw_edge, location)
        _require_keys(edge, ("from", "to", "kind", "label"), location)
        for field in ("from", "to", "label"):
            _nonempty_text(edge[field], f"{location}.{field}")
        if edge["from"] not in node_by_id or edge["to"] not in node_by_id:
            _fail(f"{location} 连线必须引用现有节点")
        if edge["kind"] not in GLOBAL_LOOP_EDGE_KINDS:
            _fail(
                f"{location}.kind 只允许: {', '.join(GLOBAL_LOOP_EDGE_KINDS)}"
            )
        edge_key = (edge["from"], edge["to"], edge["kind"])
        if edge_key in edge_keys:
            _fail(f"{location} 不允许重复连线")
        edge_keys.add(edge_key)
        source = node_by_id[edge["from"]]
        target = node_by_id[edge["to"]]
        target_type = target["type"]
        source_type = source["type"]
        if source_type == "outside_exit":
            _fail("outside_exit 图外出口不得再连接回主体流程")
        if target_type == "outside_exit" and (
            edge["kind"] != "conditional"
            or source_type != "end"
        ):
            _fail("outside_exit 只能由主体终点通过 conditional 连线进入")
        kind = edge["kind"]
        if kind == "primary":
            if (
                target_type == "outside_exit"
                or earliest_slice_index[edge["to"]]
                < earliest_slice_index[edge["from"]]
            ):
                _fail(f"{location} primary 不允许时间逆序或指向图外出口")
            primary_pairs.add((edge["from"], edge["to"]))
        elif kind == "macro_return":
            if source_type != "micro_loop" or target_type != "micro_loop":
                _fail(f"{location} macro_return 两端必须是 micro_loop")
            source_macro = source["macro_loop_id"]
            if source_macro != target["macro_loop_id"]:
                _fail(f"{location} macro_return 两端必须属于同一大 LOOP")
            source_position = node_positions[edge["from"]]
            target_position = node_positions[edge["to"]]
            if target_position <= source_position + 1:
                _fail(f"{location} macro_return 中间必须存在流程打断")
            intervening = nodes[source_position + 1 : target_position]
            if not any(
                item["type"] != "micro_loop"
                or item["macro_loop_id"] != source_macro
                for item in intervening
            ):
                _fail(f"{location} macro_return 中间必须存在其他大 LOOP 或线性节点")
        elif kind == "cross_macro":
            if source_type != "micro_loop" or target_type != "micro_loop":
                _fail(f"{location} cross_macro 两端必须是 micro_loop")
            if source["macro_loop_id"] == target["macro_loop_id"]:
                _fail(f"{location} cross_macro 两端必须属于不同大 LOOP")
        elif kind == "conditional" and target_type != "outside_exit":
            _fail(f"{location} conditional 只允许连接图外出口")

    expected_primary_pairs = {
        (current["id"], following["id"])
        for current, following in zip(subject_nodes, subject_nodes[1:])
    }
    if primary_pairs != expected_primary_pairs:
        _fail("global_loops primary 必须按时间主链连续覆盖全部主体节点")

    if outside_exits:
        outside_incoming = [
            edge
            for edge in edges
            if edge["to"] == outside_exits[0]
        ]
        if len(outside_incoming) != 1:
            _fail(
                "outside_exit 必须且只能由主体终点通过一条 conditional 连线进入"
            )


def _validate_timeline_milestones(
    value: Any, slices: list[Any], duration: float
) -> None:
    if not isinstance(value, list):
        _fail("timeline_milestones 必须是数组")
    seen_ids: set[str] = set()
    for index, raw in enumerate(value):
        location = f"timeline_milestones[{index}]"
        milestone = _require_object(raw, location)
        _require_keys(
            milestone,
            ("id", "type", "label", "timestamp", "slice_index", "note"),
            location,
        )
        milestone_id = milestone["id"]
        _nonempty_text(milestone_id, f"{location}.id")
        if milestone_id in seen_ids:
            _fail(f"{location}.id 不得重复")
        seen_ids.add(milestone_id)
        milestone_type = milestone["type"]
        if milestone_type not in TIMELINE_MILESTONE_TYPES:
            _fail(
                f"{location}.type 必须是: {', '.join(TIMELINE_MILESTONE_TYPES)}"
            )
        _nonempty_text(milestone["label"], f"{location}.label")
        _nonempty_text(milestone["note"], f"{location}.note")
        timestamp = _number(milestone["timestamp"], f"{location}.timestamp")
        if not 0 <= timestamp <= duration:
            _fail(f"{location}.timestamp 必须位于视频时长内")
        slice_index = milestone["slice_index"]
        if (
            isinstance(slice_index, bool)
            or not isinstance(slice_index, int)
            or not 0 <= slice_index < len(slices)
        ):
            _fail(f"{location}.slice_index 越界")
        target = slices[slice_index]
        if not (
            float(target["start"]) <= timestamp < float(target["end"])
            or timestamp == duration == float(target["end"])
        ):
            _fail(f"{location}.timestamp 必须落在 slice_index 对应时间片内")


def validate_analysis(data: Any) -> None:
    """Validate analysis data, raising AnalysisValidationError on failure."""
    root = _require_object(data, "analysis")
    if "emotion_curve" in root:
        _fail("analysis 不再允许旧字段 emotion_curve；请改用 global_curves")
    _require_keys(
        root, ("video", "slices", "global_curves", "global_loops"), "analysis"
    )
    video = _require_object(root["video"], "video")
    _require_keys(video, ("path", "duration_seconds"), "video")
    _nonempty_text(video["path"], "video.path")
    duration = _number(video["duration_seconds"], "video.duration_seconds")
    if duration <= 0:
        _fail("video.duration_seconds 必须大于 0")

    slices = root["slices"]
    if not isinstance(slices, list) or not slices:
        _fail("slices 必须是非空数组")
    expected_timeline = generate_timeline(duration)
    actual_timeline = [
        {
            "index": item.get("index"),
            "start": item.get("start"),
            "end": item.get("end"),
        }
        if isinstance(item, dict)
        else item
        for item in slices
    ]
    if actual_timeline != expected_timeline:
        _fail(
            "时间片 timeline 必须从 0 开始、连续覆盖至 video.duration_seconds，"
            "且边界与 generate_timeline 完全一致"
        )
    required_slice_keys = (
        "index",
        "start",
        "end",
        "main_frame",
        "evidence_frames",
        "dimensions",
        "stage_range",
        "narrative_climax",
        "flow",
        "confidence",
        "evidence",
        "open_questions",
    )
    previous_stage: dict[str, Any] | None = None
    previous_slice_end: float | None = None
    closed_stage_ids: set[str] = set()
    for position, raw_slice in enumerate(slices):
        location = f"slices[{position}]"
        item = _require_object(raw_slice, location)
        _require_keys(item, required_slice_keys, location)
        index = item["index"]
        if isinstance(index, bool) or not isinstance(index, int) or index != position:
            _fail(f"{location}.index 必须是连续整数 {position}")
        start = _number(item["start"], f"{location}.start")
        end = _number(item["end"], f"{location}.end")
        if start < 0 or end <= start or end > duration:
            _fail(f"{location} 范围必须位于视频内且 end 大于 start")

        _validate_frame(item["main_frame"], f"{location}.main_frame", start, end, duration)
        main_timestamp = float(item["main_frame"]["timestamp"])
        midpoint = start + (end - start) / 2
        if not math.isclose(main_timestamp, midpoint, rel_tol=0.0, abs_tol=1e-9):
            selection_reason = item["main_frame"].get("selection_reason")
            if selection_reason != "midpoint_uninformative":
                _fail(
                    f"{location}.main_frame.timestamp 必须等于时间片中点 {midpoint}；"
                    "仅中点无信息时允许改用临近帧，并将 "
                    "selection_reason 设为 midpoint_uninformative"
                )
            max_offset = min(30.0, max(10.0, (end - start) * 0.1))
            if abs(main_timestamp - midpoint) > max_offset:
                _fail(
                    f"{location}.main_frame.timestamp 必须使用临近有效帧；"
                    f"相对中点偏移不得超过 {max_offset:g} 秒"
                )
        evidence_frames = item["evidence_frames"]
        if not isinstance(evidence_frames, list):
            _fail(f"{location}.evidence_frames 必须是数组")
        if len(evidence_frames) > 3:
            _fail(f"{location}.evidence_frames 最多允许 3 张")
        for frame_index, frame in enumerate(evidence_frames):
            _validate_frame(
                frame,
                f"{location}.evidence_frames[{frame_index}]",
                start,
                end,
                duration,
            )

        dimensions = _require_object(item["dimensions"], f"{location}.dimensions")
        _require_keys(dimensions, DIMENSION_KEYS, f"{location}.dimensions")
        extra_dimensions = [key for key in dimensions if key not in DIMENSION_KEYS]
        if extra_dimensions:
            _fail(
                f"{location}.dimensions 必须恰好包含规定七维；额外字段: "
                f"{', '.join(extra_dimensions)}"
            )
        for key in DIMENSION_KEYS:
            dimension_location = f"{location}.dimensions.{key}"
            dimension = _require_object(dimensions[key], dimension_location)
            _require_keys(dimension, ("fact", "inference"), dimension_location)
            extra_fields = [field for field in dimension if field not in ("fact", "inference")]
            if extra_fields:
                _fail(
                    f"{dimension_location} 只允许 fact/inference；额外字段: "
                    f"{', '.join(extra_fields)}"
                )
            for field in ("fact", "inference"):
                if not isinstance(dimension[field], str):
                    _fail(f"{dimension_location}.{field} 必须是文本；无内容时允许空字符串")

        stage = _require_object(item["stage_range"], f"{location}.stage_range")
        _require_keys(
            stage, ("stage_id", "name", "start", "end"), f"{location}.stage_range"
        )
        _nonempty_text(stage["stage_id"], f"{location}.stage_range.stage_id")
        _nonempty_text(stage["name"], f"{location}.stage_range.name")
        stage_start = _number(stage["start"], f"{location}.stage_range.start")
        stage_end = _number(stage["end"], f"{location}.stage_range.end")
        if stage_start < 0 or stage_end <= stage_start or stage_end > duration:
            _fail(f"{location}.stage_range 超出视频范围")
        if not (stage_start <= start and end <= stage_end):
            _fail(f"{location}.stage_range 必须完整覆盖所属时间片")
        if previous_stage is None:
            if stage_start != start:
                _fail(f"{location}.stage_range.start 必须等于该阶段首片 start")
        elif stage["stage_id"] == previous_stage["stage_id"]:
            if (
                stage["name"],
                stage_start,
                stage_end,
            ) != (
                previous_stage["name"],
                float(previous_stage["start"]),
                float(previous_stage["end"]),
            ):
                _fail("相邻同 stage_id 的名称和范围必须完全一致")
        else:
            closed_stage_ids.add(str(previous_stage["stage_id"]))
            if str(stage["stage_id"]) in closed_stage_ids:
                _fail("同一 stage_id 必须出现在连续时间片中")
            if (
                float(previous_stage["end"]) != previous_slice_end
                or stage_start != start
                or float(previous_stage["end"]) != stage_start
            ):
                _fail("相邻阶段范围必须按时间片边界连续衔接")
        previous_stage = stage
        previous_slice_end = end

        for field, allowed in (
            ("narrative_climax", NARRATIVE_JUDGEMENTS),
            ("flow", FLOW_JUDGEMENTS),
        ):
            judgement = _require_object(item[field], f"{location}.{field}")
            _require_keys(judgement, ("judgement", "reason"), f"{location}.{field}")
            _nonempty_text(judgement["judgement"], f"{location}.{field}.judgement")
            _nonempty_text(judgement["reason"], f"{location}.{field}.reason")
            if judgement["judgement"] not in allowed:
                _fail(
                    f"{location}.{field}.judgement 只允许: {', '.join(allowed)}"
                )

        confidence = _number(item["confidence"], f"{location}.confidence")
        if not 0 <= confidence <= 1:
            _fail(f"{location}.confidence 必须在 0 到 1 之间")

        evidence = item["evidence"]
        if not isinstance(evidence, list):
            _fail(f"{location}.evidence 必须是数组")
        allowed_frame_paths = {
            item["main_frame"]["path"],
            *(frame["path"] for frame in evidence_frames),
        }
        for evidence_index, entry in enumerate(evidence):
            entry_location = f"{location}.evidence[{evidence_index}]"
            entry = _require_object(entry, entry_location)
            _require_keys(entry, ("frame", "note"), entry_location)
            _nonempty_text(entry["frame"], f"{entry_location}.frame")
            _nonempty_text(entry["note"], f"{entry_location}.note")
            if entry["frame"] not in allowed_frame_paths:
                _fail(
                    f"{entry_location}.frame 必须引用该 slice 的主图或证据图"
                )

        questions = item["open_questions"]
        if not isinstance(questions, list):
            _fail(f"{location}.open_questions 必须是数组")
        for question_index, question in enumerate(questions):
            _nonempty_text(question, f"{location}.open_questions[{question_index}]")
    if previous_stage is not None and float(previous_stage["end"]) != previous_slice_end:
        _fail("最后阶段范围 end 必须等于该阶段末片 end")
    if "timeline_milestones" in root:
        _validate_timeline_milestones(root["timeline_milestones"], slices, duration)
    _validate_global_curves(root["global_curves"], slices)
    _validate_global_loops(root["global_loops"], slices, duration)


def loads_and_validate(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnalysisValidationError(f"analysis.json 不是合法 JSON: {exc}") from exc
    validate_analysis(data)
    return data


def dumps_analysis(data: Any) -> str:
    validate_analysis(data)
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验统一 analysis.json")
    parser.add_argument("analysis", help="待校验的 analysis.json")
    parser.add_argument("--output", help="将规范化 UTF-8 JSON 写到此路径")
    args = parser.parse_args(argv)
    try:
        source = Path(args.analysis)
        if not source.is_file():
            raise FileNotFoundError(f"analysis.json 不存在: {source}")
        data = loads_and_validate(source.read_text(encoding="utf-8"))
        text = dumps_analysis(data)
        if args.output:
            atomic_write_text(args.output, text)
        else:
            encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            try:
                text.encode(encoding)
            except (LookupError, UnicodeEncodeError):
                text = json.dumps(data, ensure_ascii=True, indent=2) + "\n"
            sys.stdout.write(text)
        return 0
    except (
        OSError,
        UnicodeError,
        AnalysisValidationError,
        ValueError,
        OverflowError,
    ) as exc:
        emit_json_error(exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
