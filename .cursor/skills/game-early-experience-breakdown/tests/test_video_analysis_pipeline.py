import json
import copy
import io
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import analysis_model
import extract_frames
import video_timeline
from experience_adjustment import expected_experience_fields, load_locked_parameters


class VideoTimelineTests(unittest.TestCase):
    def test_generate_timeline_is_public_timeline_api(self):
        self.assertEqual(
            video_timeline.generate_time_slices(75.0),
            video_timeline.generate_timeline(75.0),
        )

    def test_review_step_uses_one_five_and_ten_second_cadence(self):
        self.assertEqual(1.0, video_timeline.review_step_seconds(0.0))
        self.assertEqual(1.0, video_timeline.review_step_seconds(599.0))
        self.assertEqual(5.0, video_timeline.review_step_seconds(600.0))
        self.assertEqual(5.0, video_timeline.review_step_seconds(1199.0))
        self.assertEqual(10.0, video_timeline.review_step_seconds(1200.0))

    def test_review_points_are_dense_without_changing_display_slices(self):
        duration = 1212.5
        points = video_timeline.generate_review_points(duration)
        self.assertEqual([0.0, 1.0, 2.0], points[:3])
        self.assertIn(599.0, points)
        self.assertIn(600.0, points)
        self.assertIn(1195.0, points)
        self.assertIn(1200.0, points)
        self.assertIn(1210.0, points)
        self.assertNotIn(1212.5, points)
        self.assertEqual(21, len(video_timeline.generate_timeline(duration)))

    def test_boundary_29_minutes_uses_one_minute_slices(self):
        slices = video_timeline.generate_time_slices(29 * 60)
        self.assertEqual(29, len(slices))
        self.assertEqual((28 * 60, 29 * 60), (slices[-1]["start"], slices[-1]["end"]))

    def test_boundary_30_minutes_has_thirty_slices(self):
        slices = video_timeline.generate_time_slices(30 * 60)
        self.assertEqual(30, len(slices))
        self.assertEqual((29 * 60, 30 * 60), (slices[-1]["start"], slices[-1]["end"]))

    def test_55_minutes_switches_to_five_minute_slices(self):
        slices = video_timeline.generate_time_slices(55 * 60)
        self.assertEqual(35, len(slices))
        self.assertEqual((50 * 60, 55 * 60), (slices[-1]["start"], slices[-1]["end"]))

    def test_60_minutes_has_thirty_six_slices(self):
        slices = video_timeline.generate_time_slices(60 * 60)
        self.assertEqual(36, len(slices))
        self.assertEqual((55 * 60, 60 * 60), (slices[-1]["start"], slices[-1]["end"]))

    def test_two_hours_seventeen_minutes_has_44_slices(self):
        slices = video_timeline.generate_time_slices((2 * 60 + 17) * 60)
        self.assertEqual(44, len(slices))
        self.assertEqual((130 * 60, 137 * 60), (slices[-1]["start"], slices[-1]["end"]))

    def test_short_video_produces_tail_slice(self):
        self.assertEqual(
            [{"index": 0, "start": 0.0, "end": 12.5}],
            video_timeline.generate_time_slices(12.5),
        )

    def test_invalid_duration_is_rejected(self):
        for duration in (0, -1, float("inf"), float("nan"), "60"):
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    video_timeline.generate_time_slices(duration)

    def test_probe_duration_reports_missing_ffprobe(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "video.mp4"
            video.write_bytes(b"x")
            with mock.patch("video_timeline.subprocess.run", side_effect=FileNotFoundError):
                with self.assertRaisesRegex(video_timeline.ToolError, "ffprobe"):
                    video_timeline.probe_duration(video)


class ExtractFramesTests(unittest.TestCase):
    def test_build_capture_plan_uses_midpoint_and_extra_evidence_times(self):
        slices = [{"index": 0, "start": 0.0, "end": 60.0}]
        plan = extract_frames.build_capture_plan(
            slices, 60.0, {"0": [10.0, 50.0]}
        )
        self.assertEqual([30.0, 10.0, 50.0], [item["timestamp"] for item in plan])
        self.assertEqual(["main", "evidence", "evidence"], [item["kind"] for item in plan])
        self.assertEqual(
            ["slice-000-main-000030000.jpg", "slice-000-evidence-01-000010000.jpg",
             "slice-000-evidence-02-000050000.jpg"],
            [item["filename"] for item in plan],
        )

    def test_capture_time_must_be_inside_half_open_slice_and_video(self):
        slices = [{"index": 0, "start": 0.0, "end": 60.0}]
        for timestamp in (-0.1, 60.0, 61.0):
            with self.subTest(timestamp=timestamp):
                with self.assertRaises(ValueError):
                    extract_frames.build_capture_plan(slices, 60.0, {"0": [timestamp]})

    def test_at_most_three_evidence_frames_per_slice(self):
        slices = [{"index": 0, "start": 0.0, "end": 60.0}]
        with self.assertRaisesRegex(ValueError, "1–3|1-3|3"):
            extract_frames.build_capture_plan(slices, 60.0, {"0": [1, 2, 3, 4]})

    def test_missing_ffmpeg_is_a_controlled_error(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "video.mp4"
            video.write_bytes(b"x")
            output = Path(directory) / "frames"
            plan = [{"timestamp": 1.0, "filename": "frame.jpg"}]
            with mock.patch("extract_frames.subprocess.run", side_effect=FileNotFoundError):
                with self.assertRaisesRegex(extract_frames.ToolError, "ffmpeg"):
                    extract_frames.extract_frames(video, output, plan)


def valid_global_curves(slices):
    locked_parameters = load_locked_parameters()
    curves = {
        "scale": {"min": 0, "max": 5},
        "experience_model": {
            "version": "progression-repetition-v1",
            "parameters": {
                "progression_weight": locked_parameters.progression_weight,
                "penalty_step": locked_parameters.penalty_step,
                "penalty_cap": locked_parameters.penalty_cap,
                "partial_recovery": locked_parameters.partial_recovery,
            },
        },
        "points": [
            {
                "start": item["start"],
                "end": item["end"],
                "emotion": {
                    "narrative_score": 0,
                    "supporting_score": 0,
                    "intensity": 0,
                    "valence": "neutral",
                    "drivers": [],
                    "event": "",
                    "reason": "",
                },
                "experience": {
                    "score": 3,
                    "progression_pull": {
                        "score": 2,
                        "reason": "存在普通成长反馈",
                    },
                    "repetition_context": {
                        "loop_family_id": "building_growth",
                        "variation": "reinforcement",
                        "reason": "继续基础建设循环",
                    },
                    "basis": {
                        "gameplay_concentration": "存在连续有效操作",
                        "feedback_density": "操作后有明确反馈",
                        "goal_challenge": "目标清晰且挑战适中",
                        "interruption": "未观察到明显打断",
                    },
                    "summary": "体验投入程度稳定",
                },
            }
            for item in slices
        ],
    }
    expected = expected_experience_fields(
        curves["points"], locked_parameters
    )
    for point, derived in zip(curves["points"], expected):
        point["experience"]["effective_score"] = derived["effective_score"]
        point["experience"]["adjustments"] = {
            key: derived[key]
            for key in (
                "progression_bonus",
                "repetition_penalty",
                "effective_repeat_count",
            )
        }
    return curves


def valid_global_loops(slices):
    first = slices[0]
    last = slices[-1]
    return {
        "scope": {
            "start": 0.0,
            "end": float(last["end"]),
            "end_label": "教学完成",
            "outside_exit_label": "进入下一玩法",
        },
        "macro_loops": [
            {
                "id": "settlement",
                "title": "聚落建设",
                "accent": "settlement",
                "summary": "通过建设形成成长反馈",
            }
        ],
        "loop_families": [
            {
                "id": "building_growth",
                "title": "建筑升级养成",
                "summary": "通过建设和升级提高聚落能力",
                "accent": "building_growth",
            }
        ],
        "nodes": [
            {
                "id": "entry",
                "type": "transition",
                "title": "进入教学",
                "summary": "建立初始目标",
                "macro_loop_id": "",
                "slice_indices": [0],
                "evidence_frames": [first["main_frame"]["path"]],
                "status": "confirmed",
            },
            {
                "id": "core-loop",
                "type": "micro_loop",
                "title": "基础循环",
                "summary": "完成一次闭环",
                "macro_loop_id": "settlement",
                "loop_family_id": "building_growth",
                "slice_indices": [0],
                "evidence_frames": [first["main_frame"]["path"]],
                "status": "confirmed",
                "confidence": 0.8,
                "motivation": "完成目标",
                "behaviors": ["执行核心操作"],
                "reward": "获得反馈",
                "next_motivation": "追求下一目标",
            },
            {
                "id": "end",
                "type": "end",
                "title": "教学完成",
                "summary": "抵达主体终点",
                "macro_loop_id": "",
                "slice_indices": [len(slices) - 1],
                "evidence_frames": [last["main_frame"]["path"]],
                "status": "confirmed",
            },
        ],
        "edges": [
            {"from": "entry", "to": "core-loop", "kind": "primary", "label": "进入循环"},
            {"from": "core-loop", "to": "end", "kind": "primary", "label": "完成教学"},
        ],
    }


def valid_analysis(duration=60.0):
    dimensions = {
        "阶段目标": {"fact": "出现移动提示", "inference": "目标是了解基础移动"},
        "任务链": {"fact": "出现新手任务", "inference": "任务承担教学"},
        "核心循环": {"fact": "观察到探索与战斗", "inference": "循环开始建立"},
        "渐进体验": {"fact": "功能逐步开放", "inference": "采用渐进解锁"},
        "地图体验": {"fact": "区域呈线性", "inference": "限制自由探索"},
        "经济体验": {"fact": "未观察到", "inference": "未观察到"},
        "剧情轴": {"fact": "冲突被引入", "inference": "处于铺垫阶段"},
    }
    slices = []
    for timeline_slice in video_timeline.generate_time_slices(duration):
        item = {
                **timeline_slice,
                "main_frame": {
                    "path": f"frames/main-{timeline_slice['index']}.jpg",
                    "timestamp": (
                        timeline_slice["start"] + timeline_slice["end"]
                    ) / 2,
                },
                "evidence_frames": [
                    {
                        "path": f"frames/evidence-{timeline_slice['index']}.jpg",
                        "timestamp": timeline_slice["start"],
                    }
                ],
                "dimensions": copy.deepcopy(dimensions),
                "stage_range": {
                    "stage_id": "tutorial",
                    "name": "教学",
                    "start": 0.0,
                    "end": duration,
                },
                "narrative_climax": {"judgement": "none", "reason": "铺垫阶段"},
                "flow": {"judgement": "flow_peak", "reason": "挑战匹配"},
                "confidence": 0.8,
                "evidence": [
                    {
                        "frame": f"frames/evidence-{timeline_slice['index']}.jpg",
                        "note": "教学提示",
                    }
                ],
                "open_questions": ["经济系统何时开启"],
        }
        slices.append(item)
    return {
        "video": {"path": "video.mp4", "duration_seconds": duration},
        "slices": slices,
        "global_curves": valid_global_curves(slices),
        "global_loops": valid_global_loops(slices),
    }


def valid_context(data):
    return {
        "points": [
            {
                "slice_index": index,
                "progression_pull": {
                    "score": 3,
                    "reason": "近期解锁目标可见",
                },
                "repetition_context": {
                    "loop_family_id": "building_growth",
                    "variation": "full_break" if index == 0 else "reinforcement",
                    "reason": "首次建立建设玩法层" if index == 0 else "继续基础建设循环",
                },
            }
            for index, _ in enumerate(data["slices"])
        ]
    }


class AnalysisModelTests(unittest.TestCase):
    def test_precise_timeline_milestones_are_validated(self):
        data = valid_analysis(120.0)
        data["timeline_milestones"] = [
            {
                "id": "slg-entry",
                "type": "slg_entry",
                "label": "进入SLG大地图",
                "timestamp": 90.0,
                "slice_index": 1,
                "note": "跟随雷达热气球进入大地图。",
            }
        ]
        analysis_model.validate_analysis(data)

        data["timeline_milestones"][0]["timestamp"] = 121.0
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "timeline_milestones|视频时长"
        ):
            analysis_model.validate_analysis(data)

    def test_cg_end_timeline_milestone_is_valid(self):
        data = valid_analysis(120.0)
        data["timeline_milestones"] = [
            {
                "id": "opening-cg-end",
                "type": "cg_end",
                "label": "开场CG结束",
                "timestamp": 42.5,
                "slice_index": 0,
                "note": "预渲染过场结束并恢复可操作界面。",
            }
        ]

        analysis_model.validate_analysis(data)

    def test_non_slg_map_entry_timeline_milestone_is_valid(self):
        data = valid_analysis(120.0)
        data["timeline_milestones"] = [
            {
                "id": "open-area-entry",
                "type": "map_entry",
                "label": "进入开放探索大地图",
                "timestamp": 90.0,
                "slice_index": 1,
                "note": "区域地图与探索任务开始生效，但未进入SLG玩法。",
            }
        ]

        analysis_model.validate_analysis(data)

    def test_valid_analysis_passes_and_json_round_trips_utf8(self):
        data = valid_analysis()
        analysis_model.validate_analysis(data)
        encoded = analysis_model.dumps_analysis(data)
        self.assertIn("阶段目标", encoded)
        self.assertEqual(data, json.loads(encoded))

    def test_experience_model_is_required(self):
        data = valid_analysis()
        del data["global_curves"]["experience_model"]
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "experience_model"
        ):
            analysis_model.validate_analysis(data)

    def test_global_loops_is_required_and_valid_graph_passes(self):
        data = valid_analysis(120.0)
        analysis_model.validate_analysis(data)
        del data["global_loops"]
        with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "global_loops"):
            analysis_model.validate_analysis(data)

    def test_global_loop_requires_complete_player_cycle(self):
        data = valid_analysis()
        loop = next(
            node
            for node in data["global_loops"]["nodes"]
            if node["type"] == "micro_loop"
        )
        loop["behaviors"] = []
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "behaviors|行为"
        ):
            analysis_model.validate_analysis(data)

    def test_experience_context_requires_existing_loop_family(self):
        data = valid_analysis()
        data["global_curves"]["points"][0]["experience"]["repetition_context"][
            "loop_family_id"
        ] = "missing"
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "loop_family_id"
        ):
            analysis_model.validate_analysis(data)

    def test_experience_context_allows_empty_loop_family(self):
        data = valid_analysis()
        experience = data["global_curves"]["points"][0]["experience"]
        experience["repetition_context"]["loop_family_id"] = ""
        derived = expected_experience_fields(
            data["global_curves"]["points"],
            load_locked_parameters(),
        )[0]
        experience["effective_score"] = derived["effective_score"]
        experience["adjustments"] = {
            key: derived[key]
            for key in (
                "progression_bonus",
                "repetition_penalty",
                "effective_repeat_count",
            )
        }

        analysis_model.validate_analysis(data)
        self.assertEqual(0, experience["adjustments"]["effective_repeat_count"])

    def test_effective_score_must_match_derived_adjustments(self):
        data = valid_analysis()
        data["global_curves"]["points"][0]["experience"]["effective_score"] = 5
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "effective_score|算法"
        ):
            analysis_model.validate_analysis(data)

    def test_derived_experience_values_allow_only_tiny_float_noise(self):
        data = valid_analysis()
        experience = data["global_curves"]["points"][0]["experience"]
        experience["effective_score"] += 5e-10
        experience["adjustments"]["progression_bonus"] += 5e-10

        analysis_model.validate_analysis(data)

    def test_original_experience_score_is_not_rewritten(self):
        import apply_experience_context

        data = valid_analysis()
        original = [
            point["experience"]["score"]
            for point in data["global_curves"]["points"]
        ]
        migrated = apply_experience_context.apply_context(data, valid_context(data))
        self.assertEqual(
            original,
            [
                point["experience"]["score"]
                for point in migrated["global_curves"]["points"]
            ],
        )

    def test_beboo_late_slices_use_visually_reviewed_scores_and_reasons(self):
        beboo_path = (
            ROOT.parents[2]
            / "artifacts"
            / "early-experience"
            / "viewer"
            / "data"
            / "beboo.json"
        )
        if not beboo_path.exists():
            beboo_path = ROOT.parents[2] / "data" / "beboo.json"
        data = json.loads(beboo_path.read_text(encoding="utf-8"))
        late_experience = [
            point["experience"]
            for point in data["global_curves"]["points"][30:38]
        ]

        self.assertEqual(
            [1.9, 2.4, 2.9, 2.7, 3.3, 2.5, 3.3, 3.1],
            [experience["score"] for experience in late_experience],
        )
        self.assertEqual(1.8, late_experience[2]["effective_score"])
        self.assertEqual(2.2, late_experience[6]["effective_score"])
        self.assertEqual(
            [1, 1, 1, 0, 1, 3, 1, 0],
            [
                experience["progression_pull"]["score"]
                for experience in late_experience
            ],
        )
        self.assertEqual(
            [
                "combat-route",
                "combat-route",
                "combat-route",
                "combat-route",
                "combat-route",
                "camp-prepare",
                "combat-route",
                "combat-route",
            ],
            [
                experience["repetition_context"]["loop_family_id"]
                for experience in late_experience
            ],
        )
        self.assertEqual(
            [
                "reinforcement",
                "reinforcement",
                "reinforcement",
                "reinforcement",
                "reinforcement",
                "partial_break",
                "reinforcement",
                "reinforcement",
            ],
            [
                experience["repetition_context"]["variation"]
                for experience in late_experience
            ],
        )

        generic_phrases = ("按该片", "人工判断", "人工评分为")
        for experience in late_experience:
            reason_text = "\n".join(
                [*experience["basis"].values(), experience["summary"]]
            )
            self.assertFalse(
                any(phrase in reason_text for phrase in generic_phrases),
                reason_text,
            )

    def test_narco_empire_has_valid_isolated_data_and_world_map_entry(self):
        narco_path = (
            ROOT.parents[2]
            / "artifacts"
            / "early-experience"
            / "viewer"
            / "data"
            / "narco-empire.json"
        )
        if not narco_path.exists():
            narco_path = ROOT.parents[2] / "data" / "narco-empire.json"

        self.assertTrue(narco_path.exists(), narco_path)
        data = json.loads(narco_path.read_text(encoding="utf-8"))
        analysis_model.validate_analysis(data)

        self.assertEqual(37, len(data["slices"]))
        self.assertEqual(
            "progression-repetition-v1",
            data["global_curves"]["experience_model"]["version"],
        )
        slg_entries = [
            item
            for item in data["timeline_milestones"]
            if item["type"] == "slg_entry"
        ]
        self.assertEqual(1, len(slg_entries))
        self.assertEqual(34, slg_entries[0]["slice_index"])
        self.assertGreaterEqual(slg_entries[0]["timestamp"], 3190.0)
        self.assertLess(slg_entries[0]["timestamp"], 3240.0)
        self.assertIn("坐标", slg_entries[0]["note"])
        self.assertIn("联盟", slg_entries[0]["note"])

    def test_last_war_excludes_external_capture_interruptions(self):
        last_war_path = (
            ROOT.parents[2]
            / "artifacts"
            / "early-experience"
            / "viewer"
            / "data"
            / "last-war.json"
        )
        if not last_war_path.exists():
            last_war_path = ROOT.parents[2] / "data" / "last-war.json"

        self.assertTrue(last_war_path.exists(), last_war_path)
        data = json.loads(last_war_path.read_text(encoding="utf-8"))
        analysis_model.validate_analysis(data)

        self.assertEqual(33, len(data["slices"]))
        self.assertEqual(
            "progression-repetition-v1",
            data["global_curves"]["experience_model"]["version"],
        )
        exclusions = data["capture_exclusions"]
        self.assertEqual(2, len(exclusions))
        self.assertEqual(0.0, exclusions[0]["start"])
        self.assertLessEqual(exclusions[0]["end"], 3.5)
        self.assertGreaterEqual(exclusions[1]["start"], 2618.0)
        self.assertGreater(exclusions[1]["end"], exclusions[1]["start"])
        self.assertTrue(
            all(item["reason"] == "external_capture_interruption" for item in exclusions)
        )
        interruption_text = " ".join(
            point["experience"]["basis"]["interruption"]
            for point in data["global_curves"]["points"]
        )
        self.assertNotIn("控制中心", interruption_text)
        self.assertNotIn("录屏", interruption_text)

    def test_global_loop_confidence_equals_lowest_referenced_slice(self):
        data = valid_analysis(120.0)
        micro = data["global_loops"]["nodes"][1]
        micro["slice_indices"] = [0, 1]
        micro["confidence"] = 0.9
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "confidence|最低|置信度"
        ):
            analysis_model.validate_analysis(data)

    def test_global_loop_rejects_dangling_edges(self):
        data = valid_analysis()
        data["global_loops"]["edges"][0]["to"] = "missing"
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "连线|节点"
        ):
            analysis_model.validate_analysis(data)

    def test_global_loop_outside_exit_uses_only_first_slice_after_scope(self):
        data = valid_analysis(180.0)
        graph = data["global_loops"]
        graph["scope"]["end"] = 60.0
        graph["nodes"][-1]["slice_indices"] = [0]
        graph["nodes"][-1]["evidence_frames"] = [
            data["slices"][0]["main_frame"]["path"]
        ]
        outside = {
            "id": "outside",
            "type": "outside_exit",
            "title": "范围外",
            "summary": "后续玩法",
            "macro_loop_id": "",
            "slice_indices": [1, 2],
            "evidence_frames": [data["slices"][1]["main_frame"]["path"]],
            "status": "confirmed",
        }
        graph["nodes"].append(outside)
        graph["edges"].append(
            {"from": "end", "to": "outside", "kind": "conditional", "label": "后续"}
        )
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "outside_exit|首个|图外"
        ):
            analysis_model.validate_analysis(data)

    def test_global_loop_outside_exit_cannot_link_back_to_subject(self):
        data = valid_analysis(120.0)
        graph = data["global_loops"]
        graph["scope"]["end"] = 60.0
        graph["nodes"][-1]["slice_indices"] = [0]
        graph["nodes"][-1]["evidence_frames"] = [
            data["slices"][0]["main_frame"]["path"]
        ]
        graph["nodes"].append(
            {
                "id": "outside",
                "type": "outside_exit",
                "title": "范围外",
                "summary": "后续玩法",
                "macro_loop_id": "",
                "slice_indices": [1],
                "evidence_frames": [data["slices"][1]["main_frame"]["path"]],
                "status": "confirmed",
            }
        )
        graph["edges"].extend(
            [
                {"from": "end", "to": "outside", "kind": "conditional", "label": "后续"},
                {"from": "outside", "to": "entry", "kind": "primary", "label": "非法回流"},
            ]
        )
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "outside_exit|图外"
        ):
            analysis_model.validate_analysis(data)

    def test_global_loop_outside_exit_requires_conditional_edge_from_end(self):
        data = valid_analysis(120.0)
        graph = data["global_loops"]
        graph["scope"]["end"] = 60.0
        graph["nodes"][-1]["slice_indices"] = [0]
        graph["nodes"][-1]["evidence_frames"] = [
            data["slices"][0]["main_frame"]["path"]
        ]
        graph["nodes"].append(
            {
                "id": "outside",
                "type": "outside_exit",
                "title": "范围外",
                "summary": "后续玩法",
                "macro_loop_id": "",
                "slice_indices": [1],
                "evidence_frames": [data["slices"][1]["main_frame"]["path"]],
                "status": "confirmed",
            }
        )
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "outside_exit|conditional|图外"
        ):
            analysis_model.validate_analysis(data)

    def test_global_loop_rejects_duplicate_ids_and_missing_primary_path(self):
        data = valid_analysis()
        data["global_loops"]["nodes"][1]["id"] = "entry"
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "id|重复"
        ):
            analysis_model.validate_analysis(data)

        data = valid_analysis()
        data["global_loops"]["edges"] = [
            edge
            for edge in data["global_loops"]["edges"]
            if edge["to"] != "end"
        ]
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "primary|主路径"
        ):
            analysis_model.validate_analysis(data)

    def test_global_loop_requires_unique_valid_macro_definitions(self):
        data = valid_analysis()
        del data["global_loops"]["macro_loops"]
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "macro_loops"
        ):
            analysis_model.validate_analysis(data)

        data = valid_analysis()
        data["global_loops"]["macro_loops"].append(
            {
                "id": "settlement",
                "title": "重复",
                "accent": "invalid",
                "summary": "重复定义",
            }
        )
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "macro|重复|accent"
        ):
            analysis_model.validate_analysis(data)

    def test_global_loop_requires_valid_used_loop_families(self):
        data = valid_analysis()
        del data["global_loops"]["loop_families"]
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "loop_families"
        ):
            analysis_model.validate_analysis(data)

        data = valid_analysis()
        data["global_loops"]["loop_families"][0]["accent"] = "unknown"
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "accent"
        ):
            analysis_model.validate_analysis(data)

        data = valid_analysis()
        duplicate = copy.deepcopy(data["global_loops"]["loop_families"][0])
        data["global_loops"]["loop_families"].append(duplicate)
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "loop_families|重复"
        ):
            analysis_model.validate_analysis(data)

        data = valid_analysis()
        data["global_loops"]["loop_families"].append(
            {
                "id": "unused",
                "title": "未使用",
                "summary": "没有节点引用",
                "accent": "law_system",
            }
        )
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "未使用|引用"
        ):
            analysis_model.validate_analysis(data)

    def test_micro_loop_requires_single_existing_loop_family(self):
        data = valid_analysis()
        del data["global_loops"]["nodes"][1]["loop_family_id"]
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "loop_family_id"
        ):
            analysis_model.validate_analysis(data)

        data = valid_analysis()
        data["global_loops"]["nodes"][1]["loop_family_id"] = "missing"
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "loop_family_id"
        ):
            analysis_model.validate_analysis(data)

        data = valid_analysis()
        data["global_loops"]["nodes"][0]["loop_family_id"] = "building_growth"
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "micro_loop|loop_family_id"
        ):
            analysis_model.validate_analysis(data)

    def test_global_loop_rejects_legacy_loop_and_invalid_micro_loop_fields(self):
        data = valid_analysis()
        data["global_loops"]["nodes"][1]["type"] = "loop"
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "micro_loop|type"
        ):
            analysis_model.validate_analysis(data)

        for field in ("macro_loop_id", "confidence", "reward"):
            with self.subTest(field=field):
                data = valid_analysis()
                del data["global_loops"]["nodes"][1][field]
                with self.assertRaisesRegex(
                    analysis_model.AnalysisValidationError, field
                ):
                    analysis_model.validate_analysis(data)

        data = valid_analysis()
        data["global_loops"]["nodes"][0]["reward"] = "不允许"
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "micro_loop|闭环"
        ):
            analysis_model.validate_analysis(data)

    def test_global_loop_rejects_subject_slice_beyond_scope_and_isolated_node(self):
        data = valid_analysis(120.0)
        data["global_loops"]["scope"]["end"] = 60.0
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "scope|主体"
        ):
            analysis_model.validate_analysis(data)

    def test_global_loop_end_may_mark_an_exact_exit_inside_its_slice(self):
        data = valid_analysis(120.0)
        data["global_loops"]["scope"]["end"] = 119.0

        analysis_model.validate_analysis(data)

        data = valid_analysis(120.0)
        data["global_loops"]["scope"]["end"] = 119.0
        core_loop = data["global_loops"]["nodes"][1]
        core_loop["slice_indices"] = [0, 1]

        analysis_model.validate_analysis(data)

        data = valid_analysis()
        data["global_loops"]["nodes"].insert(
            -1,
            {
                "id": "isolated",
                "type": "transition",
                "title": "孤立节点",
                "summary": "没有连线",
                "macro_loop_id": "",
                "slice_indices": [0],
                "evidence_frames": [data["slices"][0]["main_frame"]["path"]],
                "status": "confirmed",
            },
        )
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "孤立|primary|主链"
        ):
            analysis_model.validate_analysis(data)

    def test_global_loop_relation_kinds_match_macro_ownership_and_time(self):
        def analysis_with_second_micro():
            data = valid_analysis(180.0)
            graph = data["global_loops"]
            second = copy.deepcopy(graph["nodes"][1])
            second.update(
                {
                    "id": "second-loop",
                    "title": "第二循环",
                    "slice_indices": [1],
                    "evidence_frames": [data["slices"][1]["main_frame"]["path"]],
                }
            )
            graph["nodes"].insert(-1, second)
            graph["edges"] = [
                {"from": "entry", "to": "core-loop", "kind": "primary", "label": "开始"},
                {"from": "core-loop", "to": "second-loop", "kind": "primary", "label": "继续"},
                {"from": "second-loop", "to": "end", "kind": "primary", "label": "结束"},
            ]
            return data

        data = analysis_with_second_micro()
        data["global_loops"]["edges"].append(
            {
                "from": "core-loop",
                "to": "second-loop",
                "kind": "cross_macro",
                "label": "非法同类跨环",
            }
        )
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "cross_macro|不同"
        ):
            analysis_model.validate_analysis(data)

        data = analysis_with_second_micro()
        data["global_loops"]["edges"].append(
            {
                "from": "core-loop",
                "to": "second-loop",
                "kind": "macro_return",
                "label": "没有打断",
            }
        )
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "macro_return|打断"
        ):
            analysis_model.validate_analysis(data)

        data = analysis_with_second_micro()
        for edge in data["global_loops"]["edges"]:
            if edge["from"] == "core-loop" and edge["to"] == "second-loop":
                edge["from"], edge["to"] = edge["to"], edge["from"]
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "primary|时间逆序"
        ):
            analysis_model.validate_analysis(data)

    def test_global_loop_evidence_must_belong_to_referenced_slice(self):
        data = valid_analysis(120.0)
        data["global_loops"]["nodes"][0]["evidence_frames"] = [
            data["slices"][1]["main_frame"]["path"]
        ]
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "证据|时间片"
        ):
            analysis_model.validate_analysis(data)

    def test_frost_global_loops_use_seventeen_typed_micro_loops_before_slg(self):
        frost_path = (
            ROOT.parents[2]
            / "artifacts"
            / "early-experience"
            / "viewer"
            / "data"
            / "frost.json"
        )
        if not frost_path.exists():
            frost_path = (
                ROOT.parents[1]
                / "tmp"
                / "frost-breakdown"
                / "analysis.final.validated.json"
            )
        if not frost_path.exists():
            frost_path = (
                ROOT.parents[2]
                / "artifacts"
                / "frost-early-experience"
                / "viewer"
                / "data"
                / "frost.json"
            )
        if not frost_path.exists():
            frost_path = ROOT.parents[2] / "data" / "frost.json"
        data = json.loads(frost_path.read_text(encoding="utf-8"))
        self.assertEqual(1500, data["global_loops"]["scope"]["end"])
        micro_loops = [
            node
            for node in data["global_loops"]["nodes"]
            if node["type"] == "micro_loop"
        ]
        self.assertEqual(
            {"settlement": 12, "expedition": 3, "hero_growth": 2},
            dict(Counter(node["macro_loop_id"] for node in micro_loops)),
        )
        self.assertEqual(17, len(micro_loops))
        self.assertEqual(
            {
                "building_growth": 8,
                "building_production": 2,
                "expedition_progression": 3,
                "hero_growth": 2,
                "law_system": 1,
                "heating_boost": 1,
            },
            dict(Counter(node["loop_family_id"] for node in micro_loops)),
        )
        subject_ids = [
            node["id"]
            for node in data["global_loops"]["nodes"]
            if node["type"] != "outside_exit"
        ]
        self.assertEqual(
            [
                "settlement-survival-landing",
                "legacy-transition",
                "settlement-legacy-start",
                "settlement-build-queue",
                "settlement-infrastructure",
                "settlement-production-unlock",
                "settlement-expedition-ready",
                "expedition-first-sortie",
                "hero-recruit-and-deploy",
                "settlement-expedition-reinvest",
                "expedition-second-launch",
                "hero-post-battle-growth",
                "expedition-ice-river-push",
                "settlement-return-cleanup",
                "settlement-building-production",
                "settlement-temporary-heating-boost",
                "settlement-cold-policy",
                "settlement-resource-sprint",
                "main-city-end",
            ],
            subject_ids,
        )
        primary_pairs = {
            (edge["from"], edge["to"])
            for edge in data["global_loops"]["edges"]
            if edge["kind"] == "primary"
        }
        self.assertTrue(
            {
                (
                    "settlement-return-cleanup",
                    "settlement-building-production",
                ),
                (
                    "settlement-building-production",
                    "settlement-temporary-heating-boost",
                ),
                (
                    "settlement-temporary-heating-boost",
                    "settlement-cold-policy",
                ),
            }.issubset(primary_pairs)
        )
        self.assertTrue(
            any(
                edge["kind"] == "macro_return"
                for edge in data["global_loops"]["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["kind"] == "cross_macro"
                for edge in data["global_loops"]["edges"]
            )
        )
        self.assertEqual(
            {
                "type": "slg_entry",
                "timestamp": 1510.0,
                "slice_index": 25,
            },
            {
                key: data["timeline_milestones"][0][key]
                for key in ("type", "timestamp", "slice_index")
            },
        )
        if "experience_model" in data["global_curves"]:
            analysis_model.validate_analysis(data)

    def test_aoo_records_titan_plan_unlock_from_visible_main_frame(self):
        aoo_path = (
            ROOT.parents[2]
            / "artifacts"
            / "early-experience"
            / "viewer"
            / "data"
            / "aoo.json"
        )
        if not aoo_path.exists():
            aoo_path = ROOT.parents[2] / "data" / "aoo.json"
        data = json.loads(aoo_path.read_text(encoding="utf-8"))
        target_slice = data["slices"][6]
        dimension_facts = "\n".join(
            value["fact"] for value in target_slice["dimensions"].values()
        )

        self.assertEqual(1738.5, data["global_loops"]["scope"]["end"])
        self.assertEqual(386.0, target_slice["main_frame"]["timestamp"])
        self.assertIn("泰坦", dimension_facts)
        self.assertTrue(
            any(
                385.0 <= frame["timestamp"] <= 400.0
                for frame in target_slice["evidence_frames"]
            )
        )
        self.assertTrue(
            any(
                "泰坦" in f"{node['title']} {node['summary']}"
                and 6 in node["slice_indices"]
                for node in data["global_loops"]["nodes"]
                if node["type"] == "micro_loop"
            )
        )
        if "experience_model" in data["global_curves"]:
            analysis_model.validate_analysis(data)

    def test_aoo_does_not_collapse_slice_nineteen_battle_into_building_loop(self):
        aoo_path = (
            ROOT.parents[2]
            / "artifacts"
            / "early-experience"
            / "viewer"
            / "data"
            / "aoo.json"
        )
        if not aoo_path.exists():
            aoo_path = ROOT.parents[2] / "data" / "aoo.json"
        data = json.loads(aoo_path.read_text(encoding="utf-8"))
        target_slice = data["slices"][19]
        core_loop_fact = target_slice["dimensions"]["核心循环"]["fact"]

        self.assertIn("战斗", core_loop_fact)
        self.assertTrue(
            any(
                node["loop_family_id"] == "expedition_progression"
                and 19 in node["slice_indices"]
                for node in data["global_loops"]["nodes"]
                if node["type"] == "micro_loop"
            )
        )
        if "experience_model" in data["global_curves"]:
            analysis_model.validate_analysis(data)

    def test_sanbing_records_mother_death_as_exact_second_climax(self):
        sanbing_path = (
            ROOT.parents[2]
            / "artifacts"
            / "early-experience"
            / "viewer"
            / "data"
            / "sanbing.json"
        )
        if not sanbing_path.exists():
            sanbing_path = (
                ROOT.parents[1]
                / "tmp"
                / "sanbing-breakdown"
                / "analysis.validated.json"
            )
        if not sanbing_path.exists():
            sanbing_path = (
                ROOT.parents[2]
                / "artifacts"
                / "sanbing-early-experience"
                / "viewer"
                / "data"
                / "sanbing.json"
            )
        if not sanbing_path.exists():
            sanbing_path = ROOT.parents[2] / "data" / "sanbing.json"
        data = json.loads(sanbing_path.read_text(encoding="utf-8"))
        target_slice = data["slices"][7]
        target_curve = data["global_curves"]["points"][7]

        self.assertIn("母亲", target_slice["dimensions"]["剧情轴"]["fact"])
        self.assertEqual("climax", target_slice["narrative_climax"]["judgement"])
        self.assertTrue(
            any(
                473.0 <= frame["timestamp"] <= 477.0
                for frame in target_slice["evidence_frames"]
            )
        )
        self.assertTrue(
            any(
                "07:54" in evidence["note"] and "去世" in evidence["note"]
                for evidence in target_slice["evidence"]
            )
        )
        self.assertEqual(5, target_curve["emotion"]["narrative_score"])
        self.assertEqual(5, target_curve["emotion"]["intensity"])
        self.assertEqual("negative", target_curve["emotion"]["valence"])
        self.assertEqual(
            {
                "type": "slg_entry",
                "timestamp": 2160.0,
                "slice_index": 31,
            },
            {
                key: data["timeline_milestones"][0][key]
                for key in ("type", "timestamp", "slice_index")
            },
        )
        if "experience_model" in data["global_curves"]:
            analysis_model.validate_analysis(data)

    def test_invalid_json_is_rejected(self):
        with self.assertRaises(analysis_model.AnalysisValidationError):
            analysis_model.loads_and_validate("{not json")

    def test_missing_dimension_is_rejected_even_when_empty_is_allowed(self):
        data = valid_analysis()
        del data["slices"][0]["dimensions"]["经济体验"]
        with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "经济体验"):
            analysis_model.validate_analysis(data)

        data = valid_analysis()
        data["slices"][0]["dimensions"]["经济体验"] = {"fact": "", "inference": ""}
        analysis_model.validate_analysis(data)

    def test_frame_timestamp_outside_slice_is_rejected(self):
        data = valid_analysis()
        data["slices"][0]["main_frame"]["timestamp"] = 60.0
        with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "timestamp|时间"):
            analysis_model.validate_analysis(data)

    def test_more_than_three_evidence_frames_is_rejected(self):
        data = valid_analysis()
        data["slices"][0]["evidence_frames"] = [
            {"path": f"frames/{index}.jpg", "timestamp": float(index + 1)}
            for index in range(4)
        ]
        with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "3"):
            analysis_model.validate_analysis(data)

    def test_timeline_must_start_at_zero(self):
        data = valid_analysis(120.0)
        data["slices"][0]["start"] = 1.0
        data["slices"][0]["main_frame"]["timestamp"] = 30.5
        with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "时间片|timeline"):
            analysis_model.validate_analysis(data)

    def test_timeline_rejects_gap_and_overlap(self):
        for second_start in (59.0, 61.0):
            with self.subTest(second_start=second_start):
                data = valid_analysis(120.0)
                data["slices"][1]["start"] = second_start
                data["slices"][1]["main_frame"]["timestamp"] = (
                    second_start + data["slices"][1]["end"]
                ) / 2
                with self.assertRaisesRegex(
                    analysis_model.AnalysisValidationError, "时间片|timeline"
                ):
                    analysis_model.validate_analysis(data)

    def test_timeline_must_cover_video_duration(self):
        data = valid_analysis(120.0)
        data["slices"][-1]["end"] = 119.0
        data["slices"][-1]["main_frame"]["timestamp"] = 89.5
        with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "时间片|timeline"):
            analysis_model.validate_analysis(data)

    def test_timeline_boundaries_must_exactly_match_progressive_generator(self):
        data = valid_analysis(120.0)
        data["slices"][0]["end"] = 50.0
        data["slices"][0]["main_frame"]["timestamp"] = 25.0
        data["slices"][1]["start"] = 50.0
        data["slices"][1]["main_frame"]["timestamp"] = 85.0
        with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "时间片|timeline"):
            analysis_model.validate_analysis(data)

    def test_main_frame_must_be_slice_midpoint_with_tiny_tolerance(self):
        data = valid_analysis()
        data["slices"][0]["main_frame"]["timestamp"] = 30.000001
        with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "中点"):
            analysis_model.validate_analysis(data)

        data = valid_analysis()
        data["slices"][0]["main_frame"]["timestamp"] = 30.0 + 1e-10
        analysis_model.validate_analysis(data)

    def test_uninformative_midpoint_can_use_documented_nearby_main_frame(self):
        data = valid_analysis()
        data["slices"][0]["main_frame"]["timestamp"] = 35.0
        data["slices"][0]["main_frame"]["selection_reason"] = "midpoint_uninformative"

        analysis_model.validate_analysis(data)

        data["slices"][0]["main_frame"]["timestamp"] = 45.0
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError,
            "临近|偏移",
        ):
            analysis_model.validate_analysis(data)

        data["slices"][0]["main_frame"]["timestamp"] = 35.0
        data["slices"][0]["main_frame"]["selection_reason"] = "looks_better"
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError,
            "selection_reason|中点无信息",
        ):
            analysis_model.validate_analysis(data)

    def test_dimensions_rejects_extra_eighth_key(self):
        data = valid_analysis()
        data["slices"][0]["dimensions"]["额外维度"] = {
            "fact": "不允许",
            "inference": "不允许",
        }
        with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "额外|七"):
            analysis_model.validate_analysis(data)

    def test_dimension_requires_explicit_fact_and_inference_object(self):
        data = valid_analysis()
        data["slices"][0]["dimensions"]["任务链"] = "事实：任务出现；推断：承担教学"
        with self.assertRaisesRegex(analysis_model.AnalysisValidationError, "fact|inference|对象"):
            analysis_model.validate_analysis(data)

    def test_highlight_judgements_use_closed_enums(self):
        for field, invalid in (("narrative_climax", "高潮"), ("flow", "是")):
            with self.subTest(field=field):
                data = valid_analysis()
                data["slices"][0][field]["judgement"] = invalid
                with self.assertRaisesRegex(
                    analysis_model.AnalysisValidationError, "none|climax|low|flow_peak"
                ):
                    analysis_model.validate_analysis(data)

    def test_evidence_must_reference_a_frame_from_same_slice(self):
        data = valid_analysis()
        data["slices"][0]["evidence"][0]["frame"] = "frames/foreign.jpg"
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "主图|证据图|引用"
        ):
            analysis_model.validate_analysis(data)

    def test_adjacent_same_stage_id_requires_identical_name_and_range(self):
        data = valid_analysis(120.0)
        data["slices"][1]["stage_range"]["name"] = "另一个名称"
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "stage_id|名称|范围"
        ):
            analysis_model.validate_analysis(data)

    def test_global_curves_is_required_and_legacy_curve_is_rejected(self):
        data = valid_analysis()
        del data["global_curves"]
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "global_curves"
        ):
            analysis_model.validate_analysis(data)

        data = valid_analysis()
        data["emotion_curve"] = {}
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "emotion_curve|旧"
        ):
            analysis_model.validate_analysis(data)

    def test_global_curve_scale_and_scores_are_strict_without_trend_window(self):
        for field, value in (("min", -1), ("max", 6)):
            with self.subTest(value=value):
                data = valid_analysis()
                data["global_curves"]["scale"][field] = value
                with self.assertRaisesRegex(
                    analysis_model.AnalysisValidationError,
                    "scale|0|5",
                ):
                    analysis_model.validate_analysis(data)

        for path, value in (
            (("emotion", "intensity"), -0.1),
            (("emotion", "intensity"), 5.1),
            (("experience", "score"), float("inf")),
            (("experience", "score"), "3"),
        ):
            with self.subTest(path=path, value=value):
                data = valid_analysis()
                data["global_curves"]["points"][0][path[0]][path[1]] = value
                with self.assertRaisesRegex(
                    analysis_model.AnalysisValidationError, "0|5|数字|有限"
                ):
                    analysis_model.validate_analysis(data)

    def test_global_curve_points_must_align_exactly_with_slices(self):
        data = valid_analysis(120.0)
        data["global_curves"]["points"].pop()
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "数量|时间片"
        ):
            analysis_model.validate_analysis(data)

        data = valid_analysis(120.0)
        data["global_curves"]["points"][1]["start"] = 59
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "边界|时间片"
        ):
            analysis_model.validate_analysis(data)

    def test_emotion_valence_and_conditional_text_are_validated(self):
        data = valid_analysis()
        data["global_curves"]["points"][0]["emotion"]["valence"] = "sad"
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "positive|negative|mixed|neutral"
        ):
            analysis_model.validate_analysis(data)

        data = valid_analysis()
        data["global_curves"]["points"][0]["emotion"].update({
            "narrative_score": 5,
            "supporting_score": 0,
            "intensity": 5,
            "valence": "negative",
            "drivers": ["narrative"],
        })
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "event|reason|非空"
        ):
            analysis_model.validate_analysis(data)

        data["global_curves"]["points"][0]["emotion"].update({
            "event": "角色死亡",
            "reason": "核心关系断裂",
        })
        analysis_model.validate_analysis(data)

    def test_emotion_intensity_uses_narrative_dominant_formula(self):
        self.assertEqual(5, analysis_model.expected_emotion_intensity(5, 0))
        self.assertEqual(1.5, analysis_model.expected_emotion_intensity(0, 5))
        self.assertEqual(1.6, analysis_model.expected_emotion_intensity(1, 3))

        data = valid_analysis()
        data["global_curves"]["points"][0]["emotion"].update({
            "narrative_score": 1,
            "supporting_score": 3,
            "intensity": 1.5,
            "valence": "negative",
            "drivers": ["narrative", "environment_pressure", "urgency"],
            "event": "暴风雪倒计时逼近",
            "reason": "剧情铺垫叠加持续环境压力",
        })
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "intensity|公式|1.6"
        ):
            analysis_model.validate_analysis(data)

    def test_emotion_drivers_match_subscores(self):
        invalid_cases = (
            (
                {"narrative_score": 1, "supporting_score": 0, "intensity": 1,
                 "drivers": []},
                "narrative",
            ),
            (
                {"narrative_score": 0, "supporting_score": 2, "intensity": 0.6,
                 "drivers": ["narrative"]},
                "其他刺激|非剧情|剧情分为 0|narrative",
            ),
            (
                {"narrative_score": 0, "supporting_score": 0, "intensity": 0,
                 "drivers": ["relief"]},
                "零|drivers",
            ),
            (
                {"narrative_score": 0, "supporting_score": 2, "intensity": 0.6,
                 "drivers": ["urgency", "urgency"]},
                "重复",
            ),
            (
                {"narrative_score": 0, "supporting_score": 2, "intensity": 0.6,
                 "drivers": ["weather"]},
                "environment_pressure|urgency",
            ),
            (
                {"narrative_score": 0, "supporting_score": 2, "intensity": 0.6,
                 "drivers": ["narrative", "urgency"]},
                "剧情分为 0|narrative",
            ),
            (
                {"narrative_score": 1, "supporting_score": 0, "intensity": 1,
                 "drivers": ["narrative", "combat"]},
                "其他刺激分为 0|非剧情",
            ),
        )
        for patch, error in invalid_cases:
            with self.subTest(patch=patch):
                data = valid_analysis()
                emotion = data["global_curves"]["points"][0]["emotion"]
                emotion.update(patch)
                emotion.update({
                    "valence": "negative",
                    "event": "可观察刺激",
                    "reason": "形成情绪压力",
                })
                with self.assertRaisesRegex(
                    analysis_model.AnalysisValidationError, error
                ):
                    analysis_model.validate_analysis(data)

    def test_emotion_intensity_rejects_more_than_one_decimal_precision(self):
        data = valid_analysis()
        data["global_curves"]["points"][0]["emotion"].update({
            "intensity": 0.0000000005,
            "event": "错误精度",
            "reason": "用于验证严格公式",
        })
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "intensity|公式"
        ):
            analysis_model.validate_analysis(data)

    def test_experience_requires_four_basis_texts_and_summary(self):
        fields = (
            "gameplay_concentration",
            "feedback_density",
            "goal_challenge",
            "interruption",
        )
        for field in fields:
            with self.subTest(field=field):
                data = valid_analysis()
                data["global_curves"]["points"][0]["experience"]["basis"][field] = ""
                with self.assertRaisesRegex(
                    analysis_model.AnalysisValidationError, f"{field}|非空"
                ):
                    analysis_model.validate_analysis(data)

        data = valid_analysis()
        data["global_curves"]["points"][0]["experience"]["summary"] = " "
        with self.assertRaisesRegex(
            analysis_model.AnalysisValidationError, "summary|非空"
        ):
            analysis_model.validate_analysis(data)


class CliErrorTests(unittest.TestCase):
    def test_analysis_cli_falls_back_to_ascii_json_on_gbk_stdout(self):
        data = valid_analysis()
        data["slices"][0]["dimensions"]["核心循环"]["fact"] = "建设↔战斗"
        with tempfile.TemporaryDirectory() as directory:
            analysis_path = Path(directory) / "analysis.json"
            analysis_path.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
            raw_stdout = io.BytesIO()
            gbk_stdout = io.TextIOWrapper(raw_stdout, encoding="gbk")
            with mock.patch.object(sys, "stdout", gbk_stdout):
                code = analysis_model.main([str(analysis_path)])
                gbk_stdout.flush()
            output = raw_stdout.getvalue().decode("ascii")
        self.assertEqual(0, code)
        self.assertIn("\\u2194", output)
        self.assertEqual("建设↔战斗", json.loads(output)["slices"][0]["dimensions"]["核心循环"]["fact"])

    def test_extract_cli_missing_input_returns_nonzero_with_json_error(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.mp4"
            with mock.patch.object(
                sys,
                "argv",
                ["extract_frames.py", str(missing), "--output-dir", directory],
            ):
                stderr = mock.Mock()
                stderr.write = mock.Mock()
                with mock.patch("sys.stderr", stderr):
                    code = extract_frames.main()
            self.assertNotEqual(0, code)
            message = "".join(call.args[0] for call in stderr.write.call_args_list)
            self.assertIn("不存在", message)


if __name__ == "__main__":
    unittest.main()
