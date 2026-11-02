"""配置加载：唯一真源 `config.yaml` + 环境变量。

红线 #23：阈值一律来自配置，代码不硬编码。`DEFAULT_CONFIG` 只是**默认值**，
`init` 会把它落成带注释的 `config.yaml`，此后以文件为准。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .util import ConfigError, as_bool, as_float, as_int, as_str

CONFIG_FILENAME = "config.yaml"

DEFAULT_CONFIG: dict[str, Any] = {
    "github_token_env": "GITHUB_TOKEN",
    "github_base_url": "https://api.github.com",
    "llm": {
        "api_key_env": "OSSLENS_LLM_API_KEY",
        "base_url_env": "OSSLENS_LLM_BASE_URL",
        "model_env": "OSSLENS_LLM_MODEL",
        "price_table": {},
    },
    "depth": {
        "weekly_quota": {"strong": 1, "fast": 3},
        "budget": {
            "weekly_tokens": 2_000_000,
            "monthly_tokens": 6_000_000,
            "per_run_prompt_tokens": 120_000,
        },
        "baseline": {"hot": "fast", "classic": "strong", "watchlist": "strong"},
    },
    "pool": {
        "hot_min_star_delta_7d": 200,
        "hot_observe_days": 7,
        "classic_min_stars": 5000,
        "classic_min_age_days": 730,
        "dedupe": True,
    },
    "score": {
        "hot": {"star_delta_7d": 1.0, "stars": 0.6, "fork_delta_7d": 0.4},
        "classic": {"stars": 1.0, "observations": 0.7},
    },
    "watchlist": [],
}

CONFIG_TEMPLATE = """\
# osslens 唯一配置真源。由 `python -m osslens init` 生成。
# 阈值改动只改这里，代码不硬编码。
github_token_env: GITHUB_TOKEN
github_base_url: https://api.github.com

llm:
  # 缺任一变量 → 自动降级 off，退出码 0（红线 #3）
  api_key_env: OSSLENS_LLM_API_KEY
  base_url_env: OSSLENS_LLM_BASE_URL
  model_env: OSSLENS_LLM_MODEL
  # 单价表由项目负责人填写；代码不内置任何价格（设计方案 §9）
  # 例：price_table:
  #   <model-id>: {prompt_per_1m: 0.0, completion_per_1m: 0.0}
  price_table: {}

depth:
  # 周配额（设计方案 §11）
  weekly_quota:
    strong: 1
    fast: 3
  budget:
    weekly_tokens: 2000000
    monthly_tokens: 6000000
    per_run_prompt_tokens: 120000
  # 通道基线（设计方案 §2 L1）
  baseline:
    hot: fast
    classic: strong
    watchlist: strong

pool:
  hot_min_star_delta_7d: 200
  hot_observe_days: 7
  classic_min_stars: 5000
  classic_min_age_days: 730
  dedupe: true

score:
  # 权重来自设计方案 §6.1；分数只用于排序，绝不用于升档
  hot: {star_delta_7d: 1.0, stars: 0.6, fork_delta_7d: 0.4}
  classic: {stars: 1.0, observations: 0.7}

# 意图层，不是入口过滤器（设计方案 §6.4）
watchlist: []
"""


@dataclass(frozen=True)
class PoolConfig:
    hot_min_star_delta_7d: int
    hot_observe_days: int
    classic_min_stars: int
    classic_min_age_days: int
    dedupe: bool


@dataclass(frozen=True)
class BudgetConfig:
    weekly_tokens: int
    monthly_tokens: int
    per_run_prompt_tokens: int


@dataclass(frozen=True)
class DepthConfig:
    weekly_quota: dict[str, int]
    budget: BudgetConfig
    baseline: dict[str, str]


@dataclass(frozen=True)
class PriceEntry:
    prompt_per_1m: float
    completion_per_1m: float


@dataclass(frozen=True)
class LlmConfig:
    api_key_env: str
    base_url_env: str
    model_env: str
    price_table: dict[str, PriceEntry]


@dataclass(frozen=True)
class ScoreConfig:
    hot: dict[str, float]
    classic: dict[str, float]


@dataclass(frozen=True)
class LlmCredentials:
    api_key: str
    base_url: str
    model: str

    def redacted(self) -> str:
        return f"{self.model}@{self.base_url} (key=***{len(self.api_key)})"


@dataclass(frozen=True)
class Layout:
    """数据布局（设计方案 §8）。"""

    root: Path

    @property
    def config_file(self) -> Path:
        return self.root / CONFIG_FILENAME

    @property
    def patterns_dir(self) -> Path:
        return self.root / "patterns"

    @property
    def seed_patterns(self) -> Path:
        return self.patterns_dir / "seed.yaml"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def selected_jsonl(self) -> Path:
        return self.data_dir / "ledger" / "selected.jsonl"

    @property
    def pool_jsonl(self) -> Path:
        return self.data_dir / "pool" / "pool.jsonl"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def featcards_dir(self) -> Path:
        return self.data_dir / "featcards"

    @property
    def costs_jsonl(self) -> Path:
        return self.data_dir / "costs" / "costs.jsonl"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    def report_path(self, owner: str, repo: str, date: str) -> Path:
        return self.reports_dir / f"{owner}__{repo}__{date}.md"

    def featcard_path(self, owner: str, repo: str, commit: str) -> Path:
        return self.featcards_dir / f"{owner}__{repo}__{commit}.json"

    def snapshot_dir(self, owner: str, repo: str) -> Path:
        return self.snapshots_dir / f"{owner}__{repo}"

    def ensure_skeleton(self) -> None:
        for path in (
            self.patterns_dir,
            self.data_dir / "ledger",
            self.data_dir / "pool",
            self.data_dir / "snapshots",
            self.data_dir / "featcards",
            self.data_dir / "costs",
            self.reports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Config:
    layout: Layout
    github_token_env: str
    github_base_url: str
    llm: LlmConfig
    depth: DepthConfig
    pool: PoolConfig
    score: ScoreConfig
    watchlist: tuple[str, ...] = field(default_factory=tuple)

    # ------------------------------------------------------------------ 加载

    @classmethod
    def load(cls, root: Path) -> Config:
        layout = Layout(root.resolve())
        if not layout.config_file.exists():
            raise ConfigError(f"未找到 {layout.config_file}；请先运行 `python -m osslens init`")
        raw_text = layout.config_file.read_text(encoding="utf-8")
        try:
            parsed = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise ConfigError(f"{CONFIG_FILENAME} 解析失败：{exc}") from exc
        if parsed is None:
            parsed = {}
        if not isinstance(parsed, dict):
            raise ConfigError(f"{CONFIG_FILENAME} 顶层必须是映射")
        merged = _merge(DEFAULT_CONFIG, parsed, "config")
        return cls._from_mapping(layout, merged)

    @classmethod
    def from_mapping(cls, root: Path, overrides: dict[str, Any] | None = None) -> Config:
        """仅测试使用：以默认值为底，接受局部覆盖。"""
        layout = Layout(root.resolve())
        merged = _merge(DEFAULT_CONFIG, overrides or {}, "config")
        return cls._from_mapping(layout, merged)

    @classmethod
    def _from_mapping(cls, layout: Layout, raw: dict[str, Any]) -> Config:
        llm_raw = _section(raw, "llm")
        depth_raw = _section(raw, "depth")
        budget_raw = _section(depth_raw, "budget")
        pool_raw = _section(raw, "pool")
        score_raw = _section(raw, "score")

        price_table: dict[str, PriceEntry] = {}
        for model, entry in _section(llm_raw, "price_table").items():
            if not isinstance(entry, dict):
                raise ConfigError(f"llm.price_table.{model} 必须是映射")
            price_table[model] = PriceEntry(
                prompt_per_1m=as_float(entry.get("prompt_per_1m"), 0.0),
                completion_per_1m=as_float(entry.get("completion_per_1m"), 0.0),
            )

        quota = {
            str(key): as_int(value, 0) for key, value in _section(depth_raw, "weekly_quota").items()
        }
        baseline = {
            str(key): as_str(value, "off") for key, value in _section(depth_raw, "baseline").items()
        }

        watch_raw = raw.get("watchlist", [])
        if not isinstance(watch_raw, list):
            raise ConfigError("watchlist 必须是数组（元素为 owner/repo）")
        watchlist = tuple(sorted(as_str(item, "") for item in watch_raw if as_str(item, "")))

        return cls(
            layout=layout,
            github_token_env=as_str(raw.get("github_token_env"), "GITHUB_TOKEN"),
            github_base_url=as_str(raw.get("github_base_url"), "https://api.github.com"),
            llm=LlmConfig(
                api_key_env=as_str(llm_raw.get("api_key_env"), "OSSLENS_LLM_API_KEY"),
                base_url_env=as_str(llm_raw.get("base_url_env"), "OSSLENS_LLM_BASE_URL"),
                model_env=as_str(llm_raw.get("model_env"), "OSSLENS_LLM_MODEL"),
                price_table=price_table,
            ),
            depth=DepthConfig(
                weekly_quota=quota,
                budget=BudgetConfig(
                    weekly_tokens=as_int(budget_raw.get("weekly_tokens"), 2_000_000),
                    monthly_tokens=as_int(budget_raw.get("monthly_tokens"), 6_000_000),
                    per_run_prompt_tokens=as_int(budget_raw.get("per_run_prompt_tokens"), 120_000),
                ),
                baseline=baseline,
            ),
            pool=PoolConfig(
                hot_min_star_delta_7d=as_int(pool_raw.get("hot_min_star_delta_7d"), 200),
                hot_observe_days=as_int(pool_raw.get("hot_observe_days"), 7),
                classic_min_stars=as_int(pool_raw.get("classic_min_stars"), 5000),
                classic_min_age_days=as_int(pool_raw.get("classic_min_age_days"), 730),
                dedupe=as_bool(pool_raw.get("dedupe"), True),
            ),
            score=ScoreConfig(
                hot={str(k): as_float(v, 0.0) for k, v in _section(score_raw, "hot").items()},
                classic={
                    str(k): as_float(v, 0.0) for k, v in _section(score_raw, "classic").items()
                },
            ),
            watchlist=watchlist,
        )

    # ------------------------------------------------------------------ 凭据

    def github_token(self) -> str | None:
        token = os.environ.get(self.github_token_env, "").strip()
        return token or None

    def llm_credentials(self) -> LlmCredentials | None:
        """三者缺任一 → None（红线 #3：不是报错，是降级）。"""
        api_key = os.environ.get(self.llm.api_key_env, "").strip()
        base_url = os.environ.get(self.llm.base_url_env, "").strip()
        model = os.environ.get(self.llm.model_env, "").strip()
        if not (api_key and base_url and model):
            return None
        return LlmCredentials(api_key=api_key, base_url=base_url, model=model)


def _section(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"配置项 {key} 必须是映射")
    return value


def _merge(base: dict[str, Any], override: dict[str, Any], path: str) -> dict[str, Any]:
    """深合并；未知键直接报错（防止拼写错误静默生效）。

    `llm.price_table` 的键由使用者自由填写（模型 ID），不参与白名单校验。
    """
    freeform = {"config.llm.price_table"}
    result = dict(base)
    for key, value in override.items():
        if key not in base:
            raise ConfigError(f"未知配置项 {path}.{key}（拼写错误？）")
        current = base[key]
        if isinstance(current, dict) and isinstance(value, dict):
            child_path = f"{path}.{key}"
            result[key] = value if child_path in freeform else _merge(current, value, child_path)
        else:
            result[key] = value
    return result
