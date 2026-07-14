import importlib
import io
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import analysis_model
import extract_frames
import video_timeline
from test_video_analysis_pipeline import valid_analysis


def completed(returncode=0, stderr="", stdout=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


class FrameExtractionQualityTests(unittest.TestCase):
    def test_ffmpeg_timeout_is_configurable_and_controlled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video.mp4"
            video.write_bytes(b"video")
            with mock.patch(
                "extract_frames.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["ffmpeg"], 2.5),
            ) as run:
                with self.assertRaisesRegex(extract_frames.ToolError, "超时"):
                    extract_frames.extract_frames(
                        video,
                        root / "frames",
                        [{"timestamp": 0.5, "filename": "frame.jpg"}],
                        timeout=2.5,
                    )
            self.assertEqual(2.5, run.call_args.kwargs["timeout"])

    def test_ffmpeg_uses_round_trip_precision_and_matching_mapping_timestamp(self):
        with tempfile.TemporaryDirectory(prefix="抽帧-") as directory:
            root = Path(directory)
            video = root / "视频.mp4"
            video.write_bytes(b"video")
            timestamp = math.nextafter(1.0, 0.0)
            plan = [{"timestamp": timestamp, "filename": "截图.jpg"}]
            calls = []

            def fake_run(command, **kwargs):
                calls.append((command, kwargs))
                Path(command[-1]).write_bytes(b"jpeg")
                return completed()

            with mock.patch("extract_frames.subprocess.run", side_effect=fake_run):
                mappings = extract_frames.extract_frames(video, root / "输出", plan)

            command, kwargs = calls[0]
            command_timestamp = float(command[command.index("-ss") + 1])
            self.assertEqual(timestamp, command_timestamp)
            self.assertEqual(timestamp, mappings[0]["timestamp"])
            self.assertLess(command_timestamp, 1.0)
            self.assertEqual("utf-8", kwargs["encoding"])
            self.assertEqual("replace", kwargs["errors"])
            self.assertEqual(7.5, kwargs["timeout"])
            self.assertGreater((root / "输出" / "截图.jpg").stat().st_size, 0)

    def test_nonzero_ffmpeg_with_replacement_character_is_controlled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video.mp4"
            video.write_bytes(b"video")
            with mock.patch(
                "extract_frames.subprocess.run",
                return_value=completed(returncode=9, stderr="bad \ufffd stderr"),
            ):
                with self.assertRaisesRegex(extract_frames.ToolError, "bad \ufffd stderr"):
                    extract_frames.extract_frames(
                        video,
                        root / "frames",
                        [{"timestamp": 0.5, "filename": "frame.jpg"}],
                    )

    def test_ffmpeg_timeout_is_controlled_and_configurable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video.mp4"
            video.write_bytes(b"video")
            with mock.patch(
                "extract_frames.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["ffmpeg"], 2.5),
            ) as run:
                with self.assertRaisesRegex(extract_frames.ToolError, "超时|timeout"):
                    extract_frames.extract_frames(
                        video,
                        root / "frames",
                        [{"timestamp": 0.5, "filename": "frame.jpg"}],
                        timeout=2.5,
                    )
            self.assertEqual(2.5, run.call_args.kwargs["timeout"])

    def test_batch_failure_does_not_replace_existing_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video.mp4"
            video.write_bytes(b"video")
            output = root / "frames"
            output.mkdir()
            (output / "one.jpg").write_bytes(b"old-one")
            (output / "two.jpg").write_bytes(b"old-two")
            attempts = 0

            def fail_second(command, **kwargs):
                nonlocal attempts
                attempts += 1
                Path(command[-1]).write_bytes(b"new")
                return completed() if attempts == 1 else completed(3, "decode \ufffd")

            plan = [
                {"timestamp": 0.25, "filename": "one.jpg"},
                {"timestamp": 0.75, "filename": "two.jpg"},
            ]
            with mock.patch("extract_frames.subprocess.run", side_effect=fail_second):
                with self.assertRaises(extract_frames.ToolError):
                    extract_frames.extract_frames(video, output, plan)

            self.assertEqual(b"old-one", (output / "one.jpg").read_bytes())
            self.assertEqual(b"old-two", (output / "two.jpg").read_bytes())


class SubprocessAndTimelineQualityTests(unittest.TestCase):
    def test_ffprobe_timeout_is_configurable_and_controlled(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "video.mp4"
            video.write_bytes(b"x")
            with mock.patch(
                "video_timeline.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["ffprobe"], 1.25),
            ) as run:
                with self.assertRaisesRegex(video_timeline.ToolError, "超时"):
                    video_timeline.probe_duration(video, timeout=1.25)
            self.assertEqual(1.25, run.call_args.kwargs["timeout"])

    def test_ffprobe_sets_utf8_replacement_decoding(self):
        with tempfile.TemporaryDirectory(prefix="探测-") as directory:
            video = Path(directory) / "视频.mp4"
            video.write_bytes(b"x")
            with mock.patch(
                "video_timeline.subprocess.run",
                return_value=completed(stdout="12.5"),
            ) as run:
                self.assertEqual(12.5, video_timeline.probe_duration(video))
            self.assertEqual("utf-8", run.call_args.kwargs["encoding"])
            self.assertEqual("replace", run.call_args.kwargs["errors"])
            self.assertEqual(6.5, run.call_args.kwargs["timeout"])

    def test_ffprobe_timeout_is_controlled_and_configurable(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "video.mp4"
            video.write_bytes(b"x")
            with mock.patch(
                "video_timeline.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["ffprobe"], 1.25),
            ) as run:
                with self.assertRaisesRegex(video_timeline.ToolError, "超时|timeout"):
                    video_timeline.probe_duration(video, timeout=1.25)
            self.assertEqual(1.25, run.call_args.kwargs["timeout"])

    def test_huge_duration_is_rejected_without_looping_or_overflow(self):
        with self.assertRaisesRegex(ValueError, "过大|too large"):
            video_timeline.generate_timeline(sys.float_info.max)

    def test_modules_support_package_imports(self):
        sys.path.insert(0, str(ROOT))
        try:
            imported_analysis = importlib.import_module("scripts.analysis_model")
            imported_extract = importlib.import_module("scripts.extract_frames")
        finally:
            sys.path.remove(str(ROOT))
        self.assertTrue(callable(imported_analysis.validate_analysis))
        self.assertTrue(callable(imported_extract.extract_frames))


class CliJsonAndAtomicOutputTests(unittest.TestCase):
    def assert_json_error(self, callable_main, argv):
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            code = callable_main(argv)
        self.assertEqual(2, code)
        payload = json.loads(stderr.getvalue())
        self.assertEqual({"type", "message"}, set(payload["error"]))
        self.assertTrue(payload["error"]["message"])

    def test_all_three_clis_use_json_error_protocol_and_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / "不存在.mp4")
            self.assert_json_error(video_timeline.main, [missing])
            self.assert_json_error(
                extract_frames.main, [missing, "--output-dir", directory]
            )
            self.assert_json_error(analysis_model.main, [missing])

    def test_timeline_cli_atomically_writes_nonempty_unicode_output(self):
        with tempfile.TemporaryDirectory(prefix="时间线-") as directory:
            root = Path(directory)
            video = root / "视频.mp4"
            video.write_bytes(b"x")
            output = root / "结果.json"
            output.write_text("old", encoding="utf-8")
            with mock.patch("video_timeline.probe_duration", return_value=12.5):
                self.assertEqual(
                    0, video_timeline.main([str(video), "--output", str(output)])
                )
            self.assertGreater(output.stat().st_size, 0)
            self.assertEqual(12.5, json.loads(output.read_text("utf-8"))["video"]["duration_seconds"])

    def test_analysis_cli_atomically_writes_nonempty_unicode_output(self):
        with tempfile.TemporaryDirectory(prefix="分析-") as directory:
            root = Path(directory)
            source = root / "输入.json"
            source.write_text(
                json.dumps(valid_analysis(), ensure_ascii=False), encoding="utf-8"
            )
            output = root / "输出.json"
            output.write_text("old", encoding="utf-8")
            self.assertEqual(
                0, analysis_model.main([str(source), "--output", str(output)])
            )
            self.assertGreater(output.stat().st_size, 0)
            self.assertIn("阶段目标", output.read_text("utf-8"))

    def test_extract_cli_atomically_writes_frames_and_mapping(self):
        with tempfile.TemporaryDirectory(prefix="截图-") as directory:
            root = Path(directory)
            video = root / "视频.mp4"
            video.write_bytes(b"x")
            output_dir = root / "帧"
            mapping = root / "映射.json"
            mapping.write_text("old", encoding="utf-8")

            def fake_run(command, **kwargs):
                Path(command[-1]).write_bytes(b"jpeg")
                return completed()

            with (
                mock.patch("extract_frames.probe_duration", return_value=12.5),
                mock.patch("extract_frames.subprocess.run", side_effect=fake_run),
            ):
                code = extract_frames.main(
                    [
                        str(video),
                        "--output-dir",
                        str(output_dir),
                        "--mapping-output",
                        str(mapping),
                    ]
                )
            self.assertEqual(0, code)
            payload = json.loads(mapping.read_text("utf-8"))
            self.assertGreater(mapping.stat().st_size, 0)
            self.assertGreater(Path(payload["frames"][0]["path"]).stat().st_size, 0)

    def test_mapping_commit_failure_rolls_back_frames_and_old_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video.mp4"
            video.write_bytes(b"x")
            output_dir = root / "frames"
            output_dir.mkdir()
            old_frame = output_dir / "slice-000-main-000006250.jpg"
            old_frame.write_bytes(b"old-frame")
            mapping = root / "mapping.json"
            mapping.write_bytes(b"old-mapping")
            stderr = io.StringIO()

            def fake_run(command, **kwargs):
                Path(command[-1]).write_bytes(b"new-frame")
                return completed()

            with (
                mock.patch("extract_frames.probe_duration", return_value=12.5),
                mock.patch("extract_frames.subprocess.run", side_effect=fake_run),
                mock.patch(
                    "extract_frames.atomic_write_text",
                    side_effect=PermissionError("mapping denied"),
                ),
                mock.patch("sys.stderr", stderr),
            ):
                code = extract_frames.main(
                    [
                        str(video),
                        "--output-dir",
                        str(output_dir),
                        "--mapping-output",
                        str(mapping),
                    ]
                )

            self.assertEqual(2, code)
            self.assertEqual(b"old-frame", old_frame.read_bytes())
            self.assertEqual(b"old-mapping", mapping.read_bytes())
            self.assertFalse(
                any(path.name.startswith(".frames-batch-") for path in root.iterdir())
            )
            self.assertEqual(
                "PermissionError", json.loads(stderr.getvalue())["error"]["type"]
            )

    def test_mapping_failure_rolls_back_all_frames_and_old_mapping(self):
        with tempfile.TemporaryDirectory(prefix="事务-") as directory:
            root = Path(directory)
            video = root / "video.mp4"
            video.write_bytes(b"x")
            output_dir = root / "frames"
            output_dir.mkdir()
            frame = output_dir / "slice-000-main-000006250.jpg"
            frame.write_bytes(b"old-frame")
            mapping = root / "mapping.json"
            mapping.write_bytes(b"old-mapping")

            def fake_run(command, **kwargs):
                Path(command[-1]).write_bytes(b"new-frame")
                return completed()

            stderr = io.StringIO()
            with (
                mock.patch("extract_frames.probe_duration", return_value=12.5),
                mock.patch("extract_frames.subprocess.run", side_effect=fake_run),
                mock.patch(
                    "extract_frames.atomic_write_text",
                    side_effect=PermissionError("mapping denied"),
                ),
                mock.patch("sys.stderr", stderr),
            ):
                code = extract_frames.main(
                    [
                        str(video),
                        "--output-dir",
                        str(output_dir),
                        "--mapping-output",
                        str(mapping),
                    ]
                )

            self.assertEqual(2, code)
            self.assertEqual(b"old-frame", frame.read_bytes())
            self.assertEqual(b"old-mapping", mapping.read_bytes())
            self.assertEqual(
                "PermissionError", json.loads(stderr.getvalue())["error"]["type"]
            )
            self.assertFalse(
                any(path.name.startswith(".frames-batch-") for path in root.iterdir())
            )

    def test_atomic_output_failure_preserves_old_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "video.mp4"
            video.write_bytes(b"x")
            output = root / "timeline.json"
            output.write_bytes(b"old-json")
            stderr = io.StringIO()
            with (
                mock.patch("video_timeline.probe_duration", return_value=12.5),
                mock.patch("os.replace", side_effect=PermissionError("denied")),
                mock.patch("sys.stderr", stderr),
            ):
                code = video_timeline.main([str(video), "--output", str(output)])
            self.assertEqual(2, code)
            self.assertEqual(b"old-json", output.read_bytes())
            self.assertEqual("PermissionError", json.loads(stderr.getvalue())["error"]["type"])


if __name__ == "__main__":
    unittest.main()
