#!/usr/bin/env python3
"""Probe video duration and generate progressive, half-open time slices."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from .runtime_utils import atomic_write_text, emit_json_error
except ImportError:
    from runtime_utils import atomic_write_text, emit_json_error


class ToolError(RuntimeError):
    """Raised when an external video tool cannot be used."""


def generate_timeline(duration: float) -> list[dict[str, int | float]]:
    """Return slices for a positive finite duration measured in seconds."""
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise ValueError("视频时长必须是数字")
    duration = float(duration)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("视频时长必须是大于 0 的有限数")
    maximum_slices = 1_000_000
    maximum_duration = 60 * 60 + (maximum_slices - 36) * 10 * 60
    if duration > maximum_duration:
        raise ValueError(f"视频时长过大，最多支持 {maximum_slices} 个时间片")

    slices: list[dict[str, int | float]] = []
    start = 0.0
    while start < duration:
        if start < 30 * 60:
            step = 60.0
        elif start < 60 * 60:
            step = 5 * 60.0
        else:
            step = 10 * 60.0
        end = min(start + step, duration)
        slices.append({"index": len(slices), "start": start, "end": end})
        start = end
    return slices


def generate_time_slices(duration: float) -> list[dict[str, int | float]]:
    """Backward-compatible alias for generate_timeline."""
    return generate_timeline(duration)


def probe_duration(
    video_path: str | Path, ffprobe: str = "ffprobe", timeout: float = 6.5
) -> float:
    """Use ffprobe to read a video's duration in seconds."""
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f"输入视频不存在: {path}")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("ffprobe timeout 必须是大于 0 的有限数")
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
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
        raise ToolError(f"ffprobe 执行超时（{timeout} 秒）") from exc
    except FileNotFoundError as exc:
        raise ToolError(f"找不到 ffprobe，请安装 FFmpeg 并确保 ffprobe 位于 PATH") from exc
    except (OSError, UnicodeError) as exc:
        raise ToolError(f"无法执行 ffprobe: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "未知错误"
        raise ToolError(f"ffprobe 执行失败（退出码 {result.returncode}）: {detail}")
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise ToolError(f"ffprobe 返回了非法时长: {result.stdout.strip()!r}") from exc
    generate_timeline(duration)
    return duration


def _write_json(payload: Any, stream: Any = None) -> None:
    stream = stream or sys.stdout
    stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="探测视频时长并生成渐进时间片")
    parser.add_argument("video", help="输入视频路径")
    parser.add_argument("--ffprobe", default="ffprobe", help="ffprobe 可执行文件")
    parser.add_argument(
        "--ffprobe-timeout",
        type=float,
        default=6.5,
        help="ffprobe 超时秒数（默认 6.5）",
    )
    parser.add_argument("--output", help="输出 JSON 文件；省略时写入标准输出")
    args = parser.parse_args(argv)
    try:
        duration = probe_duration(args.video, args.ffprobe, args.ffprobe_timeout)
        payload = {
            "video": {
                "path": Path(args.video).as_posix(),
                "duration_seconds": duration,
            },
            "slices": generate_timeline(duration),
        }
        if args.output:
            atomic_write_text(
                args.output, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
            )
        else:
            _write_json(payload)
        return 0
    except (OSError, UnicodeError, ToolError, ValueError, OverflowError) as exc:
        emit_json_error(exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
