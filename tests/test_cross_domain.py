"""Q5 跨域抽象（实现轮 v1.0 T2）契约测试。

★ 覆盖卡 T2.5 五个必测点：阈值触发 / 未达阈值 / off 零调用 / 幂等重放 /
  无真实 L2 条目时 insufficient_samples 合法终态。
★ 另测：两个阈值均被消费、九字段落盘、type=TYPE_CROSS_DOMAIN、budget_gate 生效、
  CachedModelCaller 不重复、CLI `--cross` 与簇内 run 不混排、真源纯净（不伪造条目）。
★ 本文件样本一律为 tests/ 内的**结构化夹具**（tmp_path 工作区），绝不写进 patterns/*.yaml 真源。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from osslens import patterns as p
from osslens.abstract import (
    STATUS_COMPLETED,
    STATUS_INSUFFICIENT,
    STATUS_NO_CREDENTIALS,
    TYPE_CLUSTER,
    TYPE_CROSS_DOMAIN,
    CachedModelCaller,
    ModelResult,
    RunRecord,
    append_run,
    cross_domain_run,
    load_runs,
)
from osslens.cli import main
from osslens.config import Config, Layout
from osslens.depth import EVENT_CALL, EVENT_DOWNGRADE, load_events
from osslens.util import fmt_iso

from .conftest import write_config

LATER = datetime(2026, 11, 6, 0, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- 夹具


def _workspace(tmp_path: Path, *, overrides: dict | None = None) -> Config:
    layout = Layout(tmp_path)
    layout.ensure_skeleton()
    write_config(tmp_path, overrides)
    return Config.load(tmp_path)


def _l2(entry_id: str) -> p.PatternEntry:
    """合法 L2 条目（带真实反例位，过 validate_entry）。"""
    return p.PatternEntry(
        id=entry_id,
        level="L2",
        cluster="inference",
        statement="前缀重叠高时采用缓存复用",
        tags=("cache.hits.paged",),
        counterexamples=(p.Evidence(repo="test-org/inference-1", kind="反例"),),
    )


def _seed_l2(config: Config, count: int) -> None:
    p.save_library(config.layout.library_patterns, tuple(_l2(f"P-{i}") for i in range(count)))


def _seed_cluster_runs(config: Config, count: int) -> None:
    """构造 `count` 条已完成的簇内 run 历史（验证 every_runs 阈值被消费）。"""
    for i in range(count):
        append_run(
            config.layout,
            RunRecord(
                run_id=f"cluster-{i}",
                type=TYPE_CLUSTER,
                cluster="inference",
                trigger="新增样本 6 (>= 6)",
                input_projects=(f"test-org/inference-{i}",),
                input_patterns=(),
                ops=(),
                llm_calls=1,
                created_at=fmt_iso(LATER),
                status=STATUS_COMPLETED,
                self_check=p.build_self_check((), ()),
            ),
        )


class _FakeCaller:
    """可控模型调用者：返回一条 strengthen op（作用到已存在的 L2 条目）。"""

    def __init__(self, target: str = "P-0") -> None:
        self.calls = 0
        self.target = target

    def __call__(self, *, system: str, user: str) -> ModelResult:
        self.calls += 1
        return ModelResult(
            ops=(
                p.Op(
                    op="strengthen",
                    id=self.target,
                    evidence=(p.Evidence(repo="test-org/inference-0", kind="正例"),),
                ),
            ),
            prompt_tokens=120,
            completion_tokens=60,
            cache_hit_tokens=0,
            calls=1,
            status="ok",
            reason="",
            model="deepseek-flash",
        )


# --------------------------------------------------------------------------- 阈值触发


def test_cross_domain_triggers_by_l2_entry_threshold(tmp_path: Path) -> None:
    """L2 条目 ≥ 8 → 触发跨域 run，模型调用生效、type=cross-domain、ops 应用、usage 记账。"""
    config = _workspace(tmp_path)
    _seed_l2(config, 8)  # cross_domain_min_l2_entries = 8
    fake = _FakeCaller()
    result = cross_domain_run(config, as_of=LATER, caller=fake)
    assert result.record.type == TYPE_CROSS_DOMAIN
    assert result.record.status == STATUS_COMPLETED
    assert result.record.llm_calls == 1 and fake.calls == 1
    assert result.record.cluster == "<cross-domain>"
    assert len(result.record.input_patterns) == 8  # 输入 = L2 结构化摘要（条目 id）
    assert result.record.input_projects == ()  # 不重喂全量项目
    # usage 记账：purpose 为 cross-domain
    calls = [e for e in load_events(config.layout) if e.event == EVENT_CALL]
    assert len(calls) == 1 and calls[0].purpose == TYPE_CROSS_DOMAIN
    # 九字段落盘
    stored = load_runs(config.layout)
    assert len(stored) == 1 and stored[0].run_id == result.record.run_id
    assert stored[0].type == TYPE_CROSS_DOMAIN
    # ops 确实修订了真源条目
    lib = p.load_library(config.layout.library_patterns)
    assert next(e for e in lib if e.id == "P-0").revision == 2


def test_cross_domain_triggers_by_cluster_runs_threshold(tmp_path: Path) -> None:
    """每 4 次簇内 run → 触发（即使 L2 条目 < 8）：第二个阈值也被真实消费。"""
    config = _workspace(tmp_path)
    _seed_l2(config, 2)  # 2 < 8
    _seed_cluster_runs(config, 4)  # 4 % 4 == 0 → every_runs 触发
    fake = _FakeCaller()
    result = cross_domain_run(config, as_of=LATER, caller=fake)
    assert result.record.status == STATUS_COMPLETED
    assert fake.calls == 1
    assert "簇内 run 4" in result.record.trigger


# --------------------------------------------------------------------------- 未达阈值 / 空态


def test_cross_domain_below_threshold_is_insufficient(tmp_path: Path) -> None:
    """L2 < 8 且簇内 run 未到 4 → insufficient_samples 合法终态，0 条 0 LLM。"""
    config = _workspace(tmp_path)
    _seed_l2(config, 2)
    fake = _FakeCaller()
    result = cross_domain_run(config, as_of=LATER, caller=fake)
    assert result.record.status == STATUS_INSUFFICIENT
    assert result.record.llm_calls == 0 and fake.calls == 0
    assert result.record.ops == () and result.record.produced_patterns == ()
    assert any("阈值未达" in w for w in result.record.warnings)


def test_cross_domain_no_real_l2_is_pure_insufficient(tmp_path: Path) -> None:
    """无真实 L2 条目（真源纯净）→ insufficient_samples，不伪造条目凑数（红线 8）。"""
    config = _workspace(tmp_path)  # library.yaml 仍为 []
    _seed_cluster_runs(config, 4)  # 即便 every_runs 触发，无 L2 输入仍应空态
    result = cross_domain_run(config, as_of=LATER, off=True)
    assert result.record.status == STATUS_INSUFFICIENT
    assert result.record.llm_calls == 0
    assert any("无真实 L2 条目" in w for w in result.record.warnings)
    assert p.load_library(config.layout.library_patterns) == ()  # 真源未被写入合成条目


# --------------------------------------------------------------------------- off / budget / 幂等 / 缓存


def test_cross_domain_off_zero_llm(tmp_path: Path) -> None:
    """阈值达标但 off 档 → 零 LLM、no_credentials 合法终态；降级事件 purpose=cross-domain。"""
    config = _workspace(tmp_path)
    _seed_l2(config, 8)
    fake = _FakeCaller()
    result = cross_domain_run(config, as_of=LATER, caller=fake, off=True)
    assert result.record.status == STATUS_NO_CREDENTIALS
    assert result.record.llm_calls == 0 and fake.calls == 0
    downgrades = [e for e in load_events(config.layout) if e.event == EVENT_DOWNGRADE]
    assert len(downgrades) == 1 and downgrades[0].purpose == TYPE_CROSS_DOMAIN


def test_cross_domain_budget_gate_applies(tmp_path: Path) -> None:
    """budget_gate（estimate_safety_factor）在跨域路径同样生效：闸门拦截 → budget_blocked。"""
    config = _workspace(tmp_path, overrides={"depth": {"budget": {"per_run_prompt_tokens": 1}}})
    _seed_l2(config, 8)
    fake = _FakeCaller()
    result = cross_domain_run(config, as_of=LATER, caller=fake)
    assert result.record.status == "budget_blocked"
    assert fake.calls == 0 and result.record.llm_calls == 0


def test_cross_domain_idempotent_replay(tmp_path: Path) -> None:
    """同 as_of + 同输入 → 同一 run_id；第二次重放，不重复调用模型、不重复写记录。"""
    config = _workspace(tmp_path)
    _seed_l2(config, 8)
    fake = _FakeCaller()
    first = cross_domain_run(config, as_of=LATER, caller=fake)
    second = cross_domain_run(config, as_of=LATER, caller=fake)
    assert first.record.run_id == second.record.run_id
    assert first.appended is True and second.appended is False
    assert fake.calls == 1  # 重放未重复调用
    assert len(load_runs(config.layout)) == 1


def test_cross_domain_cached_caller_no_duplicate(tmp_path: Path) -> None:
    """CachedModelCaller：同输入命中缓存，不重复调用底层模型。

    用 write=False 固定真源不被 ops 改写（否则 confidence 变化会改变 l2_summary → cache key 变化），
    从而隔离出纯粹的「同输入缓存」语义；不同 as_of 保证两次都是真实调用路径而非 run 重放。
    """
    config = _workspace(tmp_path)
    _seed_l2(config, 8)
    inner = _FakeCaller()
    cached = CachedModelCaller(inner, config.layout)
    r1 = cross_domain_run(config, as_of=LATER, caller=cached, write=False)
    later = datetime(2026, 11, 7, 0, 0, tzinfo=UTC)
    r2 = cross_domain_run(config, as_of=later, caller=cached, write=False)
    assert r1.record.run_id != r2.record.run_id  # 不同 as_of → 不同 run（非重放）
    assert inner.calls == 1  # 第二次命中结果缓存，未再调用模型
    assert r2.record.status == STATUS_COMPLETED
    assert cached.hits == 1


# --------------------------------------------------------------------------- CLI


def test_cli_cross_writes_cross_domain_run_and_not_mixed(tmp_path: Path) -> None:
    """`abstract --cross` 写 cross-domain 记录；默认 abstract 写簇内记录，两者 type 不混排。"""
    _workspace(tmp_path)
    code1 = main(["abstract", "--root", str(tmp_path), "--as-of", fmt_iso(LATER), "--off"])
    code2 = main(
        ["abstract", "--root", str(tmp_path), "--as-of", fmt_iso(LATER), "--off", "--cross"]
    )
    assert code1 == 0 and code2 == 0
    runs = load_runs(Layout(tmp_path))
    types = {r.type for r in runs}
    assert TYPE_CROSS_DOMAIN in types, "--cross 必须落 cross-domain 记录"
    assert TYPE_CLUSTER in types, "默认 abstract 仍是簇内记录（不混排）"
    cross = next(r for r in runs if r.type == TYPE_CROSS_DOMAIN)
    assert cross.status == STATUS_INSUFFICIENT  # 真源空 → 合法空态
