#!/usr/bin/env python3
"""Build a portable, offline HTML viewer from the unified analysis.json."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path, PureWindowsPath
from typing import Any

try:
    from .analysis_model import dumps_analysis, loads_and_validate
    from .runtime_utils import emit_json_error
except ImportError:
    from analysis_model import dumps_analysis, loads_and_validate
    from runtime_utils import emit_json_error


ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _image_format(path: Path) -> str | None:
    with path.open("rb") as stream:
        header = stream.read(12)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if header.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "GIF"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "WebP"
    return None


def _safe_relative_path(raw_path: str) -> tuple[str, tuple[str, ...]]:
    """Return a browser path and filesystem parts for a safe relative image path."""
    windows_path = PureWindowsPath(raw_path)
    slash_path = raw_path.replace("\\", "/")
    if (
        not slash_path
        or slash_path.startswith("/")
        or windows_path.drive
        or windows_path.is_absolute()
    ):
        raise ValueError(f"截图路径必须是相对路径: {raw_path}")
    raw_parts = slash_path.split("/")
    if any(part == ".." for part in raw_parts):
        raise ValueError(f"截图路径不允许目录穿越: {raw_path}")
    parts = tuple(part for part in raw_parts if part not in ("", "."))
    if not parts:
        raise ValueError(f"截图路径为空: {raw_path}")
    for part in parts:
        if part != part.rstrip(" ."):
            raise ValueError(f"截图路径含 Windows 不允许的尾随点或空格: {raw_path}")
        if ":" in part:
            raise ValueError(f"截图路径不允许 Windows ADS 冒号: {raw_path}")
        if part.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
            raise ValueError(f"截图路径使用 Windows 保留名: {raw_path}")
    return "/".join(parts), parts


def _iter_frame_references(data: dict[str, Any]):
    for item in data["slices"]:
        yield item["main_frame"], "path"
        for frame in item["evidence_frames"]:
            yield frame, "path"
        for evidence in item["evidence"]:
            yield evidence, "frame"
    for node in data["global_loops"]["nodes"]:
        for index in range(len(node["evidence_frames"])):
            yield node["evidence_frames"], index


def _prepare_images(
    data: dict[str, Any], source_root: Path, package_root: Path
) -> dict[str, Any]:
    normalized = copy.deepcopy(data)
    source_root = source_root.resolve()
    destinations: dict[str, str] = {}
    copied: set[str] = set()

    for container, key in _iter_frame_references(normalized):
        raw_path = container[key]
        browser_path, parts = _safe_relative_path(raw_path)
        collision_key = browser_path.casefold()
        previous = destinations.get(collision_key)
        if previous is not None and previous != raw_path:
            raise ValueError(f"截图相对路径重名冲突: {previous} / {raw_path}")
        destinations[collision_key] = raw_path

        source = source_root.joinpath(*parts).resolve()
        try:
            source.relative_to(source_root)
        except ValueError as exc:
            raise ValueError(f"截图路径越出 analysis.json 所在目录: {raw_path}") from exc
        if not source.is_file():
            raise ValueError(f"截图不存在或不是文件: {raw_path}")
        if source.stat().st_size <= 0:
            raise ValueError(f"截图为空: {raw_path}")
        if _image_format(source) is None:
            raise ValueError(
                f"截图格式或魔数无效（仅支持 PNG/JPEG/GIF/WebP）: {raw_path}"
            )

        output_path = f"screenshots/{browser_path}"
        container[key] = output_path
        if browser_path not in copied:
            destination = package_root / "screenshots"
            destination = destination.joinpath(*parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.add(browser_path)
    return normalized


def _render_index() -> str:
    template = (ASSETS_DIR / "viewer.html").read_text(encoding="utf-8")
    css = (ASSETS_DIR / "viewer.css").read_text(encoding="utf-8")
    javascript = (ASSETS_DIR / "viewer.js").read_text(encoding="utf-8")
    return template.replace("/*__VIEWER_CSS__*/", css).replace(
        "/*__VIEWER_JS__*/", javascript
    )


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _journal_path(output: Path) -> Path:
    output = _absolute(output)
    digest = hashlib.sha256(str(output).casefold().encode("utf-8")).hexdigest()[:16]
    return output.parent / f".viewer-transaction-{digest}.json"


def _fsync_directory(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _write_journal(journal: Path, record: dict[str, Any]) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            prefix=f".{journal.name}.",
            suffix=".tmp",
            dir=journal.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, journal)
        temporary = None
        _fsync_directory(journal.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _remove_journal(journal: Path) -> None:
    journal.unlink(missing_ok=True)
    _fsync_directory(journal.parent)


def _transaction_checkpoint(name: str) -> None:
    """Test seam for simulating process interruption at durable boundaries."""


def _validated_record(output: Path, record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("查看器事务 journal 格式错误")
    required = {"version", "state", "output", "backup", "staged", "had_output"}
    if not required.issubset(record):
        raise ValueError("查看器事务 journal 缺少字段")
    expected_output = _absolute(output)
    recorded_output = _absolute(Path(record["output"]))
    backup = _absolute(Path(record["backup"]))
    staged = _absolute(Path(record["staged"]))
    if recorded_output != expected_output:
        raise ValueError("查看器事务 journal 与输出目录不匹配")
    if backup.parent != expected_output.parent or not backup.name.startswith(
        ".viewer-backup-"
    ):
        raise ValueError("查看器事务 backup 路径不安全")
    if staged.parent != expected_output.parent or not staged.name.startswith(
        ".viewer-build-"
    ):
        raise ValueError("查看器事务 staged 路径不安全")
    record = dict(record)
    record.update(output=str(expected_output), backup=str(backup), staged=str(staged))
    return record


def _recover_transaction(output: Path) -> None:
    output = _absolute(output)
    journal = _journal_path(output)
    if not journal.is_file():
        return
    record = _validated_record(
        output, json.loads(journal.read_text(encoding="utf-8"))
    )
    backup = Path(record["backup"])
    staged = Path(record["staged"])
    had_output = bool(record["had_output"])

    if had_output and backup.exists() and not output.exists():
        os.replace(backup, output)
        _fsync_directory(output.parent)
    elif not had_output and not output.exists() and staged.exists():
        os.replace(staged, output)
        _fsync_directory(output.parent)

    if staged.exists() and staged != output:
        shutil.rmtree(staged, ignore_errors=True)
    if backup.exists():
        try:
            shutil.rmtree(backup)
        except OSError:
            return
    _remove_journal(journal)


def _rollback_transaction(record: dict[str, Any], journal: Path) -> None:
    output = Path(record["output"])
    backup = Path(record["backup"])
    staged = Path(record["staged"])
    if record["had_output"] and backup.exists():
        if output.exists():
            shutil.rmtree(output)
        os.replace(backup, output)
        _fsync_directory(output.parent)
    elif not record["had_output"] and output.exists() and not staged.exists():
        shutil.rmtree(output)
    if staged.exists():
        shutil.rmtree(staged, ignore_errors=True)
    _remove_journal(journal)


def _commit_directory(staged: Path, output: Path) -> None:
    staged = _absolute(staged)
    output = _absolute(output)
    if output.exists() and not output.is_dir():
        raise ValueError(f"输出路径已存在且不是目录: {output}")
    backup = output.parent / f".viewer-backup-{uuid.uuid4().hex}"
    journal = _journal_path(output)
    record: dict[str, Any] = {
        "version": 1,
        "state": "prepared",
        "output": str(output),
        "backup": str(backup),
        "staged": str(staged),
        "had_output": output.exists(),
    }
    _write_journal(journal, record)
    try:
        _transaction_checkpoint("after_journal")
        if record["had_output"]:
            os.replace(output, backup)
            _fsync_directory(output.parent)
            _transaction_checkpoint("after_backup_move")
        record["state"] = "old_moved"
        _write_journal(journal, record)
        os.replace(staged, output)
        _fsync_directory(output.parent)
        _transaction_checkpoint("after_new_move")
        record["state"] = "new_committed"
        _write_journal(journal, record)
    except Exception:
        _rollback_transaction(record, journal)
        raise

    if backup.exists():
        try:
            shutil.rmtree(backup)
        except OSError:
            return
    _remove_journal(journal)


def _validate_output_separation(
    analysis_path: Path, data: dict[str, Any], output_dir: Path
) -> None:
    source_root = analysis_path.parent.resolve()
    output_resolved = output_dir.resolve(strict=False)
    if output_resolved == source_root or output_resolved in source_root.parents:
        raise ValueError("输出目录与 analysis.json 输入目录重叠")
    for container, key in _iter_frame_references(data):
        _, parts = _safe_relative_path(container[key])
        source = source_root.joinpath(*parts).resolve()
        if output_resolved == source or output_resolved in source.parents:
            raise ValueError(f"输出目录包含源截图路径，存在输入删除风险: {container[key]}")


def build_package(analysis_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Validate analysis and atomically build an offline viewer package."""
    analysis_path = _absolute(Path(analysis_path))
    output_dir = _absolute(Path(output_dir))
    _recover_transaction(output_dir)
    if not analysis_path.is_file():
        raise FileNotFoundError(f"analysis.json 不存在: {analysis_path}")
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"输出路径已存在且不是目录: {output_dir}")

    data = loads_and_validate(analysis_path.read_text(encoding="utf-8"))
    _validate_output_separation(analysis_path, data, output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(
        tempfile.mkdtemp(prefix=".viewer-build-", dir=output_dir.parent)
    )
    committed = False
    try:
        normalized = _prepare_images(data, analysis_path.parent, staged)
        (staged / "data.json").write_text(
            dumps_analysis(normalized), encoding="utf-8", newline=""
        )
        (staged / "index.html").write_text(
            _render_index(), encoding="utf-8", newline=""
        )
        _commit_directory(staged, output_dir)
        committed = True
        return normalized
    finally:
        if (
            not committed
            and staged.exists()
            and not _journal_path(output_dir).exists()
        ):
            shutil.rmtree(staged, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="构建可移动的游戏前期体验拆解查看器")
    parser.add_argument("analysis", help="统一格式 analysis.json")
    parser.add_argument("--output-dir", required=True, help="查看器包输出目录")
    args = parser.parse_args(argv)
    try:
        build_package(args.analysis, args.output_dir)
        return 0
    except (
        OSError,
        UnicodeError,
        ValueError,
        OverflowError,
    ) as exc:
        emit_json_error(exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
