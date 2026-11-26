# openvinotoolkit/openvino 深度分析

> 阅读档位：选型尽调（profile=adoption_due_diligence）
> 注意力预算：定位 15 / 架构 15 / 抽象 10 / ADR 10 / 扩展 5 / 经验卡 0 / 工程维护 45
> 证据约定：[事实] 确定性提取 · [判断] 有 file:line 或文档锚点 · [未获得] 当前未采集

## 导读

> **是什么**：OpenVINO™ is an open source toolkit for optimizing and deploying AI inference
> **架构一句话**：[判断] 顶层以 `src`、`docs`、`.github` 为主，入口为 `.github/actions/cache/dist/cleanup-only/index.js`（静态结构判断，未做动态跟踪）。
> **最大风险**：Top1 贡献者占比 5.55%，决策集中度需关注
> **不适合**：需要稳定 API/长期支持承诺的场景，请先核对发布节奏与维护状态；依赖链许可证与权重许可能力当前未采集，不能据此做出商用结论。

## 1. 项目定位与目标

[事实] openvinotoolkit/openvino 属于 `未指定` 领域、`classic` 通道，主语言 C++（88%），12,746 stars / 3,719 forks。

[事实] 项目自述：OpenVINO™ is an open source toolkit for optimizing and deploying AI inference。

[事实] README 摘要：Tool for automatic iteration over commit set with provided operation. For example, binary search with given cryterion (check application output, compare printed blobs, etc.) git >= *2.0* cmake >= OpenVino minimum required version (CMakeLists.txt) python >= *3.6* ccache >= *3.0* 1. Install **CCache**: `sudo apt install -y ccache` `sudo /usr/sbin/update-ccache-symlinks` `echo 'export PATH="/usr/lib/ccache:$PATH"' | tee -a ~/.bashrc`。

- **目标用户**：[判断] 模型工程师 / 推理基础设施开发者；终端用户与性能调优人员
- **替代方案与差异**：[未获得] 本次未采集竞品对比与 roadmap，不得据此推断「没有替代品」。
- **不解决什么**：[未获得] 没有路线图与 issue 语料，无法可靠界定能力边界。

[判断] 阶段信号：仓库已存在 2,964 天，近一年发布 11 个版本，最近提交距今 0 天，维护状态「active」。这只说明是否仍在维护，不等于成熟度结论。

## 2. 架构全景

### 2.1 上下文边界

[判断] 架构说明文档：`.github/scripts/meat/README.md`, `README.md`, `samples/c/hello_classification/README.md`, `samples/cpp/hello_remote_tensor/README.md`, `src/bindings/js/node/README.md`；边界结论来自文档与目录结构，未经运行验证。
[事实] 硬件/内核线索：vendors=[]、kernel_langs=[]。

### 2.2 模块职责

| 模块 | 文件数 | 职责（启发式） |
|---|---:|---|
| `src` | 16,301 | 核心实现 |
| `docs` | 1,018 | 文档 |
| `.github` | 384 | 业务实现（职责需人工确认） |
| `samples` | 151 | 业务实现（职责需人工确认） |
| `tests` | 1,068 | 测试与用例 |

### 2.3 一次调用的路径（运行时视图）

[判断] 静态推断：`.github/actions/cache/dist/cleanup-only/index.js`, `.github/actions/cache/dist/restore-only/index.js`, `.github/actions/cache/dist/restore/index.js`, `.github/actions/cache/dist/save-only/index.js`, `.github/actions/cache/dist/save/index.js`, `.github/actions/install_wheel/dist/index.js`, `.github/actions/wait-for-check-completion/dist/index.js`, `.github/actions/wait-for-check-completion/src/index.js`, `docs/articles_en/assets/snippets/main.py`, `docs/snippets/src/main.cpp`, `docs/snippets/src/main.py`, `samples/cpp/benchmark/sync_benchmark/main.cpp`, `samples/cpp/benchmark/throughput_benchmark/main.cpp`, `samples/cpp/benchmark_app/main.cpp`, `samples/cpp/classification_sample_async/main.cpp`, `samples/cpp/hello_classification/main.cpp`, `samples/cpp/hello_nv12_input_classification/main.cpp`, `samples/cpp/hello_query_device/main.cpp`, `samples/cpp/hello_remote_tensor/main.cpp`, `samples/cpp/hello_reshape_ssd/main.cpp`, `samples/cpp/model_creation_sample/main.cpp`, `src/bindings/js/node/lib/index.ts`, `src/bindings/js/node/tests/e2e/demo-electron-app/index.js`, `src/core/tests/main.cpp`, `src/frontends/tests/frontend/shared/gtest_main_manifest/main.cpp`, `src/frontends/tests/frontend/shared/src/main.cpp`, `src/plugins/intel_cpu/tools/dump_jit_disassm/__main__.py`, `src/plugins/intel_npu/tests/functional/main.cpp`, `src/plugins/intel_npu/tests/unit/main.cpp`, `src/plugins/intel_npu/tools/compile_tool/main.cpp`, `src/plugins/intel_npu/tools/protopipe/main.cpp`, `src/plugins/intel_npu/tools/single-image-test/main.cpp`, `src/tests/functional/plugin/conformance/subgraphs_dumper/src/main.cpp`, `src/tests/functional/plugin/conformance/test_runner/conformance_infra/src/main.cpp`, `src/tests/functional/plugin/shared/src/main.cpp`, `tests/stress_tests/memleaks_tests/main.cpp`, `tests/stress_tests/unittests/main.cpp`, `tests/time_tests/src/timetests_helper/main.cpp`, `tools/benchmark_tool/openvino/tools/benchmark/main.py`, `tools/ovc/openvino/tools/ovc/__main__.py`, `tools/ovc/openvino/tools/ovc/main.py` → 输出。内部 import 边约 0 条，只用于判断调用方向；**未做运行时跟踪**，参数与分支需读源码确认。

### 2.4 数据与控制流

[未获得] 未检测到并行/缓存轴证据；不代表项目中不存在。

```mermaid
graph TD
  A[无可提取的内部模块依赖边]
```

## 3. 核心抽象与契约

[未获得] 本次源码切片未识别到显式接口/注册模式；这不等于项目没有抽象层，只说明当前采集粒度不足。

入口候选（可作为契约阅读起点）：`.github/actions/cache/dist/cleanup-only/index.js`、`.github/actions/cache/dist/restore-only/index.js`、`.github/actions/cache/dist/restore/index.js`、`.github/actions/cache/dist/save-only/index.js`、`.github/actions/cache/dist/save/index.js`、`.github/actions/install_wheel/dist/index.js`、`.github/actions/wait-for-check-completion/dist/index.js`、`.github/actions/wait-for-check-completion/src/index.js`、`docs/articles_en/assets/snippets/main.py`、`docs/snippets/src/main.cpp`、`docs/snippets/src/main.py`、`samples/cpp/benchmark/sync_benchmark/main.cpp`、`samples/cpp/benchmark/throughput_benchmark/main.cpp`、`samples/cpp/benchmark_app/main.cpp`、`samples/cpp/classification_sample_async/main.cpp`、`samples/cpp/hello_classification/main.cpp`、`samples/cpp/hello_nv12_input_classification/main.cpp`、`samples/cpp/hello_query_device/main.cpp`、`samples/cpp/hello_remote_tensor/main.cpp`、`samples/cpp/hello_reshape_ssd/main.cpp`、`samples/cpp/model_creation_sample/main.cpp`、`src/bindings/js/node/lib/index.ts`、`src/bindings/js/node/tests/e2e/demo-electron-app/index.js`、`src/core/tests/main.cpp`、`src/frontends/tests/frontend/shared/gtest_main_manifest/main.cpp`、`src/frontends/tests/frontend/shared/src/main.cpp`、`src/plugins/intel_cpu/tools/dump_jit_disassm/__main__.py`、`src/plugins/intel_npu/tests/functional/main.cpp`、`src/plugins/intel_npu/tests/unit/main.cpp`、`src/plugins/intel_npu/tools/compile_tool/main.cpp`、`src/plugins/intel_npu/tools/protopipe/main.cpp`、`src/plugins/intel_npu/tools/single-image-test/main.cpp`、`src/tests/functional/plugin/conformance/subgraphs_dumper/src/main.cpp`、`src/tests/functional/plugin/conformance/test_runner/conformance_infra/src/main.cpp`、`src/tests/functional/plugin/shared/src/main.cpp`、`tests/stress_tests/memleaks_tests/main.cpp`、`tests/stress_tests/unittests/main.cpp`、`tests/time_tests/src/timetests_helper/main.cpp`、`tools/benchmark_tool/openvino/tools/benchmark/main.py`、`tools/ovc/openvino/tools/ovc/__main__.py`、`tools/ovc/openvino/tools/ovc/main.py`

## 4. 关键设计决策（ADR）

每条固定六字段：决策 / 替代 / 代价 / 证据 / 可复用规则 / 边界·反模式。

### ADR-1 · t1: 用二分遍历提交区间定位首个坏提交

- **决策**：用二分遍历提交区间定位首个坏提交
- **替代**：逐提交线性扫描
- **代价**：依赖单调性假设，非单调回归会漏判
- **证据**：`tools/commit_slider/README.md:5`
- **可复用规则**：回归定位用二分而非线性扫描，前提是失败状态单调
- **边界/反模式**：回归非单调或存在互相掩盖的 bug 时不适用

### ADR-2 · t2: 从 benchmark_report.csv 读指标而非解析控制台输出

- **决策**：从 benchmark_report.csv 读指标而非解析控制台输出
- **替代**：正则解析 benchmark_app 控制台延迟文本
- **代价**：需额外生成报告文件并管理临时目录
- **证据**：`tools/commit_slider/README.md:76`
- **可复用规则**：机器消费的指标走结构化报告，不解析人类可读输出
- **边界/反模式**：工具不提供报告输出时只能退回文本解析

### ADR-3 · t3: 预构建应用缓存映射跳过重建

- **决策**：预构建应用缓存映射跳过重建
- **替代**：每个提交都完整重新构建
- **代价**：缓存缺失提交被标记忽略，可能漏掉真实回归
- **证据**：`tools/commit_slider/README.md:139`
- **可复用规则**：长区间回溯用预构建产物缓存换取速度，需显式标注忽略项
- **边界/反模式**：缓存与源码不一致或提交改动构建配置时不可用

### ADR-4 · t4: 构建命令列表可配置并带 catchMsg 正则

- **决策**：构建命令列表可配置并带 catchMsg 正则
- **替代**：硬编码单一构建流程
- **代价**：配置复杂度上升，错误匹配依赖正则质量
- **证据**：`tools/commit_slider/README.md:170`
- **可复用规则**：外部命令编排用声明式列表加输出正则捕获失败
- **边界/反模式**：命令输出格式不稳定时正则会误判，需人工核对日志

## 5. 扩展与改造路径

[未获得] 未识别到显式插件/注册点。

[判断] 新增能力的静态路径（需按实际代码复核）：

1. 在入口处接入参数/配置（入口候选：`.github/actions/cache/dist/cleanup-only/index.js`, `.github/actions/cache/dist/restore-only/index.js`, `.github/actions/cache/dist/restore/index.js`, `.github/actions/cache/dist/save-only/index.js`, `.github/actions/cache/dist/save/index.js`, `.github/actions/install_wheel/dist/index.js`, `.github/actions/wait-for-check-completion/dist/index.js`, `.github/actions/wait-for-check-completion/src/index.js`, `docs/articles_en/assets/snippets/main.py`, `docs/snippets/src/main.cpp`, `docs/snippets/src/main.py`, `samples/cpp/benchmark/sync_benchmark/main.cpp`, `samples/cpp/benchmark/throughput_benchmark/main.cpp`, `samples/cpp/benchmark_app/main.cpp`, `samples/cpp/classification_sample_async/main.cpp`, `samples/cpp/hello_classification/main.cpp`, `samples/cpp/hello_nv12_input_classification/main.cpp`, `samples/cpp/hello_query_device/main.cpp`, `samples/cpp/hello_remote_tensor/main.cpp`, `samples/cpp/hello_reshape_ssd/main.cpp`, `samples/cpp/model_creation_sample/main.cpp`, `src/bindings/js/node/lib/index.ts`, `src/bindings/js/node/tests/e2e/demo-electron-app/index.js`, `src/core/tests/main.cpp`, `src/frontends/tests/frontend/shared/gtest_main_manifest/main.cpp`, `src/frontends/tests/frontend/shared/src/main.cpp`, `src/plugins/intel_cpu/tools/dump_jit_disassm/__main__.py`, `src/plugins/intel_npu/tests/functional/main.cpp`, `src/plugins/intel_npu/tests/unit/main.cpp`, `src/plugins/intel_npu/tools/compile_tool/main.cpp`, `src/plugins/intel_npu/tools/protopipe/main.cpp`, `src/plugins/intel_npu/tools/single-image-test/main.cpp`, `src/tests/functional/plugin/conformance/subgraphs_dumper/src/main.cpp`, `src/tests/functional/plugin/conformance/test_runner/conformance_infra/src/main.cpp`, `src/tests/functional/plugin/shared/src/main.cpp`, `tests/stress_tests/memleaks_tests/main.cpp`, `tests/stress_tests/unittests/main.cpp`, `tests/time_tests/src/timetests_helper/main.cpp`, `tools/benchmark_tool/openvino/tools/benchmark/main.py`, `tools/ovc/openvino/tools/ovc/__main__.py`, `tools/ovc/openvino/tools/ovc/main.py`, `src`）；
2. 复用上表中的注册/分派结构，实现新的后端或适配器；
3. 补对应测试与文档，再走发布流程。

- 扩展文档：[未获得]
- 改造成本：[未获得] 需要先确认契约稳定性与测试覆盖，本报告不估算人日。

## 6. 经验卡

### 经验 1 · 回归定位用二分而非线性扫描，前提是失败状态单调

- **证据**：`tools/commit_slider/README.md:5`（来自 openvinotoolkit/openvino）
- **适用边界**：回归非单调或存在互相掩盖的 bug 时不适用
- **反模式**：在边界之外照搬「用二分遍历提交区间定位首个坏提交」，代价会变成「依赖单调性假设，非单调回归会漏判」
- **如果我来做**：先确认边界成立，再选择「用二分遍历提交区间定位首个坏提交」而非「逐提交线性扫描」

### 经验 2 · 机器消费的指标走结构化报告，不解析人类可读输出

- **证据**：`tools/commit_slider/README.md:76`（来自 openvinotoolkit/openvino）
- **适用边界**：工具不提供报告输出时只能退回文本解析
- **反模式**：在边界之外照搬「从 benchmark_report.csv 读指标而非解析控制台输出」，代价会变成「需额外生成报告文件并管理临时目录」
- **如果我来做**：先确认边界成立，再选择「从 benchmark_report.csv 读指标而非解析控制台输出」而非「正则解析 benchmark_app 控制台延迟文本」

### 经验 3 · 长区间回溯用预构建产物缓存换取速度，需显式标注忽略项

- **证据**：`tools/commit_slider/README.md:139`（来自 openvinotoolkit/openvino）
- **适用边界**：缓存与源码不一致或提交改动构建配置时不可用
- **反模式**：在边界之外照搬「预构建应用缓存映射跳过重建」，代价会变成「缓存缺失提交被标记忽略，可能漏掉真实回归」
- **如果我来做**：先确认边界成立，再选择「预构建应用缓存映射跳过重建」而非「每个提交都完整重新构建」

### 经验 4 · 外部命令编排用声明式列表加输出正则捕获失败

- **证据**：`tools/commit_slider/README.md:170`（来自 openvinotoolkit/openvino）
- **适用边界**：命令输出格式不稳定时正则会误判，需人工核对日志
- **反模式**：在边界之外照搬「构建命令列表可配置并带 catchMsg 正则」，代价会变成「配置复杂度上升，错误匹配依赖正则质量」
- **如果我来做**：先确认边界成立，再选择「构建命令列表可配置并带 catchMsg 正则」而非「硬编码单一构建流程」

## 附录 A 证据索引与未知项

### A1. 代码证据索引

| id | 决策 | 证据 |
|---|---|---|
| t1 | 用二分遍历提交区间定位首个坏提交 | `tools/commit_slider/README.md:5` |
| t2 | 从 benchmark_report.csv 读指标而非解析控制台输出 | `tools/commit_slider/README.md:76` |
| t3 | 预构建应用缓存映射跳过重建 | `tools/commit_slider/README.md:139` |
| t4 | 构建命令列表可配置并带 catchMsg 正则 | `tools/commit_slider/README.md:170` |

- 置信度：med
- 架构范式标签：模块化、通用优先

### A2. 外部资料

- 来源：deepwiki
- url：https://deepwiki.com/openvinotoolkit/openvino
- fetched_at：2026-11-26T20:04:15Z
- sha256：`d84acf112d4f88936e54e0be8bf128ddde971b6234c38adebe897b607048f441`
- 判定：hit — 正文含 9 个仓库内真实路径（阈值 3）
- 原文快照：`source.txt`（与判定元数据分文件存放）

### A3. 未获得项

- 依赖链许可证、模型权重/数据许可、CLA —— 未采集；
- issue/PR 响应质量、CI 运行结果 —— 未采集；
- roadmap、竞品对比、用户画像 —— 未采集；
**未获得的指标**：

- `used_by`：GitHub 无公开 API；L0 标注为未获得，不估算


## 附录 B 许可证 / 维护 / 工程 / 成本

### B1. 许可证与合规风险

[事实] 主许可证 **Apache-2.0**；组织类型 —；治理文档：有。

[未获得] 依赖链是否存在 GPL/AGPL、模型权重与数据集许可、CLA 要求；这些必须人工或由后续数据源补齐，本报告不给出「可商用」结论。

### B2. 维护状态与风险

[事实] 贡献者 413 人，Top1 占比 5.55%；近 90 天 / 365 天提交 1,127 / 2,000 次；最近提交距今 0 天，维护状态「active」。

- Top1 贡献者占比 5.55%，决策集中度需关注

### B3. 运行与工程体系

[事实] 仓库约 19,317 个文件、250.3 MiB；本次采集 20 个源码切片（tarball `6ed398a4c4693e09`）。
[事实] 语言构成：Batchfile 0.00%、C 3.36%、C# 0.00%、C++ 87.89%、CMake 1.45%、CSS 0.01%、HTML 0.03%、JavaScript 0.11%、PowerShell 0.01%、PureBasic 0.00%、Python 7.09%、Shell 0.03%、TypeScript 0.02%；硬件 vendors=[]、kernel_langs=[]。

[未获得] 构建脚本、依赖安装、测试体系、CI/CD、配置与 secret 管理未采集；本报告不能回答「能否在目标环境跑起来」。

**特征卡已知限制**：

- 证据来自 20 个源码切片的逐行扫描，未覆盖文件不计入
- issue_close_ratio_90d 需 search API，L0/L1 未调用
- cncf_or_foundation 与 Organization 的 org_type 细分需人工判定，置 null

### B4. 运行元数据与成本

| 项 | 值 |
|---|---|
| 仓库 | openvinotoolkit/openvino |
| commit | `2e7a29705be71c0a15f01b5c1d34b5fe72955fbb` |
| 分析基准时间 (as-of) | 2026-11-26T12:42:03Z |
| 通道 / 领域 | classic / 未指定 |
| 请求档位 (requested_depth) | fast |
| **实际档位** (actual_depth) | fast |
| 降级原因 (reason) | baseline — 按通道基线 |
| 配额状态 (quota_state) | strong 0/1、fast 3/5（周起点 2026-11-23）；tokens 周 33883/2000000、月 378121/6000000（月起点 2026-11-01） |
| 快照 sha256 | `655f1514418e4db43520d58596c52358b06ff9261422a421271059bed29ecb12` |
| 成本说明 | 本次 ¥0.0227（模型调用 1 次）；输入 10,087 tok / 命中 256 tok / 输出 376 tok |
| 累计 | 本周 ¥0.1006 / 44,346 tok；本月 ¥1.1309 / 388,584 tok |
| 单价 | deepseek-flash 输入未命中 ¥2/M · 缓存命中 ¥0.04/M · 输出 ¥8/M（官方中文页，核对 2026-11-03，取高峰价；低谷约为一半） |
| 口径 | 本次分析的成本（不含开发期重复调用）；账户累计见 cost；成本说明同 as-of 重跑不变（幂等优先）；两者不一致是设计，不是 bug |

**档位决策链路**：

1. L1 通道基线：classic → strong；自动链按 auto_default=fast 取更省档位 → fast（非 L4 人工 override）
2. 凭据：齐全
3. L2 周配额：fast 已用 3/5，未用满
4. L3 预算：估算 4651 × 安全系数 1.3 = 6046 tok（单选上限 120000），周 33883/2000000
5. 结论：实际档位 fast（按通道基线）

**上下文组装**（裁剪发生在调用之前）：

| 块 | 优先级 | 估算 token |
|---|---|---|
| featcard | 1 | 2,273 |
| readme | 2 | 2,378 |

- 丢弃：—
- 合计 4,651 / 上限 120,000

### B5. 特征卡摘要

- 卡文件：`data/featcards/openvinotoolkit__openvino__2e7a29705be71c0a15f01b5c1d34b5fe72955fbb.json`（schema 1.0）
- 入口文件：.github/actions/cache/dist/cleanup-only/index.js, .github/actions/cache/dist/restore-only/index.js, .github/actions/cache/dist/restore/index.js, .github/actions/cache/dist/save-only/index.js, .github/actions/cache/dist/save/index.js, .github/actions/install_wheel/dist/index.js, .github/actions/wait-for-check-completion/dist/index.js, .github/actions/wait-for-check-completion/src/index.js, docs/articles_en/assets/snippets/main.py, docs/snippets/src/main.cpp, docs/snippets/src/main.py, samples/cpp/benchmark/sync_benchmark/main.cpp, samples/cpp/benchmark/throughput_benchmark/main.cpp, samples/cpp/benchmark_app/main.cpp, samples/cpp/classification_sample_async/main.cpp, samples/cpp/hello_classification/main.cpp, samples/cpp/hello_nv12_input_classification/main.cpp, samples/cpp/hello_query_device/main.cpp, samples/cpp/hello_remote_tensor/main.cpp, samples/cpp/hello_reshape_ssd/main.cpp, samples/cpp/model_creation_sample/main.cpp, src/bindings/js/node/lib/index.ts, src/bindings/js/node/tests/e2e/demo-electron-app/index.js, src/core/tests/main.cpp, src/frontends/tests/frontend/shared/gtest_main_manifest/main.cpp, src/frontends/tests/frontend/shared/src/main.cpp, src/plugins/intel_cpu/tools/dump_jit_disassm/__main__.py, src/plugins/intel_npu/tests/functional/main.cpp, src/plugins/intel_npu/tests/unit/main.cpp, src/plugins/intel_npu/tools/compile_tool/main.cpp, src/plugins/intel_npu/tools/protopipe/main.cpp, src/plugins/intel_npu/tools/single-image-test/main.cpp, src/tests/functional/plugin/conformance/subgraphs_dumper/src/main.cpp, src/tests/functional/plugin/conformance/test_runner/conformance_infra/src/main.cpp, src/tests/functional/plugin/shared/src/main.cpp, tests/stress_tests/memleaks_tests/main.cpp, tests/stress_tests/unittests/main.cpp, tests/time_tests/src/timetests_helper/main.cpp, tools/benchmark_tool/openvino/tools/benchmark/main.py, tools/ovc/openvino/tools/ovc/__main__.py, tools/ovc/openvino/tools/ovc/main.py
- 最大目录深度：11；monorepo：是
- 源码切片：20 个文件（tarball `6ed398a4c4693e09`）
- 依赖：直接 / 传递 = — / —（L1 未解析清单文件）

**并行轴**

- 并行 `CP` = false（无证据）
- 并行 `DP` = false（无证据）
- 并行 `EP` = false（无证据）
- 并行 `PP` = false（无证据）
- 并行 `SP` = false（无证据）
- 并行 `TP` = false（无证据）

**缓存**

- 缓存 `kv_offload` = false（无证据）
- 缓存 `paged` = false（无证据）
- 缓存 `prefix_reuse` = false（无证据）
- 缓存 `radix` = false（无证据）

- 硬件：vendors=[]、arch_gates=[]、kernel_langs=[]
- 治理文档：是

**依赖图**（内部模块 import 边，节点/边排序后输出）

```mermaid
graph TD
  A[无可提取的内部模块依赖边]
```

**已知限制**：

- 证据来自 20 个源码切片的逐行扫描，未覆盖文件不计入
- issue_close_ratio_90d 需 search API，L0/L1 未调用
- cncf_or_foundation 与 Organization 的 org_type 细分需人工判定，置 null

### B6. 体检事实（确定性，零 LLM）

| 指标 | 值 |
|---|---|
| Star / Fork | 12,746 / 3,719 |
| 被依赖 (Used by) | — |
| 贡献者 / Top1 占比 | 413 / 5.55% |
| Top10 贡献集中度 | 26.27% |
| 90 天 / 365 天提交 | 1,127 / 2,000 |
| 最近提交 / 距今天数 | 2026-11-26T08:59:07Z / 0 |
| 维护状态 | active |
| 项目年龄 / 发布数(365d) | 2,964 天 / 11 |
| 组织类型 / 许可证 | — / Apache-2.0 |
| 文件数 / 体积 | 19,317 / 250.3 MiB |
| 内部模块依赖边 | 0 |

**语言构成**：Batchfile 0.00%、C 3.36%、C# 0.00%、C++ 87.89%、CMake 1.45%、CSS 0.01%、HTML 0.03%、JavaScript 0.11%、PowerShell 0.01%、PureBasic 0.00%、Python 7.09%、Shell 0.03%、TypeScript 0.02%

**模块体量 Top10**

| 模块 | 文件数 | 字节 |
|---|---|---|
| src | 16,301 | 182,341,266 |
| docs | 1,018 | 52,273,456 |
| .github | 384 | 13,064,122 |
| samples | 151 | 6,236,991 |
| tests | 1,068 | 4,856,454 |
| tools | 164 | 2,050,947 |
| cmake | 120 | 556,991 |
| thirdparty | 40 | 356,526 |
| licensing | 6 | 352,587 |
| .claude | 37 | 228,239 |

**未获得的指标**：

- `used_by`：GitHub 无公开 API；L0 标注为未获得，不估算
