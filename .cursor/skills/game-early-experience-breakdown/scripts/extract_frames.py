#!/usr/bin/env python3
"""Extract one main frame and optional evidence frames for each video slice."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:
    from .runtime_utils import atomic_write_text, emit_json_error
    from .video_timeline import (
        ToolError,
        generate_review_points,
        generate_timeline,
        probe_duration,
    )
except ImportError:
    from runtime_utils import atomic_write_text, emit_json_error
    from video_timeline import ToolError, generate_review_points, generate_timeline, probe_duration


def _stable_filename(
    slice_index: int, kind: str, timestamp: float, evidence_index: int | None = None
) -> str:
    milliseconds = round(timestamp * 1000)
    if kind == "main":
        label = "main"
    else:
        label = f"evidence-{evidence_index:02d}"
    return f"slice-{slice_index:03d}-{label}-{milliseconds:09d}.jpg"


def build_capture_plan(
    slices: list[dict[str, Any]],
    video_duration: float,
    evidence_times: dict[str | int, list[float]] | None = None,
) -> list[dict[str, Any]]:
    """Build deterministic frame jobs; evidence timestamps are absolute seconds."""
    evidence_times = evidence_times or {}
    plan: list[dict[str, Any]] = []
    for item in slices:
        index = int(item["index"])
        start = float(item["start"])
        end = float(item["end"])
        if start < 0 or end <= start or end > video_duration:
            raise ValueError(f"时间片 {index} 超出视频范围")

        midpoint = start + (end - start) / 2
        plan.append(
            {
                "slice_index": index,
                "kind": "main",
                "timestamp": midpoint,
                "filename": _stable_filename(index, "main", midpoint),
            }
        )
        extras = evidence_times.get(str(index), evidence_times.get(index, []))
        if extras is None:
            extras = []
        if not isinstance(extras, list):
            raise ValueError(f"时间片 {index} 的证据时间点必须是数组")
        if len(extras) > 3:
            raise ValueError(f"时间片 {index} 最多允许 3 张证据图（额外时间点 1-3 个）")
        for evidence_index, raw_timestamp in enumerate(extras, start=1):
            if isinstance(raw_timestamp, bool) or not isinstance(raw_timestamp, (int, float)):
                raise ValueError(f"时间片 {index} 的证据时间点必须是数字")
            timestamp = float(raw_timestamp)
            if not math.isfinite(timestamp) or not (start <= timestamp < end):
                raise ValueError(
                    f"证据时间 {timestamp} 不在时间片 {index} 的左闭右开范围 [{start}, {end})"
                )
            if not (0 <= timestamp < video_duration):
                raise ValueError(f"证据时间 {timestamp} 超出视频范围")
            plan.append(
                {
                    "slice_index": index,
                    "kind": "evidence",
                    "evidence_index": evidence_index,
                    "timestamp": timestamp,
                    "filename": _stable_filename(
                        index, "evidence", timestamp, evidence_index
                    ),
                }
            )
    return plan


def _rollback_frames(committed: list[tuple[Path, Path | None]]) -> None:
    for final_target, backup in reversed(committed):
        if backup is None:
            try:
                final_target.unlink()
            except FileNotFoundError:
                pass
        else:
            os.replace(backup, final_target)


@contextmanager
def frame_batch_transaction(
    video_path: str | Path,
    output_dir: str | Path,
    plan: list[dict[str, Any]],
    ffmpeg: str = "ffmpeg",
    timeout: float = 7.5,
) -> Iterator[list[dict[str, Any]]]:
    """Commit frames, retaining rollback backups until the context succeeds."""
    video = Path(video_path)
    if not video.is_file():
        raise FileNotFoundError(f"输入视频不存在: {video}")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("ffmpeg timeout 必须是大于 0 的有限数")
    output = Path(output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    mappings: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(
        prefix=f".{output.name}-batch-", dir=output.parent
    ) as temporary_directory:
        staging = Path(temporary_directory)
        staged_files: list[tuple[Path, Path]] = []
        for job in plan:
            final_target = output / job["filename"]
            staged_target = staging / job["filename"]
            timestamp = float(job["timestamp"])
            command = [
                ffmpeg,
                "-v",
                "error",
                "-ss",
                format(timestamp, ".17g"),
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-y",
                str(staged_target),
            ]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise ToolError(
                    f"ffmpeg 抽帧超时（时间 {timestamp} 秒，超时 {timeout} 秒）"
                ) from exc
            except FileNotFoundError as exc:
                raise ToolError(
                    "找不到 ffmpeg，请安装 FFmpeg 并确保 ffmpeg 位于 PATH"
                ) from exc
            except (OSError, UnicodeError) as exc:
                raise ToolError(f"无法执行 ffmpeg: {exc}") from exc
            if result.returncode != 0:
                detail = result.stderr.strip() or "未知错误"
                raise ToolError(
                    f"ffmpeg 抽帧失败（时间 {timestamp} 秒，退出码 "
                    f"{result.returncode}）: {detail}"
                )
            if not staged_target.is_file() or staged_target.stat().st_size <= 0:
                raise ToolError(f"ffmpeg 未生成有效截图: {job['filename']}")
            staged_files.append((staged_target, final_target))
            mapping = dict(job)
            mapping["timestamp"] = timestamp
            mapping["path"] = final_target.as_posix()
            mappings.append(mapping)

        output.mkdir(parents=True, exist_ok=True)
        backups = staging / ".backups"
        backups.mkdir()
        committed: list[tuple[Path, Path | None]] = []
        try:
            for staged_target, final_target in staged_files:
                backup: Path | None = None
                if final_target.exists():
                    backup = backups / final_target.name
                    shutil.copy2(final_target, backup)
                os.replace(staged_target, final_target)
                committed.append((final_target, backup))
        except (OSError, UnicodeError):
            _rollback_frames(committed)
            raise
        try:
            yield mappings
        except BaseException:
            _rollback_frames(committed)
            raise


def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    plan: list[dict[str, Any]],
    ffmpeg: str = "ffmpeg",
    timeout: float = 7.5,
) -> list[dict[str, Any]]:
    """Extract and atomically commit a standalone frame batch."""
    with frame_batch_transaction(
        video_path, output_dir, plan, ffmpeg=ffmpeg, timeout=timeout
    ) as mappings:
        return mappings


def _load_evidence_config(path: str | None) -> dict[str | int, list[float]]:
    if not path:
        return {}
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"证据配置不存在: {config_path}")
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"证据配置不是合法 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("证据配置根节点必须是对象")
    candidate = data.get("evidence_times", data)
    if not isinstance(candidate, dict):
        raise ValueError("evidence_times 必须是以时间片索引为键的对象")
    return candidate


def _write_json(payload: Any, stream: Any = None) -> None:
    stream = stream or sys.stdout
    stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按渐进时间片抽取主截图和证据截图")
    parser.add_argument("video", help="输入视频路径")
    parser.add_argument("--output-dir", required=True, help="截图输出目录")
    parser.add_argument("--evidence-config", help="额外证据时间点 JSON")
    parser.add_argument("--mapping-output", help="时间戳映射 JSON；省略时写标准输出")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg 可执行文件")
    parser.add_argument("--ffprobe", default="ffprobe", help="ffprobe 可执行文件")
    parser.add_argument(
        "--ffmpeg-timeout",
        type=float,
        default=7.5,
        help="每张截图的 ffmpeg 超时秒数（默认 7.5）",
    )
    parser.add_argument(
        "--ffprobe-timeout",
        type=float,
        default=6.5,
        help="ffprobe 超时秒数（默认 6.5）",
    )
    args = parser.parse_args(argv)
    try:
        video = Path(args.video)
        if not video.is_file():
            raise FileNotFoundError(f"输入视频不存在: {video}")
        duration = probe_duration(video, args.ffprobe, args.ffprobe_timeout)
        slices = generate_timeline(duration)
        plan = build_capture_plan(
            slices, duration, _load_evidence_config(args.evidence_config)
        )
        with frame_batch_transaction(
            video,
            args.output_dir,
            plan,
            ffmpeg=args.ffmpeg,
            timeout=args.ffmpeg_timeout,
        ) as frames:
            payload = {
                "video": {"path": video.as_posix(), "duration_seconds": duration},
                "slices": slices,
                "review_points": generate_review_points(duration),
                "frames": frames,
            }
            text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
            if args.mapping_output:
                atomic_write_text(args.mapping_output, text)
            else:
                sys.stdout.write(text)
        return 0
    except (OSError, UnicodeError, ToolError, ValueError, OverflowError) as exc:
        emit_json_error(exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
