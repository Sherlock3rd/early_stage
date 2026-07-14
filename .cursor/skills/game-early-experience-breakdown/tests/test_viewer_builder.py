import copy
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_viewer
from analysis_model import dumps_analysis
from test_video_analysis_pipeline import valid_analysis

MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05"
    b"\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


class ViewerBuilderTests(unittest.TestCase):
    def make_input(self, root: Path, data=None, create_images=True) -> tuple[Path, dict]:
        data = copy.deepcopy(data or valid_analysis())
        for node in data["global_loops"]["nodes"]:
            allowed = {
                frame["path"]
                for index in node["slice_indices"]
                for frame in [
                    data["slices"][index]["main_frame"],
                    *data["slices"][index]["evidence_frames"],
                ]
            }
            if any(path not in allowed for path in node["evidence_frames"]):
                node["evidence_frames"] = [
                    data["slices"][node["slice_indices"][0]]["main_frame"]["path"]
                ]
        analysis = root / "输入" / "analysis.json"
        analysis.parent.mkdir(parents=True)
        if create_images:
            for item in data["slices"]:
                paths = [item["main_frame"]["path"]]
                paths.extend(frame["path"] for frame in item["evidence_frames"])
                paths.extend(entry["frame"] for entry in item["evidence"])
                for relative in paths:
                    image = analysis.parent / Path(relative)
                    image.parent.mkdir(parents=True, exist_ok=True)
                    image.write_bytes(MINIMAL_PNG)
        analysis.write_text(dumps_analysis(data), encoding="utf-8")
        return analysis, data

    def test_successful_build_has_portable_package_structure(self):
        with tempfile.TemporaryDirectory(prefix="查看器-") as directory:
            root = Path(directory)
            analysis, _ = self.make_input(root)
            output = root / "可移动包"

            build_viewer.build_package(analysis, output)

            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "data.json").is_file())
            self.assertTrue((output / "screenshots").is_dir())
            self.assertFalse(any(path.name.startswith(".viewer-build-") for path in root.iterdir()))

    def test_data_json_is_normalized_input_with_rebased_image_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis, original = self.make_input(root)
            output = root / "viewer"

            normalized = build_viewer.build_package(analysis, output)
            written = json.loads((output / "data.json").read_text(encoding="utf-8"))

            self.assertEqual(normalized, written)
            expected = copy.deepcopy(original)
            for item in expected["slices"]:
                item["main_frame"]["path"] = "screenshots/" + item["main_frame"]["path"]
                for frame in item["evidence_frames"]:
                    frame["path"] = "screenshots/" + frame["path"]
                for entry in item["evidence"]:
                    entry["frame"] = "screenshots/" + entry["frame"]
            for node in expected["global_loops"]["nodes"]:
                node["evidence_frames"] = [
                    "screenshots/" + path for path in node["evidence_frames"]
                ]
            self.assertEqual(expected, written)

    def test_screenshots_preserve_unicode_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = valid_analysis()
            data["slices"][0]["main_frame"]["path"] = "帧/主画面.jpg"
            data["slices"][0]["evidence_frames"][0]["path"] = "帧/证据/图一.jpg"
            data["slices"][0]["evidence"][0]["frame"] = "帧/证据/图一.jpg"
            analysis, _ = self.make_input(root, data)

            build_viewer.build_package(analysis, root / "viewer")

            self.assertEqual(
                MINIMAL_PNG,
                (root / "viewer/screenshots/帧/主画面.jpg").read_bytes(),
            )
            self.assertTrue((root / "viewer/screenshots/帧/证据/图一.jpg").is_file())

    def test_parent_absolute_windows_and_colliding_paths_are_rejected(self):
        bad_paths = ("../secret.jpg", "/absolute.jpg", r"C:\secret.jpg")
        for bad_path in bad_paths:
            with self.subTest(path=bad_path), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                data = valid_analysis()
                data["slices"][0]["main_frame"]["path"] = bad_path
                analysis, _ = self.make_input(root, data, create_images=False)
                with self.assertRaisesRegex(ValueError, "路径|相对|穿越"):
                    build_viewer.build_package(analysis, root / "viewer")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = valid_analysis()
            data["slices"][0]["main_frame"]["path"] = "frames/a.jpg"
            data["slices"][0]["evidence_frames"][0]["path"] = "frames/./a.jpg"
            data["slices"][0]["evidence"][0]["frame"] = "frames/./a.jpg"
            analysis, _ = self.make_input(root, data)
            with self.assertRaisesRegex(ValueError, "重名|冲突"):
                build_viewer.build_package(analysis, root / "viewer")

    def test_windows_reserved_ambiguous_and_ads_paths_are_rejected(self):
        for bad_path in (
            "frames/CON.jpg",
            "frames/aux",
            "frames/name. ",
            "frames/name.",
            "frames/name:stream.jpg",
        ):
            with self.subTest(path=bad_path):
                with self.assertRaisesRegex(ValueError, "Windows|保留|尾随|ADS|路径"):
                    build_viewer._safe_relative_path(bad_path)

    def test_windows_backslash_separator_is_normalized(self):
        browser_path, parts = build_viewer._safe_relative_path(
            r"截图\第一章\主画面.jpg"
        )
        self.assertEqual("截图/第一章/主画面.jpg", browser_path)
        self.assertEqual(("截图", "第一章", "主画面.jpg"), parts)

    def test_output_equal_to_or_ancestor_of_analysis_parent_is_rejected(self):
        for output_kind in ("parent", "ancestor"):
            with self.subTest(output_kind=output_kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                analysis, _ = self.make_input(root)
                output = analysis.parent if output_kind == "parent" else root
                try:
                    with self.assertRaisesRegex(ValueError, "输出|输入|重叠"):
                        build_viewer.build_package(analysis, output)
                finally:
                    self.assertTrue(analysis.is_file())

    def test_output_containing_source_screenshot_is_rejected_without_deleting_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = valid_analysis()
            data["slices"][0]["main_frame"]["path"] = "viewer/source.jpg"
            analysis, _ = self.make_input(root, data)
            source = analysis.parent / "viewer/source.jpg"

            with self.assertRaisesRegex(ValueError, "输出|截图|重叠"):
                build_viewer.build_package(analysis, analysis.parent / "viewer")

            self.assertTrue(analysis.is_file())
            self.assertTrue(source.is_file())

    def test_symlinked_output_resolving_to_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis, _ = self.make_input(root)
            link = root / "linked-output"
            try:
                os.symlink(analysis.parent, link, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"当前环境不能创建目录符号链接: {exc}")
            with self.assertRaisesRegex(ValueError, "输出|输入|重叠"):
                build_viewer.build_package(analysis, link)

    def test_missing_or_empty_screenshot_is_rejected(self):
        for empty in (False, True):
            with self.subTest(empty=empty), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                analysis, data = self.make_input(root)
                image = analysis.parent / data["slices"][0]["main_frame"]["path"]
                if empty:
                    image.write_bytes(b"")
                else:
                    image.unlink()
                with self.assertRaisesRegex(ValueError, "截图|图片|不存在|为空"):
                    build_viewer.build_package(analysis, root / "viewer")

    def test_plain_text_disguised_as_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis, data = self.make_input(root)
            image = analysis.parent / data["slices"][0]["main_frame"]["path"]
            image.write_bytes(b"this is not an image")
            with self.assertRaisesRegex(ValueError, "PNG|JPEG|GIF|WebP|格式|魔数"):
                build_viewer.build_package(analysis, root / "viewer")

    def test_image_magic_accepts_required_formats(self):
        headers = {
            "PNG": b"\x89PNG\r\n\x1a\nrest",
            "JPEG": b"\xff\xd8\xff\xe0rest",
            "GIF": b"GIF89arest",
            "WebP": b"RIFF\x04\x00\x00\x00WEBP",
        }
        with tempfile.TemporaryDirectory() as directory:
            for expected, header in headers.items():
                with self.subTest(expected=expected):
                    path = Path(directory) / expected
                    path.write_bytes(header)
                    self.assertEqual(expected, build_viewer._image_format(path))

    def test_build_failure_preserves_old_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis, _ = self.make_input(root)
            output = root / "viewer"
            output.mkdir()
            marker = output / "old.txt"
            marker.write_text("old", encoding="utf-8")

            with mock.patch("build_viewer.shutil.copy2", side_effect=PermissionError("denied")):
                with self.assertRaises(PermissionError):
                    build_viewer.build_package(analysis, output)

            self.assertEqual("old", marker.read_text(encoding="utf-8"))
            self.assertEqual(["old.txt"], [path.name for path in output.iterdir()])

    def test_backup_cleanup_failure_is_nonfatal_after_new_package_is_committed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "viewer"
            output.mkdir()
            (output / "old.txt").write_text("old", encoding="utf-8")
            staged = root / "staged"
            staged.mkdir()
            (staged / "new.txt").write_text("new", encoding="utf-8")

            with mock.patch(
                "build_viewer.shutil.rmtree",
                side_effect=PermissionError("cleanup denied"),
            ):
                build_viewer._commit_directory(staged, output)

            self.assertEqual("new", (output / "new.txt").read_text(encoding="utf-8"))
            self.assertFalse((output / "old.txt").exists())
            self.assertTrue(any(path.name.startswith(".viewer-backup-") for path in root.iterdir()))

    def test_transaction_recovers_consistently_after_crash_at_each_commit_step(self):
        class SimulatedCrash(BaseException):
            pass

        expectations = {
            "after_journal": "old",
            "after_backup_move": "old",
            "after_new_move": "new",
        }
        for checkpoint, expected in expectations.items():
            with self.subTest(checkpoint=checkpoint), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                analysis, _ = self.make_input(root)
                output = root / "viewer"
                output.mkdir()
                (output / "old.txt").write_text("old", encoding="utf-8")

                def crash(name):
                    if name == checkpoint:
                        raise SimulatedCrash(name)

                with mock.patch(
                    "build_viewer._transaction_checkpoint", side_effect=crash
                ):
                    with self.assertRaises(SimulatedCrash):
                        build_viewer.build_package(analysis, output)

                journal = build_viewer._journal_path(output)
                self.assertTrue(journal.is_file())
                build_viewer._recover_transaction(output)
                self.assertFalse(journal.exists())
                if expected == "old":
                    self.assertEqual("old", (output / "old.txt").read_text("utf-8"))
                else:
                    self.assertTrue((output / "index.html").is_file())
                    self.assertFalse((output / "old.txt").exists())

    def test_normal_commit_failure_rolls_back_old_package_and_removes_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis, _ = self.make_input(root)
            output = root / "viewer"
            output.mkdir()
            (output / "old.txt").write_text("old", encoding="utf-8")

            def fail(name):
                if name == "after_backup_move":
                    raise PermissionError("simulated commit failure")

            with mock.patch("build_viewer._transaction_checkpoint", side_effect=fail):
                with self.assertRaises(PermissionError):
                    build_viewer.build_package(analysis, output)

            self.assertEqual("old", (output / "old.txt").read_text("utf-8"))
            self.assertFalse(build_viewer._journal_path(output).exists())

    def test_special_url_characters_are_preserved_on_disk_and_encoded_for_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = valid_analysis()
            data["slices"][0]["main_frame"]["path"] = "帧/主#100%.jpg"
            analysis, _ = self.make_input(root, data)

            build_viewer.build_package(analysis, root / "viewer")

            self.assertTrue((root / "viewer/screenshots/帧/主#100%.jpg").is_file())
            written = json.loads((root / "viewer/data.json").read_text(encoding="utf-8"))
            self.assertEqual(
                "screenshots/帧/主#100%.jpg",
                written["slices"][0]["main_frame"]["path"],
            )

    def test_html_contains_compact_overview_and_dimension_tabs(self):
        html = (ROOT / "assets" / "viewer.html").read_text(encoding="utf-8")
        script = (ROOT / "assets" / "viewer.js").read_text(encoding="utf-8")
        combined = html + script
        for hook in (
            'id="timeline"',
            'id="filters"',
            'id="detail-panel"',
            'id="overview-track"',
            'id="previous-slice"',
            'id="next-slice"',
            'id="dimension-tabs"',
            'id="highlight-filter"',
            'id="lightbox"',
            'id="emotion-curve-section"',
            'id="emotion-curve-svg"',
            'id="emotion-curve-legend"',
            'id="emotion-curve-tooltip"',
            'id="emotion-algorithm-details"',
            'id="curve-reading-guide"',
            'id="experience-trend-summary"',
            "阶段目标",
            "任务链",
            "核心循环",
            "渐进体验",
            "地图体验",
            "经济体验",
            "剧情轴",
            "置信度",
            "待确认项",
        ):
            self.assertIn(hook, combined)
        for obsolete in (
            "<h3>事实</h3>",
            "<h3>推断</h3>",
            "<h3>证据</h3>",
            "高潮/低谷时间证据",
            "心流高点时间证据",
            "证据路径",
        ):
            self.assertNotIn(obsolete, combined)
        self.assertIn("narrative", combined)
        self.assertIn("flow", combined)
        self.assertNotIn("综合情绪值", combined)
        self.assertNotIn("维度分 × 维度权重", combined)
        self.assertNotIn('role="dialog"', html)

    def test_assets_have_no_external_urls_or_cdn_dependencies(self):
        for name in ("viewer.html", "viewer.css", "viewer.js"):
            text = (ROOT / "assets" / name).read_text(encoding="utf-8").lower()
            self.assertNotIn("http://", text)
            self.assertNotIn("https://", text)
            self.assertNotIn("//cdn", text)

    def test_cli_invalid_json_uses_json_error_protocol_and_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "bad.json"
            source.write_text("{bad", encoding="utf-8")
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                code = build_viewer.main([str(source), "--output-dir", str(root / "viewer")])
            self.assertEqual(2, code)
            payload = json.loads(stderr.getvalue())
            self.assertEqual({"type", "message"}, set(payload["error"]))
            self.assertIn("JSON", payload["error"]["message"])

    def test_cli_invalid_analysis_contract_uses_json_error_and_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = valid_analysis()
            del data["slices"][0]["dimensions"]["阶段目标"]
            source = root / "invalid-analysis.json"
            source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                code = build_viewer.main([str(source), "--output-dir", str(root / "viewer")])
            self.assertEqual(2, code)
            payload = json.loads(stderr.getvalue())
            self.assertEqual("AnalysisValidationError", payload["error"]["type"])
            self.assertIn("阶段目标", payload["error"]["message"])

    def test_cli_rejects_existing_non_directory_output_with_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis, _ = self.make_input(root)
            output = root / "viewer"
            output.write_text("old", encoding="utf-8")
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr):
                code = build_viewer.main([str(analysis), "--output-dir", str(output)])
            self.assertEqual(2, code)
            self.assertEqual("old", output.read_text(encoding="utf-8"))


class ViewerJavascriptBehaviorTests(unittest.TestCase):
    def run_node(self, expression: str):
        script = ROOT / "assets" / "viewer.js"
        command = (
            f"const viewer=require({json.dumps(str(script))});"
            f"const result=({expression});"
            "process.stdout.write(JSON.stringify(result));"
        )
        completed = subprocess.run(
            ["node", "-e", command],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(completed.stdout)

    def run_node_async(self, expression: str):
        script = ROOT / "assets" / "viewer.js"
        command = (
            f"const viewer=require({json.dumps(str(script))});"
            f"Promise.resolve({expression}).then(result=>"
            "process.stdout.write(JSON.stringify(result)),error=>{"
            "console.error(error);process.exit(1);});"
        )
        completed = subprocess.run(
            ["node", "-e", command],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(completed.stdout)

    def test_long_timeline_fits_container_without_horizontal_track(self):
        slices = [
            {"start": item["start"], "end": item["end"]}
            for item in valid_analysis(137 * 60)["slices"]
        ]
        self.assertEqual(44, len(slices))
        layout = self.run_node(
            f"viewer.computeTimelineLayout(137*60,{json.dumps(slices)})"
        )
        self.assertNotIn("trackWidth", layout)
        self.assertEqual(44, len(layout["nodes"]))
        self.assertEqual(0, layout["nodes"][0]["left"])
        self.assertAlmostEqual(100, layout["nodes"][-1]["left"] + layout["nodes"][-1]["width"])
        for current, following in zip(layout["nodes"], layout["nodes"][1:]):
            self.assertAlmostEqual(
                current["left"] + current["width"],
                following["left"],
            )

    def test_dual_curves_use_linear_regression_over_real_time(self):
        data = valid_analysis(125)
        for point, emotion, experience in zip(
            data["global_curves"]["points"], (5, 2, 0), (1, 3, 5)
        ):
            point["emotion"].update({
                "intensity": emotion,
                "valence": "negative" if emotion else "neutral",
                "event": "关键事件" if emotion else "",
                "reason": "情绪冲击" if emotion else "",
            })
            point["experience"]["score"] = experience
        encoded = json.dumps(data, ensure_ascii=False)
        result = self.run_node(
            "({"
            "rising:viewer.linearRegressionTrend("
            "[{time:30,score:1},{time:90,score:3},{time:150,score:5}],0,5),"
            "flat:viewer.linearRegressionTrend([{time:30,score:2}],0,5),"
            "falling:viewer.linearRegressionTrend("
            "[{time:0,score:5},{time:60,score:3},{time:120,score:1}],0,5),"
            "clamped:viewer.linearRegressionTrend("
            "[{time:0,score:0},{time:1,score:5},{time:2,score:5}],0,5),"
            f"model:viewer.globalCurvesViewModel({encoded})"
            "})"
        )
        self.assertAlmostEqual(1 / 30, result["rising"]["slope"])
        self.assertAlmostEqual(1, result["rising"]["openingPrediction"])
        self.assertAlmostEqual(5, result["rising"]["endingPrediction"])
        self.assertAlmostEqual(4, result["rising"]["delta"])
        self.assertEqual("rising", result["rising"]["direction"])
        self.assertEqual([2], result["flat"]["predictions"])
        self.assertEqual("flat", result["flat"]["direction"])
        self.assertEqual("falling", result["falling"]["direction"])
        self.assertGreater(result["clamped"]["rawEndingPrediction"], 5)
        self.assertEqual(5, result["clamped"]["endingPrediction"])
        self.assertEqual(3, len(result["model"]["points"]))
        self.assertAlmostEqual(
            result["model"]["trendSummary"]["predictions"][0],
            result["model"]["points"][0]["experienceTrend"],
        )
        self.assertEqual(2, len(result["model"]["trendPoints"]))
        self.assertLess(
            result["model"]["points"][0]["y"]["emotion"],
            result["model"]["points"][0]["y"]["experience"],
        )
        self.assertLess(
            result["model"]["points"][0]["x"],
            result["model"]["points"][1]["x"],
        )

    def test_curve_chart_uses_responsive_container_dimensions(self):
        data = valid_analysis(125)
        model = self.run_node(
            f"viewer.globalCurvesViewModel({json.dumps(data, ensure_ascii=False)},1376,420)"
        )
        self.assertEqual(1376, model["width"])
        self.assertEqual(420, model["height"])
        for point in model["points"]:
            self.assertGreaterEqual(point["x"], model["padding"]["left"])
            self.assertLessEqual(
                point["x"],
                model["width"] - model["padding"]["right"],
            )
            for y in point["y"].values():
                self.assertGreaterEqual(y, model["padding"]["top"])
                self.assertLessEqual(
                    y,
                    model["height"] - model["padding"]["bottom"],
                )

        css = (ROOT / "assets" / "viewer.css").read_text(encoding="utf-8")
        self.assertRegex(
            css,
            r"#emotion-curve-svg\s*\{[^}]*height:\s*clamp\(480px,\s*42vw,\s*600px\)",
        )
        self.assertRegex(
            css,
            r"@media \(max-width:\s*540px\)[\s\S]*?"
            r"#emotion-curve-svg\s*\{[^}]*height:\s*"
            r"clamp\(320px,\s*82vw,\s*420px\)",
        )
        self.assertRegex(
            css,
            r"\.emotion-curve-chart\s*\{[^}]*width:\s*100%;[^}]*height:\s*100%;",
        )
        self.assertRegex(
            css,
            r"main\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\);",
        )
        script = (ROOT / "assets" / "viewer.js").read_text(encoding="utf-8")
        self.assertIn("curveContainer.clientWidth", script)
        self.assertIn("curveContainer.clientHeight", script)
        self.assertIn("ResizeObserver", script)
        self.assertRegex(
            script,
            r"new ResizeObserver\([\s\S]*?renderEmotionCurve\(\);\s*"
            r"renderSelected\(\);",
        )

    def test_curve_slice_hit_bands_cover_full_plot_without_gaps(self):
        data = valid_analysis(125)
        model = self.run_node(
            f"viewer.globalCurvesViewModel({json.dumps(data, ensure_ascii=False)})"
        )
        bands = self.run_node(
            f"viewer.curveSliceBands({json.dumps(model, ensure_ascii=False)})"
        )
        self.assertEqual(len(model["points"]), len(bands))
        self.assertAlmostEqual(model["padding"]["left"], bands[0]["left"])
        self.assertAlmostEqual(
            model["width"] - model["padding"]["right"],
            bands[-1]["right"],
        )
        for current, following in zip(bands, bands[1:]):
            self.assertGreater(current["right"], current["left"])
            self.assertAlmostEqual(current["right"], following["left"])
        self.assertEqual(model["padding"]["top"], bands[0]["top"])
        self.assertEqual(model["plotHeight"], bands[0]["height"])

        html = self.run_node(
            f"viewer.globalCurvesSvgMarkup({json.dumps(model, ensure_ascii=False)},"
            "viewer.defaultGlobalCurveVisibility())"
        )
        self.assertEqual(
            len(model["points"]),
            html.count('class="curve-slice-hit-zone'),
        )
        self.assertIn('data-curve-slice="0"', html)

        empty_state = self.run_node(
            "viewer.curveSliceInteractionState(0,-1,[false,false])"
        )
        self.assertFalse(empty_state["selected"])
        self.assertTrue(empty_state["filteredOut"])
        self.assertTrue(empty_state["disabled"])

    def test_curve_selection_has_no_persistent_box_and_tooltip_can_overflow(self):
        css = (ROOT / "assets" / "viewer.css").read_text(encoding="utf-8")
        self.assertRegex(
            css,
            r"\.emotion-curve-canvas\s*\{[^}]*overflow:\s*visible;",
        )
        self.assertRegex(
            css,
            r"\.emotion-curve-section\s*\{[^}]*position:\s*relative;"
            r"[^}]*z-index:\s*2;",
        )
        self.assertNotRegex(
            css,
            r"\.curve-slice-hit-zone\.selected\s*\{[^}]*"
            r"(?:fill|stroke):",
        )
        self.assertNotIn(
            ".curve-slice-hit-zone.selected + .curve-slice-guide",
            css,
        )

    def test_loop_family_statistics_deduplicates_and_counts_reinforcement(self):
        families = [
            {
                "id": family_id,
                "title": title,
                "summary": f"{title}说明",
                "accent": family_id,
            }
            for family_id, title in (
                ("building_growth", "建筑升级养成"),
                ("building_production", "建筑生产"),
                ("expedition_progression", "推关玩法"),
                ("hero_growth", "英雄养成"),
                ("law_system", "法令系统"),
                ("heating_boost", "临时供暖强化"),
            )
        ]
        counts = {
            "building_growth": 8,
            "building_production": 2,
            "expedition_progression": 3,
            "hero_growth": 2,
            "law_system": 1,
            "heating_boost": 1,
        }
        graph = {
            "loop_families": families,
            "nodes": [
                {"type": "micro_loop", "loop_family_id": family_id}
                for family_id, count in counts.items()
                for _ in range(count)
            ],
        }
        statistics = self.run_node(
            f"viewer.loopFamilyStatistics({json.dumps(graph, ensure_ascii=False)})"
        )
        self.assertEqual(17, statistics["eventCount"])
        self.assertEqual(6, statistics["uniqueCount"])
        self.assertEqual(
            [
                ["building_growth", 8, 7],
                ["building_production", 2, 1],
                ["expedition_progression", 3, 2],
                ["hero_growth", 2, 1],
                ["law_system", 1, 0],
                ["heating_boost", 1, 0],
            ],
            [
                [item["id"], item["occurrences"], item["reinforcements"]]
                for item in statistics["families"]
            ],
        )
        statistics["families"][0]["title"] = "<img src=x onerror=bad()>"
        html = self.run_node(
            "viewer.loopFamilyStatisticsMarkup("
            f"{json.dumps(statistics, ensure_ascii=False)})"
        )
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img src=x onerror=bad()&gt;", html)
        self.assertIn("事件级小 LOOP", html)
        self.assertIn("去重小 LOOP", html)

        special = {
            "loop_families": [
                {
                    "id": "__proto__",
                    "title": "特殊类型",
                    "summary": "验证安全计数",
                    "accent": "building_growth",
                }
            ],
            "nodes": [
                {"type": "micro_loop", "loop_family_id": "__proto__"},
            ],
        }
        special_statistics = self.run_node(
            "viewer.loopFamilyStatistics("
            f"{json.dumps(special, ensure_ascii=False)})"
        )
        self.assertEqual(1, special_statistics["families"][0]["occurrences"])
        self.assertEqual(0, special_statistics["families"][0]["reinforcements"])

    def test_related_loop_navigation_handles_multiple_empty_and_filtered_nodes(self):
        nodes = [
            {
                "id": "building-production",
                "type": "micro_loop",
                "title": "建筑生产",
                "slice_indices": [20],
            },
            {
                "id": "heating-boost",
                "type": "micro_loop",
                "title": "临时供暖强化",
                "slice_indices": [20],
            },
            {
                "id": "hero-growth",
                "type": "micro_loop",
                "title": "英雄养成",
                "slice_indices": [15],
            },
            {
                "id": "story-transition",
                "type": "transition",
                "title": "剧情过渡",
                "slice_indices": [2],
            },
        ]
        visible = [True] * 21
        items = self.run_node(
            f"viewer.relatedMicroLoops({json.dumps(nodes, ensure_ascii=False)},"
            f"20,{json.dumps(visible)})"
        )
        self.assertEqual(
            ["building-production", "heating-boost"],
            [item["id"] for item in items],
        )
        self.assertTrue(all(not item["disabled"] for item in items))

        hidden = [True] * 21
        hidden[20] = False
        disabled = self.run_node(
            f"viewer.relatedMicroLoops({json.dumps(nodes, ensure_ascii=False)},"
            f"20,{json.dumps(hidden)})"
        )
        self.assertTrue(all(item["disabled"] for item in disabled))
        empty = self.run_node(
            f"viewer.relatedMicroLoops({json.dumps(nodes, ensure_ascii=False)},"
            f"2,{json.dumps(visible)})"
        )
        self.assertEqual([], empty)
        empty_html = self.run_node(
            "viewer.relatedLoopNavigationMarkup([])"
        )
        self.assertIn("当前时间片无关联 LOOP", empty_html)
        items[0]["title"] = "<script>bad()</script>"
        html = self.run_node(
            "viewer.relatedLoopNavigationMarkup("
            f"{json.dumps(items, ensure_ascii=False)})"
        )
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt;", html)
        self.assertIn('data-related-loop="building-production"', html)

    def test_hierarchical_loop_view_model_keeps_four_parts_and_filter_state(self):
        data = valid_analysis(120)
        self.assertEqual(
            {},
            self.run_node("viewer.defaultMacroLoopVisibility({bad:true})"),
        )
        model = self.run_node(
            f"viewer.hierarchicalLoopsViewModel({json.dumps(data, ensure_ascii=False)},"
            "[true,false],viewer.defaultMacroLoopVisibility("
            f"{json.dumps(data['global_loops']['macro_loops'], ensure_ascii=False)}))"
        )
        loop = next(
            node for node in model["nodes"] if node["type"] == "micro_loop"
        )
        self.assertEqual(
            ["动机", "行为", "奖励", "下一动机"],
            [part["label"] for part in loop["parts"]],
        )
        self.assertEqual(["执行核心操作"], loop["parts"][1]["values"])
        self.assertFalse(loop["disabled"])
        self.assertFalse(loop["dimmed"])
        self.assertEqual(0, loop["primarySlice"])
        end = next(node for node in model["nodes"] if node["type"] == "end")
        self.assertTrue(end["disabled"])

    def test_hierarchical_loop_segments_split_on_interruption_without_reordering(self):
        data = valid_analysis(180)
        graph = data["global_loops"]
        graph["macro_loops"].append(
            {
                "id": "expedition",
                "title": "战斗远征",
                "accent": "expedition",
                "summary": "通过战斗取得收益",
            }
        )
        expedition = copy.deepcopy(graph["nodes"][1])
        expedition.update(
            {
                "id": "expedition-loop",
                "title": "首次远征",
                "macro_loop_id": "expedition",
                "slice_indices": [1],
                "evidence_frames": [data["slices"][1]["main_frame"]["path"]],
            }
        )
        settlement_return = copy.deepcopy(expedition)
        settlement_return.update(
            {
                "id": "settlement-return",
                "title": "回投建设",
                "macro_loop_id": "settlement",
            }
        )
        graph["nodes"].insert(-1, expedition)
        graph["nodes"].insert(-1, settlement_return)
        graph["edges"] = [
            {"from": "entry", "to": "core-loop", "kind": "primary", "label": "开始"},
            {
                "from": "core-loop",
                "to": "expedition-loop",
                "kind": "primary",
                "label": "出征",
            },
            {
                "from": "expedition-loop",
                "to": "settlement-return",
                "kind": "primary",
                "label": "返乡",
            },
            {
                "from": "settlement-return",
                "to": "end",
                "kind": "primary",
                "label": "结束",
            },
            {
                "from": "core-loop",
                "to": "settlement-return",
                "kind": "macro_return",
                "label": "战后回流",
            },
            {
                "from": "expedition-loop",
                "to": "settlement-return",
                "kind": "cross_macro",
                "label": "战利回投",
            },
        ]
        visibility = {"settlement": False, "expedition": True}
        model = self.run_node(
            f"viewer.hierarchicalLoopsViewModel({json.dumps(data, ensure_ascii=False)},"
            f"[true,true,true],{json.dumps(visibility)})"
        )
        self.assertEqual(
            ["entry", "core-loop", "expedition-loop", "settlement-return", "end"],
            [node["id"] for node in model["nodes"]],
        )
        self.assertEqual(
            ["settlement:0", "expedition:0", "settlement:1"],
            [segment["id"] for segment in model["segments"]],
        )
        dimmed = [
            node["id"] for node in model["nodes"] if node.get("dimmed")
        ]
        self.assertEqual(["core-loop", "settlement-return"], dimmed)
        self.assertIn(
            "首次远征 → 回投建设：战利回投",
            [edge["mobileLabel"] for edge in model["relationEdges"]],
        )
        self.assertTrue(
            next(
                edge
                for edge in model["relationEdges"]
                if edge["kind"] == "cross_macro"
            )["dimmed"]
        )
        all_visible = self.run_node(
            "viewer.showAllMacroLoops({settlement:false,expedition:false})"
        )
        self.assertEqual({"settlement": True, "expedition": True}, all_visible)

    def test_hierarchical_loop_markup_escapes_text_and_has_semantic_colors(self):
        data = valid_analysis()
        loop = data["global_loops"]["nodes"][1]
        loop["motivation"] = "<img src=x onerror=bad()>"
        data["global_loops"]["macro_loops"][0]["title"] = "<b>聚落</b>"
        html = self.run_node(
            f"viewer.hierarchicalLoopsMarkup(viewer.hierarchicalLoopsViewModel("
            f"{json.dumps(data, ensure_ascii=False)},[true],{{settlement:true}}))"
        )
        self.assertNotIn("<img", html)
        self.assertNotIn("<b>聚落</b>", html)
        self.assertIn("&lt;img src=x onerror=bad()&gt;", html)
        for hook in (
            "macro-segment-settlement",
            "loop-part-motivation",
            "loop-part-behavior",
            "loop-part-reward",
            "loop-part-next",
            'data-loop-node="core-loop"',
            'data-loop-part="reward"',
        ):
            self.assertIn(hook, html)
        self.assertIn("进入教学", html)
        self.assertIn("基础循环", html)
        self.assertRegex(html, r"进入教学\s*→\s*基础循环")

    def test_hierarchical_loop_tooltip_removed_and_navigation_hooks_present(self):
        template = (ROOT / "assets" / "viewer.html").read_text(encoding="utf-8")
        css = (ROOT / "assets" / "viewer.css").read_text(encoding="utf-8")
        script = (ROOT / "assets" / "viewer.js").read_text(encoding="utf-8")
        self.assertIn('id="related-loop-navigation"', template)
        self.assertIn('id="global-loop-statistics"', template)
        self.assertNotIn('id="global-loop-tooltip"', template)
        self.assertNotIn(".global-loop-tooltip", css)
        self.assertNotIn("hierarchicalLoopTooltipMarkup", script)
        self.assertNotIn("showGlobalLoopTooltip", script)
        self.assertNotIn("hideGlobalLoopTooltip", script)
        self.assertNotIn(
            'byId("global-loop-canvas").addEventListener("pointerover"',
            script,
        )
        self.assertIn("function focusLoopNode(", script)
        self.assertIn("scrollIntoView", script)
        self.assertIn("loop-location-pulse", script)

    def test_global_loop_section_is_last_and_responsive(self):
        template = (ROOT / "assets" / "viewer.html").read_text(encoding="utf-8")
        self.assertLess(
            template.index('id="detail-panel"'),
            template.index('id="global-loop-section"'),
        )
        self.assertIn('id="global-loop-legend"', template)
        self.assertIn('id="global-loop-statistics"', template)
        self.assertIn('id="global-loop-canvas"', template)
        self.assertLess(
            template.index('id="global-loop-section"'),
            template.index("</main>"),
        )
        css = (ROOT / "assets" / "viewer.css").read_text(encoding="utf-8")
        for hook in (
            ".macro-segment-settlement",
            ".macro-segment-expedition",
            ".macro-segment-hero-growth",
            ".macro-loop-dimmed",
            ".loop-part-motivation",
            ".loop-part-behavior",
            ".loop-part-reward",
            ".loop-part-next",
            ".global-loop-statistics",
            ".loop-family-stat-list",
            ".related-loop-navigation",
            ".loop-location-pulse",
        ):
            self.assertIn(hook, css)
        self.assertRegex(
            css,
            r"\.micro-loop-parts\s*\{[^}]*grid-template-columns:\s*"
            r"minmax\(0,\s*1fr\)\s+auto\s+minmax\(0,\s*1fr\)\s+auto\s+"
            r"minmax\(0,\s*1fr\)\s+auto\s+minmax\(0,\s*1fr\);",
        )
        self.assertRegex(
            css,
            r"@media \(max-width:\s*720px\)[\s\S]*?"
            r"\.micro-loop-parts\s*\{[^}]*grid-template-columns:\s*1fr;",
        )
        script = (ROOT / "assets" / "viewer.js").read_text(encoding="utf-8")
        self.assertIn("function renderGlobalLoops()", script)
        self.assertIn("hierarchicalLoopConnectorSvg", script)
        self.assertIn('data-macro-loop-action="show-all"', script)
        self.assertIn("data.global_loops?.macro_loops", script)
        self.assertIn("macro-relation-dimmed", script)
        self.assertIn('byId("global-loop-canvas").addEventListener("click"', script)

    def test_dual_curve_svg_has_three_lines_valence_and_semantic_markers(self):
        data = valid_analysis(60)
        point = data["global_curves"]["points"][0]
        point["emotion"].update({
            "narrative_score": 4,
            "supporting_score": 0,
            "intensity": 4,
            "valence": "negative",
            "drivers": ["narrative"],
            "event": "角色死亡",
            "reason": "核心关系断裂",
        })
        point["experience"]["score"] = 5
        data["slices"][0]["narrative_climax"]["judgement"] = "climax"
        model = self.run_node(
            f"viewer.globalCurvesViewModel({json.dumps(data, ensure_ascii=False)})"
        )
        html = self.run_node(
            f"viewer.globalCurvesSvgMarkup({json.dumps(model, ensure_ascii=False)},"
            f"viewer.defaultGlobalCurveVisibility())"
        )
        for hook in (
            "global-emotion-line",
            "global-experience-line",
            "global-trend-line",
            "valence-negative",
            "climax-marker",
            "flow-marker",
            'data-curve-slice="0"',
        ):
            self.assertIn(hook, html)
        flow_marker = re.search(
            r'<text class="flow-marker"[^>]* y="([^"]+)"',
            html,
        )
        self.assertIsNotNone(flow_marker)
        self.assertGreaterEqual(
            float(flow_marker.group(1)),
            model["padding"]["top"] + 18,
        )

        hidden = self.run_node(
            f"viewer.globalCurvesSvgMarkup({json.dumps(model, ensure_ascii=False)},"
            "{emotion:false,experience:true,trend:true})"
        )
        self.assertNotIn("global-emotion-line", hidden)
        self.assertIn("global-experience-line", hidden)

        all_hidden = self.run_node(
            f"viewer.globalCurvesSvgMarkup({json.dumps(model, ensure_ascii=False)},"
            "{emotion:false,experience:false,trend:false})"
        )
        self.assertEqual(
            len(model["points"]),
            all_hidden.count('class="curve-slice-hit-zone'),
        )
        self.assertIn('aria-describedby="emotion-curve-tooltip"', all_hidden)

        emotion_only = self.run_node(
            f"viewer.globalCurvesSvgMarkup({json.dumps(model, ensure_ascii=False)},"
            "{emotion:true,experience:false,trend:false})"
        )
        self.assertIn(f'cy="{model["points"][0]["y"]["emotion"]}"', emotion_only)
        self.assertNotIn(f'cy="{model["points"][0]["y"]["experience"]}"', emotion_only)

    def test_dual_curve_legend_toggles_three_series(self):
        result = self.run_node(
            "(()=>{"
            "const initial=viewer.defaultGlobalCurveVisibility();"
            "const hidden=viewer.updateGlobalCurveVisibility(initial,{type:'toggle',series:'emotion'});"
            "const all=viewer.updateGlobalCurveVisibility(hidden,{type:'all'});"
            "return {initial,hidden,all,legend:viewer.globalCurvesLegendMarkup(all)};"
            "})()"
        )
        self.assertTrue(all(result["initial"].values()))
        self.assertFalse(result["hidden"]["emotion"])
        self.assertTrue(all(result["all"].values()))
        self.assertIn('data-curve-action="all"', result["legend"])
        self.assertIn('data-curve-series-toggle="emotion"', result["legend"])
        self.assertIn("情绪强度", result["legend"])
        self.assertIn("体验趋势", result["legend"])

    def test_dual_curve_tooltip_escapes_and_explains_manual_scores(self):
        html = self.run_node(
            "viewer.globalCurvesTooltipMarkup({start:0,end:60,emotionIntensity:5,"
            "narrativeScore:5,supportingScore:2,"
            "emotionDrivers:['narrative','environment_pressure','urgency'],"
            "valence:'<svg onload=bad()>',emotionEvent:'角色死亡',emotionReason:'关系断裂',"
            "experienceScore:2,experienceTrend:2.5,experienceBasis:{"
            "gameplay_concentration:'操作较少',feedback_density:'任务反馈',"
            "goal_challenge:'目标明确',interruption:'<img src=x onerror=bad()>'},"
            "experienceSummary:'玩法被剧情打断'})"
        )
        self.assertNotIn("<img", html)
        self.assertNotIn("<svg", html)
        self.assertIn("&lt;svg onload=bad()&gt;", html)
        self.assertIn("&lt;img src=x onerror=bad()&gt;", html)
        self.assertIn("情绪强度 5.0", html)
        self.assertIn("剧情刺激 5.0", html)
        self.assertIn("其他刺激 2.0", html)
        self.assertIn("剧情", html)
        self.assertIn("环境压力", html)
        self.assertIn("紧迫目标", html)
        self.assertIn("体验强度 2.0", html)
        self.assertIn("玩法浓度", html)
        guide = self.run_node("viewer.globalCurvesGuideMarkup()")
        self.assertIn("剧情为主体", guide)
        self.assertIn("70%", guide)
        self.assertIn("环境压力", guide)
        self.assertTrue(
            self.run_node("viewer.shouldDismissEmotionTooltip({key:'Escape'})")
        )
        self.assertFalse(
            self.run_node("viewer.shouldDismissEmotionTooltip({key:'Enter'})")
        )
        placement = self.run_node(
            "viewer.curveTooltipPlacement({x:500,y:{emotion:18,experience:170}},"
            "{width:1000,height:360},1000,430)"
        )
        self.assertTrue(placement["below"])
        self.assertEqual(50, placement["leftPercent"])
        edge = self.run_node(
            "viewer.curveTooltipPlacement({x:0,y:{emotion:170,experience:170}},"
            "{width:1000,height:360},1000,430)"
        )
        self.assertGreaterEqual(edge["leftPx"], 223)
        self.assertLessEqual(edge["leftPx"], 777)
        css = (ROOT / "assets" / "viewer.css").read_text(encoding="utf-8")
        self.assertRegex(
            css,
            r"@media \(max-width: 540px\)[\s\S]*?"
            r"\.emotion-curve-tooltip\s*\{[^}]*position:\s*fixed;"
            r"[^}]*left:\s*12px\s*!important;[^}]*right:\s*12px;",
        )
        template = (ROOT / "assets" / "viewer.html").read_text(encoding="utf-8")
        self.assertIn(
            'id="emotion-curve-tooltip" class="emotion-curve-tooltip" '
            'role="tooltip"',
            template,
        )
        script = (ROOT / "assets" / "viewer.js").read_text(encoding="utf-8")
        self.assertRegex(
            script,
            r"document\.activeElement[\s\S]*?[Cc]urveSlice[\s\S]*?\.focus\(\)",
        )
        self.assertRegex(
            script,
            r"shouldDismissEmotionTooltip\(event\)[\s\S]*?"
            r"hideEmotionTooltip\(\)",
        )
        self.assertNotIn("hideGlobalLoopTooltip", script)

    def test_highlight_classification_uses_exact_values_and_keeps_multiple_labels(self):
        both = self.run_node(
            "viewer.classifyHighlights({"
            "narrative_climax:{judgement:'climax',reason:'转折'},"
            "flow:{judgement:'flow_peak',reason:'挑战匹配'}})"
        )
        self.assertEqual(["narrative-high", "flow-high"], both)
        false_positive = self.run_node(
            "viewer.classifyHighlights({"
            "narrative_climax:{judgement:'none',reason:'不是高潮'},"
            "flow:{judgement:'none',reason:'不是心流高点'}})"
        )
        self.assertEqual([], false_positive)

    def test_stage_summary_aggregates_distinct_stage_goals(self):
        slices = [
            {
                "stage_range": {"stage_id": "tutorial", "name": "教学", "start": 0, "end": 120},
                "dimensions": {"阶段目标": {"fact": "移动提示", "inference": "学会移动"}},
            },
            {
                "stage_range": {"stage_id": "tutorial", "name": "教学", "start": 0, "end": 120},
                "dimensions": {"阶段目标": {"fact": "战斗提示", "inference": "学会战斗"}},
            },
        ]
        stages = self.run_node(f"viewer.aggregateStages({json.dumps(slices, ensure_ascii=False)})")
        self.assertEqual(
            ["移动提示", "战斗提示"],
            stages[0]["goals"],
        )

    def test_filter_detail_tabs_and_lightbox_pure_behaviors(self):
        slice_data = {
                "start": 60,
                "end": 120,
                "stage_range": {"stage_id": "tutorial", "name": "教学", "start": 0, "end": 120},
                "main_frame": {"path": "screenshots/帧/主#100%.jpg", "timestamp": 90},
                "evidence_frames": [
                    {"path": "screenshots/帧/证据%.jpg", "timestamp": 70}
                ],
                "evidence": [{"frame": "screenshots/帧/证据%.jpg", "note": "出现提示"}],
                "open_questions": ["奖励是否固定"],
                "dimensions": {
                    "阶段目标": {"fact": "", "inference": "不展示"},
                    "任务链": {"fact": "前往营地", "inference": "不展示"},
                    "核心循环": {"fact": "", "inference": ""},
                    "渐进体验": {"fact": "", "inference": ""},
                    "地图体验": {"fact": "", "inference": ""},
                    "经济体验": {"fact": "", "inference": ""},
                    "剧情轴": {"fact": "冲突升级", "inference": "剧情张力上升"},
                },
                "confidence": 0.8,
                "narrative_climax": {"judgement": "climax", "reason": "转折"},
                "flow": {"judgement": "flow_peak", "reason": "挑战匹配"},
        }
        encoded = json.dumps(slice_data, ensure_ascii=False)
        result = self.run_node(
            "({"
            f"match:viewer.matchesSlice({encoded},{{keyword:'冲突',stage:'教学',highlight:'climax'}}),"
            f"miss:viewer.matchesSlice({encoded},{{keyword:'经济',stage:'',highlight:''}}),"
            f"detail:viewer.detailViewModel({encoded},'剧情轴'),"
            f"tabs:viewer.dimensionTabs({encoded},'剧情轴'),"
            f"lightbox:viewer.lightboxViewModel({encoded}.main_frame)"
            "})"
        )
        self.assertTrue(result["match"])
        self.assertFalse(result["miss"])
        self.assertEqual(2, len(result["detail"]["screenshots"]))
        self.assertEqual(["奖励是否固定"], result["detail"]["questions"])
        self.assertEqual("冲突升级", result["detail"]["description"])
        self.assertEqual(80, result["detail"]["confidence"])
        self.assertTrue(result["tabs"][0]["disabled"])
        self.assertTrue(result["tabs"][-1]["active"])
        self.assertEqual(
            "screenshots/%E5%B8%A7/%E4%B8%BB%23100%25.jpg",
            result["lightbox"]["src"],
        )
        self.assertEqual("1:30", result["lightbox"]["caption"])

    def test_malicious_analysis_text_is_escaped_in_detail_html(self):
        slice_data = {
                "start": 0,
                "end": 60,
                "stage_range": {"stage_id": "unsafe", "name": "<img src=x onerror=alert(1)>", "start": 0, "end": 60},
                "main_frame": {"path": "screenshots/main.jpg", "timestamp": 30},
                "evidence_frames": [],
                "evidence": [{"frame": "screenshots/main.jpg", "note": "<script>bad()</script>"}],
                "open_questions": ["<svg onload=bad()>"],
                "dimensions": {
                    "剧情轴": {
                        "fact": "<b onclick=bad()>事实</b>",
                        "inference": "<b onclick=bad()>推断</b>",
                    }
                },
                "confidence": 0.5,
                "narrative_climax": {"judgement": "none", "reason": "<iframe>"},
                "flow": {"judgement": "none", "reason": "<object>"},
        }
        html = self.run_node(
            f"viewer.detailHtml({json.dumps(slice_data, ensure_ascii=False)},'剧情轴')"
        )
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<svg onload", html)
        self.assertNotIn("&lt;script&gt;", html)
        self.assertIn("&lt;b onclick=bad()&gt;事实&lt;/b&gt;", html)

    def test_detail_omits_internal_analysis_and_hides_empty_questions(self):
        data = valid_analysis()["slices"][0]
        data["open_questions"] = []
        html = self.run_node(
            f"viewer.detailHtml({json.dumps(data, ensure_ascii=False)},'阶段目标')"
        )
        self.assertNotIn("推断", html)
        self.assertNotIn("证据", html)
        self.assertNotIn("高潮/低谷", html)
        self.assertNotIn("心流高点", html)
        self.assertNotIn("待确认项", html)
        self.assertIn("置信度", html)
        self.assertIn("dimension-tab", html)

    def test_timeline_selection_moves_between_visible_slices(self):
        result = self.run_node(
            "({"
            "next:viewer.adjacentVisibleIndex(1,1,[true,false,true,true]),"
            "previous:viewer.adjacentVisibleIndex(2,-1,[true,false,true,true]),"
            "edge:viewer.adjacentVisibleIndex(3,1,[true,false,true,true])"
            "})"
        )
        self.assertEqual({"next": 2, "previous": 0, "edge": 3}, result)

    def test_filtered_stage_jump_zero_results_and_global_keyboard_are_safe(self):
        slices = [
            {"stage_range": {"name": "教学"}},
            {"stage_range": {"name": "教学"}},
            {"stage_range": {"name": "探索"}},
        ]
        result = self.run_node(
            "({"
            f"stage:viewer.firstVisibleIndexInStage('教学',{json.dumps(slices, ensure_ascii=False)},[false,true,true]),"
            "empty:viewer.selectedIndexForVisible(1,[false,false,false]),"
            "fallback:viewer.selectedIndexForVisible(1,[true,false,true]),"
            "buttonKey:viewer.timelineKeyDirection({key:'ArrowRight',target:{tagName:'BUTTON'}}),"
            "inputKey:viewer.timelineKeyDirection({key:'ArrowLeft',target:{tagName:'INPUT'}})"
            "})"
        )
        self.assertEqual(
            {
                "stage": 1,
                "empty": -1,
                "fallback": 0,
                "buttonKey": 1,
                "inputKey": 0,
            },
            result,
        )

    def test_timeline_nodes_have_mobile_friendly_hit_targets(self):
        css = (ROOT / "assets" / "viewer.css").read_text(encoding="utf-8")
        self.assertIn(".timeline-node::before", css)
        self.assertIn("width: 24px", css)

    def test_file_fetch_failure_invokes_visible_fallback(self):
        visible = self.run_node_async(
            "viewer.loadInitialData("
            "()=>Promise.reject(new Error('file blocked')),"
            "()=>{throw new Error('must not initialize')},"
            "(error)=>({hidden:false,message:error.message})"
            ")"
        )
        self.assertEqual({"hidden": False, "message": "file blocked"}, visible)

    def test_image_markup_has_visible_load_failure_fallback(self):
        markup = self.run_node(
            "viewer.imageMarkupPure({path:'screenshots/missing.png',timestamp:1})"
        )
        self.assertIn("onerror=", markup)
        self.assertIn("图片加载失败", markup)

    def test_focus_gallery_wraps_and_renders_blurred_side_previews(self):
        frames = [
            {"path": "screenshots/one.jpg", "timestamp": 1},
            {"path": "screenshots/two.jpg", "timestamp": 2},
            {"path": "screenshots/three.jpg", "timestamp": 3},
        ]
        encoded = json.dumps(frames)
        result = self.run_node(
            "({"
            f"model:viewer.galleryViewModel({encoded},0),"
            f"previous:viewer.adjacentGalleryIndex(0,-1,{len(frames)}),"
            f"next:viewer.adjacentGalleryIndex(2,1,{len(frames)}),"
            f"html:viewer.galleryHtml({encoded},0)"
            "})"
        )
        self.assertEqual(2, result["model"]["previousIndex"])
        self.assertEqual(1, result["model"]["nextIndex"])
        self.assertEqual(2, result["previous"])
        self.assertEqual(0, result["next"])
        self.assertIn("gallery-preview previous", result["html"])
        self.assertIn("gallery-preview next", result["html"])
        self.assertIn("gallery-current", result["html"])
        self.assertIn("1 / 3", result["html"])
        self.assertIn("data-gallery-direction", result["html"])

    def test_gallery_container_does_not_shadow_delegated_navigation_targets(self):
        html = self.run_node(
            "viewer.galleryHtml(["
            "{path:'screenshots/one.jpg',timestamp:1},"
            "{path:'screenshots/two.jpg',timestamp:2}"
            "],0)"
        )
        self.assertNotIn('<div class="gallery" data-gallery-index=', html)
        self.assertIn('data-gallery-current-index="0"', html)

    def test_current_gallery_image_is_bounded_by_its_display_shell(self):
        css = (ROOT / "assets" / "viewer.css").read_text(encoding="utf-8")
        self.assertRegex(
            css,
            r"\.gallery-current img\s*\{[^}]*position:\s*absolute;"
            r"[^}]*inset:\s*0;[^}]*width:\s*100%;[^}]*height:\s*100%;"
            r"[^}]*object-fit:\s*contain;",
        )

    def test_single_image_gallery_hides_navigation(self):
        html = self.run_node(
            "viewer.galleryHtml([{path:'screenshots/one.jpg',timestamp:1}],0)"
        )
        self.assertNotIn("data-gallery-direction", html)
        self.assertNotIn("gallery-preview", html)

    def test_keyboard_gallery_rerender_restores_focus(self):
        result = self.run_node(
            "(()=>{"
            "const target={calls:0,focus(options){this.calls++;this.options=options}};"
            "const container={querySelector(selector){this.selector=selector;return target}};"
            "return {restored:viewer.restoreGalleryFocus(container),calls:target.calls,"
            "preventScroll:target.options.preventScroll,selector:container.selector};"
            "})()"
        )
        self.assertEqual(
            {
                "restored": True,
                "calls": 1,
                "preventScroll": True,
                "selector": ".gallery-current [data-lightbox]",
            },
            result,
        )

    def test_lightbox_controller_keyboard_focus_and_restore(self):
        expression = """
        (() => {
          function element() {
            return {
              hidden: true, inert: true, open: false, focused: 0, attrs: {},
              listeners: {},
              classList: { add(){}, remove(){} },
              addEventListener(type, fn) { this.listeners[type] = fn; },
              setAttribute(key, value) { this.attrs[key] = value; },
              removeAttribute(key) { delete this.attrs[key]; },
              focus() { this.focused += 1; },
              showModal() { this.open = true; },
              close() { this.open = false; }
            };
          }
          const dialog=element(), lightboxClose=element(), image=element(), caption=element();
          const doc=element(), imageTrigger=element();
          const controller=viewer.createLightboxController({
            lightbox:dialog, lightboxClose, lightboxImage:image,
            lightboxCaption:caption, documentRef:doc
          });
          controller.openLightbox(imageTrigger, 'safe.jpg', '0:30');
          const lightboxOpened = dialog.open && lightboxClose.focused === 1;
          doc.listeners.keydown({key:'Escape', preventDefault(){}});
          return {
            lightboxOpened,
            closed:!dialog.open && imageTrigger.focused === 1
          };
        })()
        """
        result = self.run_node(expression)
        self.assertEqual(
            {
                "lightboxOpened": True,
                "closed": True,
            },
            result,
        )

    def test_repeated_option_population_replaces_options_and_binds_once(self):
        expression = """
        (() => {
          const select={
            options:[{value:''}],
            append(option){this.options.push(option);}
          };
          const doc={createElement(){return {};}};
          viewer.replaceSelectOptions(select,['教学','探索'],doc);
          viewer.replaceSelectOptions(select,['教学'],doc);
          return select.options.map(option=>option.value);
        })()
        """
        self.assertEqual(["", "教学"], self.run_node(expression))
        script = (ROOT / "assets" / "viewer.js").read_text(encoding="utf-8")
        self.assertIn("overviewTrack.onclick =", script)
        self.assertNotIn('overviewTrack.addEventListener("click"', script)


if __name__ == "__main__":
    unittest.main()
