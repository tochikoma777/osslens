# Changelog

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；版本号遵守语义化版本。

## [0.1.0] - 2026-11-02 · tag `l0`

L0：采集 + 建池 + 去重 + **off 档体检报告**。全链路零 LLM。

### 新增

- `python -m osslens init`：工作区骨架、`config.yaml`、`patterns/seed.yaml`（已存在则跳过，不覆盖）
- `python -m osslens pool add`：真实 GitHub 快照（stars/forks/commits/contributors/languages/tree）→ 追加观测
- `python -m osslens pool list`：hot / classic **分通道** z-score 打分排序
- `python -m osslens pool eligible`：观察期（热点 ≥7 天）与通道阈值判定，输出排除原因
- `python -m osslens analyze`：off 档体检报告（运行元数据 / 体检事实 / 特征卡摘要 / 洞见 `—` / 外部资料）
- `python -m osslens cost`：本周 / 本月 token、费用、按档位分布、降级与拦截次数、预算剩余
- 档位四层解析：L1 通道基线 → 凭据 / 实现能力 → L2 周配额 → L3 预算闸门 → L4 override
- 降级**双写**留痕：报告「运行元数据」块 + `data/costs/costs.jsonl`
- 特征卡 L0（确定性、零 LLM），`parallel/cache/hardware` 无证据一律 `false`

### 工程

- `pyproject.toml`（setuptools + httpx + PyYAML），`[dev]` 含 pytest / ruff / mypy / respx
- 门禁：`pytest` · `ruff check` · `ruff format --check` · `mypy --strict`
- 37 个测试，语句覆盖率 83%（`pool.py` 95%、`config.py` 88%、`collect.py` 87%）

### 已知限制

- `used_by` / `deps.*` / `loc_total` / `internal_edge_count` / `issue_close_ratio_90d` 为 `null`（L0 不读源码、无可公开 API）
- 热点通道的 7 日增量需 ≥2 次观测；首次入池必为 `0`（设计如此，不估算）
- 外部工具（DeepWiki / Zread）未接线，报告标注「不可用（未索引）」
- `abstract` / `site` / 模式召回 未实现（L3 / L4）
