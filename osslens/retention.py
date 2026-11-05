"""T5 缓存层保留策略（设计方案 v1.3 §8.2「按可再生性分层」为唯一权威）。

分层是**白名单**而非黑名单：只有两类路径被视为可再生缓存——
  * ``data/snapshots/**/src/**``           源码切片（按 commit 可重拉，L1 坑 E7）
  * ``data/llm_cache/**``                  LLM 结果缓存
其余一律视为真源，函数拒绝处理并在 ``protected`` 中列出：
  * ``data/snapshots/**/external/**``     外部资料快照（不可再生真源，红线 #13）
  * ``data/snapshots/**/*.json``          采集快照元数据 + sha256
  * ``data/{ledger,pool,costs}/*.jsonl``  append-only 真源（红线 #6）
  * ``patterns/`` · ``reports/`` · ``config.yaml``

★ 默认 ``dry_run=True``：本模块只提供策略与能力，不擅自改动已入 git 的文件。
清理/归档只在调用方显式 ``dry_run=False`` 时生效，且只作用于缓存层新增写入。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import Config, Layout
from .util import sha256_bytes

SNAPSHOTS = "snapshots"
SRC = "src"
EXTERNAL = "external"
LLM_CACHE = "llm_cache"


@dataclass(frozen=True)
class RetentionResult:
    cache_files: tuple[str, ...]
    unique_objects: tuple[str, ...]
    duplicate_files: tuple[str, ...]
    archived: tuple[str, ...]
    protected: tuple[str, ...]
    bytes_reclaimable: int
    dry_run: bool


def is_cache_layer(path: Path, layout: Layout) -> bool:
    """是否为可再生缓存层文件。真源一律返回 False。"""
    try:
        rel = path.relative_to(layout.data_dir)
    except ValueError:
        return False
    parts = rel.parts
    if not parts:
        return False
    if parts[0] == LLM_CACHE and len(parts) >= 2:
        return True
    if parts[0] == SNAPSHOTS and SRC in parts:
        # src/ 之后的任意深度都算缓存，但 external/ 永不算
        return EXTERNAL not in parts and SRC in parts[2:]
    return False


def cache_files(layout: Layout) -> tuple[Path, ...]:
    """枚举缓存层文件（确定性排序）。快照目录不存在时返回空元组。"""
    found: list[Path] = []
    for base, marker in (
        (layout.snapshots_dir, SRC),
        (layout.data_dir / LLM_CACHE, None),
    ):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            if marker is not None and marker not in path.relative_to(base).parts:
                continue
            if is_cache_layer(path, layout):
                found.append(path)
    return tuple(sorted(set(found)))


def protected_paths(layout: Layout) -> tuple[str, ...]:
    """列出绝不可触碰的真源路径（用于测试断言与验收留痕）。"""
    out: set[str] = set()
    if layout.snapshots_dir.exists():
        for path in layout.snapshots_dir.rglob("*"):
            if path.is_file() and not is_cache_layer(path, layout):
                out.add(_rel(path, layout))
    for name in ("ledger", "pool", "costs"):
        base = layout.data_dir / name
        if base.exists():
            for path in base.rglob("*.jsonl"):
                out.add(_rel(path, layout))
    for name in ("patterns", "reports"):
        base = layout.root / name
        if base.exists():
            for path in base.rglob("*"):
                if path.is_file():
                    out.add(_rel(path, layout))
    cfg = layout.config_file
    if cfg.exists():
        out.add(_rel(cfg, layout))
    return tuple(sorted(out))


def object_path(layout: Layout, digest: str) -> Path:
    return layout.data_dir / "cache_objects" / digest[:2] / digest


def store_object(layout: Layout, data: bytes) -> tuple[Path, bool]:
    """内容寻址：同 sha256 内容只存一份。返回 (路径, 是否新写入)。"""
    target = object_path(layout, sha256_bytes(data))
    if target.exists():
        return target, False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target, True


def dedupe_caches(layout: Layout) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """**纯规划**：计算内容寻址去重结果，不写任何文件。

    返回 (全部缓存文件, 应存在的唯一对象, 内容重复的文件)。
    ``store_object`` 只在 apply_retention(dry_run=False) 时调用。
    """
    files = cache_files(layout)
    seen: dict[str, Path] = {}
    unique: set[str] = set()
    duplicates: list[str] = []
    for path in files:
        digest = sha256_bytes(path.read_bytes())
        unique.add(_rel(object_path(layout, digest), layout))
        if digest in seen and seen[digest] != path:
            duplicates.append(_rel(path, layout))
        seen.setdefault(digest, path)
    return tuple(_rel(p, layout) for p in files), tuple(sorted(unique)), tuple(duplicates)


def _snapshot_date(path: Path, layout: Layout) -> str | None:
    """归档基准日期。

    ``snapshots/<owner>__<repo>/<YYYY-MM-DD>/src/...`` 取路径里的日期段（确定性）；
    ``llm_cache/`` 等无日期语义的缓存取文件 mtime 的 UTC 日期（运维语义，不参与报告时间，
    不违反红线 #8——红线只约束报告时间来自 --as-of）。
    """
    try:
        parts = path.relative_to(layout.snapshots_dir).parts
    except ValueError:
        parts = ()
    for part in parts:
        if len(part) == 10 and part[4] == "-" and part[7] == "-":
            try:
                datetime.strptime(part, "%Y-%m-%d")
                return part
            except ValueError:
                continue
    if path.is_file():
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).strftime("%Y-%m-%d")
    return None


def plan_archive(layout: Layout, config: Config, as_of: datetime) -> tuple[Path, ...]:
    """列出超过保留期的缓存层文件（``cache_keep_days``），真源永不入列。"""
    if not config.retention.enabled:
        return ()
    cutoff = as_of - timedelta(days=config.retention.cache_keep_days)
    out: list[Path] = []
    for path in cache_files(layout):
        stamp = _snapshot_date(path, layout)
        if stamp is None:
            continue
        if datetime.strptime(stamp, "%Y-%m-%d").date() < cutoff.date():
            out.append(path)
    return tuple(sorted(out))


def apply_retention(
    layout: Layout, config: Config, as_of: datetime, *, dry_run: bool = True
) -> RetentionResult:
    """执行保留策略。dry_run=True 只规划不落盘；dry_run=False 归档缓存层文件到 archive_dir。

    ★ 归档只移动缓存层文件；``external/``、快照元数据、三个 jsonl 真源绝不进入移动清单。
    """
    files, unique, duplicates = dedupe_caches(layout)
    candidates = plan_archive(layout, config, as_of)
    archive_root = layout.root / config.retention.archive_dir
    archived: list[str] = []
    reclaimable = 0
    if not dry_run:
        # 内容寻址对象：同 sha256 只落盘一次（可再生索引，不触碰真源）
        for path in cache_files(layout):
            store_object(layout, path.read_bytes())
    for path in candidates:
        reclaimable += path.stat().st_size
        if not dry_run:
            target = archive_root / _rel(path, layout)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(target))
        archived.append(_rel(path, layout))
    return RetentionResult(
        cache_files=files,
        unique_objects=unique,
        duplicate_files=duplicates,
        archived=tuple(archived),
        protected=protected_paths(layout),
        bytes_reclaimable=reclaimable,
        dry_run=dry_run,
    )


def _rel(path: Path, layout: Layout) -> str:
    try:
        return path.relative_to(layout.root).as_posix()
    except ValueError:
        return path.as_posix()
