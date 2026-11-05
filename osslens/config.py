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
        "models": {"fast": "deepseek-flash", "strong": "deepseek-v4-pro"},
        "thinking": {"fast": False, "strong": True},
        "timeout_seconds": 120.0,
        "max_retries": 2,
        # 按档位给输出上限；strong 开启 thinking，reasoning token 计入 completion_tokens，需更大余量
        "max_output_tokens": {"fast": 4096, "strong": 8192},
        # 高峰价单值（保守上界），单位 CNY / 1M tokens；来源见 docs/成本预算.md
        "price_table": {
            "deepseek-flash": {
                "cache_hit_per_1m": 0.04,
                "prompt_per_1m": 2.0,
                "completion_per_1m": 8.0,
            },
            "deepseek-v4-pro": {
                "cache_hit_per_1m": 0.30,
                "prompt_per_1m": 9.0,
                "completion_per_1m": 27.0,
            },
        },
    },
    "depth": {
        "weekly_quota": {"strong": 1, "fast": 3},
        "budget": {
            "weekly_tokens": 2_000_000,
            "monthly_tokens": 6_000_000,
            "per_run_prompt_tokens": 120_000,
            "max_calls_per_run": 12,
            # D12-2：估算低估 25.6%（17,354→21,803），闸门按 估算×系数 判断，默认 1.3
            "estimate_safety_factor": 1.3,
        },
        "baseline": {"hot": "fast", "classic": "strong", "watchlist": "strong"},
    },
    # T5：缓存层保留策略（按可再生性分层，设计方案 v1.3 §8.2 为唯一权威）
    "retention": {
        "enabled": True,
        "cache_keep_days": 30,
        "archive_dir": "data/cache_archive",
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
    "featcard": {"maintenance": {"active_days": 90, "slowed_days": 365}},
    "external": {
        "deepwiki_enabled": True,
        "deepwiki_transport": "mcp",
        "deepwiki_base_url": "https://deepwiki.com",
        "deepwiki_mcp_url": "https://mcp.deepwiki.com/mcp",
        "min_repo_paths": 3,
        "timeout_seconds": 40.0,
    },
    "sources": {"max_files": 20, "max_total_bytes": 524288, "max_file_bytes": 204800},
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
  # 分档模型名（D6-1：不再用单一 model_env）
  models:
    fast: deepseek-flash
    strong: deepseek-v4-pro
  # 按档位控制 thinking（D6-3）；fast 关闭以省输出费用
  thinking:
    fast: false
    strong: true
  timeout_seconds: 120
  max_retries: 2
  # 按档位给输出上限；strong 开启 thinking，reasoning token 计入 completion_tokens
  max_output_tokens:
    fast: 4096
    strong: 8192
  # ★ 单价只来自 config，代码不内置任何价格字面量（设计方案 §9）
  # 人民币 / 1M tokens，取「高峰价」单值 = 保守上界；低谷约为表中一半
  # 来源：DeepSeek 官方定价页，核对 2026-11-03（见 docs/成本预算.md）
  price_table:
    deepseek-flash:
      cache_hit_per_1m: 0.04
      prompt_per_1m: 2.0
      completion_per_1m: 8.0
    deepseek-v4-pro:
      cache_hit_per_1m: 0.30
      prompt_per_1m: 9.0
      completion_per_1m: 27.0

depth:
  # 周配额（设计方案 §11）
  weekly_quota:
    strong: 1
    fast: 3
  budget:
    weekly_tokens: 2000000
    monthly_tokens: 6000000
    per_run_prompt_tokens: 120000
    # 第 5 道闸：单次 run 调用次数上限（M7）
    max_calls_per_run: 12
    # D12-2：估算 × 安全系数 才与闸门比较（L1 实测低估 25.6%）
    estimate_safety_factor: 1.3
  # 通道基线（设计方案 §2 L1）
  baseline:
    hot: fast
    classic: strong
    watchlist: strong

# T5：缓存层保留策略（按可再生性分层，设计方案 v1.3 §8.2 为唯一权威）
# 只作用于 src/（源码切片）与 data/llm_cache/；external/ 与三个 jsonl 真源永不触碰
retention:
  enabled: true
  cache_keep_days: 30
  archive_dir: data/cache_archive

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

featcard:
  # D6-5：维护状态阈值外置（历史素材的 30/180 天口径不采用）
  maintenance:
    active_days: 90
    slowed_days: 365

external:
  deepwiki_enabled: true
  # mcp（官方，默认）| html（页面抓取，遇 Vercel 校验会 blocked）
  deepwiki_transport: mcp
  deepwiki_base_url: https://deepwiki.com
  deepwiki_mcp_url: https://mcp.deepwiki.com/mcp
  # fail-closed：正文必须含 ≥N 个仓库内真实路径才算命中（红线 #4）
  min_repo_paths: 3
  timeout_seconds: 40

sources:
  # 证据提取的源码采集上限（单个仓库）
  max_files: 20
  max_total_bytes: 524288
  max_file_bytes: 204800

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
    max_calls_per_run: int
    estimate_safety_factor: float = 1.3


@dataclass(frozen=True)
class RetentionConfig:
    """T5：缓存层保留策略。只描述缓存层，真源边界由代码白名单钉死。"""

    enabled: bool
    cache_keep_days: int
    archive_dir: str


@dataclass(frozen=True)
class DepthConfig:
    weekly_quota: dict[str, int]
    budget: BudgetConfig
    baseline: dict[str, str]


@dataclass(frozen=True)
class PriceEntry:
    """单价（CNY / 1M tokens）。三值齐全：缓存命中 / 输入未命中 / 输出。"""

    cache_hit_per_1m: float
    prompt_per_1m: float
    completion_per_1m: float


@dataclass(frozen=True)
class LlmConfig:
    api_key_env: str
    base_url_env: str
    models: dict[str, str]
    thinking: dict[str, bool]
    price_table: dict[str, PriceEntry]
    max_output_tokens: dict[str, int]
    timeout_seconds: float
    max_retries: int


@dataclass(frozen=True)
class MaintenanceConfig:
    active_days: int
    slowed_days: int


@dataclass(frozen=True)
class FeatcardConfig:
    maintenance: MaintenanceConfig


@dataclass(frozen=True)
class ExternalConfig:
    deepwiki_enabled: bool
    deepwiki_transport: str
    deepwiki_base_url: str
    deepwiki_mcp_url: str
    min_repo_paths: int
    timeout_seconds: float


@dataclass(frozen=True)
class SourcesConfig:
    max_files: int
    max_total_bytes: int
    max_file_bytes: int


@dataclass(frozen=True)
class ScoreConfig:
    hot: dict[str, float]
    classic: dict[str, float]


@dataclass(frozen=True)
class LlmCredentials:
    """凭据只含 key + base_url；模型按档位从 `llm.models` 取。"""

    api_key: str
    base_url: str

    def redacted(self) -> str:
        return f"{self.base_url} (key=***{len(self.api_key)})"


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
    featcard: FeatcardConfig
    external: ExternalConfig
    sources: SourcesConfig
    retention: RetentionConfig
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
        feat_raw = _section(raw, "featcard")
        maint_raw = _section(feat_raw, "maintenance")
        ext_raw = _section(raw, "external")
        src_raw = _section(raw, "sources")
        ret_raw = _section(raw, "retention")

        price_table: dict[str, PriceEntry] = {}
        for model, entry in _section(llm_raw, "price_table").items():
            if not isinstance(entry, dict):
                raise ConfigError(f"llm.price_table.{model} 必须是映射")
            price_table[model] = PriceEntry(
                cache_hit_per_1m=as_float(entry.get("cache_hit_per_1m"), 0.0),
                prompt_per_1m=as_float(entry.get("prompt_per_1m"), 0.0),
                completion_per_1m=as_float(entry.get("completion_per_1m"), 0.0),
            )

        models_raw = _section(llm_raw, "models")
        models = {str(k): as_str(v) for k, v in models_raw.items() if as_str(v)}
        if not models:
            raise ConfigError("llm.models 不能为空（需 fast / strong 至少各一项）")

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
                models=models,
                thinking={
                    str(key): as_bool(value, False)
                    for key, value in _section(llm_raw, "thinking").items()
                },
                price_table=price_table,
                max_output_tokens={
                    str(k): as_int(v, 4096)
                    for k, v in _section(llm_raw, "max_output_tokens").items()
                }
                or {"fast": 4096, "strong": 8192},
                timeout_seconds=as_float(llm_raw.get("timeout_seconds"), 120.0),
                max_retries=as_int(llm_raw.get("max_retries"), 2),
            ),
            depth=DepthConfig(
                weekly_quota=quota,
                budget=BudgetConfig(
                    weekly_tokens=as_int(budget_raw.get("weekly_tokens"), 2_000_000),
                    monthly_tokens=as_int(budget_raw.get("monthly_tokens"), 6_000_000),
                    per_run_prompt_tokens=as_int(budget_raw.get("per_run_prompt_tokens"), 120_000),
                    max_calls_per_run=as_int(budget_raw.get("max_calls_per_run"), 12),
                    estimate_safety_factor=as_float(budget_raw.get("estimate_safety_factor"), 1.3),
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
            featcard=FeatcardConfig(
                maintenance=MaintenanceConfig(
                    active_days=as_int(maint_raw.get("active_days"), 90),
                    slowed_days=as_int(maint_raw.get("slowed_days"), 365),
                )
            ),
            external=ExternalConfig(
                deepwiki_enabled=as_bool(ext_raw.get("deepwiki_enabled"), True),
                deepwiki_transport=as_str(ext_raw.get("deepwiki_transport"), "mcp"),
                deepwiki_mcp_url=as_str(
                    ext_raw.get("deepwiki_mcp_url"), "https://mcp.deepwiki.com/mcp"
                ),
                deepwiki_base_url=as_str(ext_raw.get("deepwiki_base_url"), "https://deepwiki.com"),
                min_repo_paths=as_int(ext_raw.get("min_repo_paths"), 3),
                timeout_seconds=as_float(ext_raw.get("timeout_seconds"), 40.0),
            ),
            sources=SourcesConfig(
                max_files=as_int(src_raw.get("max_files"), 20),
                max_total_bytes=as_int(src_raw.get("max_total_bytes"), 524_288),
                max_file_bytes=as_int(src_raw.get("max_file_bytes"), 204_800),
            ),
            retention=RetentionConfig(
                enabled=as_bool(ret_raw.get("enabled"), True),
                cache_keep_days=as_int(ret_raw.get("cache_keep_days"), 30),
                archive_dir=as_str(ret_raw.get("archive_dir"), "data/cache_archive"),
            ),
            watchlist=watchlist,
        )

    # ------------------------------------------------------------------ 凭据

    def github_token(self) -> str | None:
        token = os.environ.get(self.github_token_env, "").strip()
        return token or None

    def llm_credentials(self) -> LlmCredentials | None:
        """key 与 base_url 缺任一 → None（红线 #3：不是报错，是降级）。"""
        api_key = os.environ.get(self.llm.api_key_env, "").strip()
        base_url = os.environ.get(self.llm.base_url_env, "").strip()
        if not (api_key and base_url):
            return None
        return LlmCredentials(api_key=api_key, base_url=base_url)

    def model_for(self, depth: str) -> str:
        return self.llm.models.get(depth) or self.llm.models.get("fast") or ""

    def max_output_for(self, depth: str) -> int:
        return self.llm.max_output_tokens.get(depth) or self.llm.max_output_tokens.get("fast", 4096)

    def safety_adjusted(self, estimated_prompt_tokens: int) -> int:
        """D12-2：闸门按 估算×安全系数 判断，防止估算低估导致漏拦。"""
        factor = self.depth.budget.estimate_safety_factor
        if factor <= 1.0:
            return estimated_prompt_tokens
        return int(estimated_prompt_tokens * factor)


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
    # 旧版单一 model_env：读到时忽略（D6-1 迁移），不报未知键
    legacy = {"config.llm.model_env"}
    result = dict(base)
    for key, value in override.items():
        if key not in base:
            if f"{path}.{key}" in legacy:
                continue
            raise ConfigError(f"未知配置项 {path}.{key}（拼写错误？）")
        current = base[key]
        if isinstance(current, dict) and isinstance(value, dict):
            child_path = f"{path}.{key}"
            result[key] = value if child_path in freeform else _merge(current, value, child_path)
        else:
            result[key] = value
    return result
