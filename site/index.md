# osslens 静态站点索引

- 基准时间 (as-of)：2026-11-13T16:16:57Z
- 产物：纯静态 HTML/MD；无后端、无外部 JS/CDN、零 LLM、零网络
- 真源：`reports/*.md` · `data/featcards/` · `patterns/library.yaml` · `data/costs/costs.jsonl` · `data/abstract/runs.jsonl`（站点只读）

## 页面

- [首页](index.html)
- [报告](reports.html)
- [特征卡](featcards.html)
- [规律库](patterns.html)
- [成本](costs.html)
- [抽象 run](runs.html)
- [检索](search.html)
- [范式标签](tags.html)
- [并排对比](compare.html)
- [本索引（纯 MD，可脱离站点阅读）](index.md)

## 项目清单（按仓库 / 基准时间 / 档位确定性排序）

| 仓库 | 基准时间 (as-of) | 实际档位 | 报告 |
|---|---|---|---|
| Dao-AILab/flash-attention | 2026-11-13T16:16:57Z | fast | [报告页](report-Dao-AILab__flash-attention__2026-11-13.html) · [源 MD](../reports/Dao-AILab__flash-attention__2026-11-13.md) |
| InternLM/lmdeploy | 2026-11-06T00:00:00Z | off | [报告页](report-InternLM__lmdeploy__2026-11-06.html) · [源 MD](../reports/InternLM__lmdeploy__2026-11-06.md) |
| InternLM/lmdeploy | 2026-11-09T00:00:00Z | off | [报告页](report-InternLM__lmdeploy__2026-11-09.html) · [源 MD](../reports/InternLM__lmdeploy__2026-11-09.md) |
| ModelTC/lightllm | 2026-11-06T00:00:00Z | off | [报告页](report-ModelTC__lightllm__2026-11-06.html) · [源 MD](../reports/ModelTC__lightllm__2026-11-06.md) |
| deepseek-ai/DeepEP | 2026-11-02T00:00:00Z | off（降级：未配置 LLM 凭据（api_key / base_url / model 缺一）） | [报告页](report-deepseek-ai__DeepEP__2026-11-02.html) · [源 MD](../reports/deepseek-ai__DeepEP__2026-11-02.md) |
| deepseek-ai/DeepEP | 2026-11-03T00:00:00Z | strong | [报告页](report-deepseek-ai__DeepEP__2026-11-03.html) · [源 MD](../reports/deepseek-ai__DeepEP__2026-11-03.md) |
| deepseek-ai/FlashMLA | 2026-11-02T00:00:00Z | off（降级：未配置 LLM 凭据（api_key / base_url / model 缺一）） | [报告页](report-deepseek-ai__FlashMLA__2026-11-02.html) · [源 MD](../reports/deepseek-ai__FlashMLA__2026-11-02.md) |
| huggingface/text-generation-inference | 2026-11-06T00:00:00Z | off | [报告页](report-huggingface__text-generation-inference__2026-11-06.html) · [源 MD](../reports/huggingface__text-generation-inference__2026-11-06.md) |
| microsoft/onnxruntime | 2026-11-13T14:56:59Z | off（降级：未配置 LLM 凭据（api_key / base_url / model 缺一）） | [报告页](report-microsoft__onnxruntime__2026-11-13.html) · [源 MD](../reports/microsoft__onnxruntime__2026-11-13.md) |
| sgl-project/sglang | 2026-11-06T00:00:00Z | off | [报告页](report-sgl-project__sglang__2026-11-06.html) · [源 MD](../reports/sgl-project__sglang__2026-11-06.md) |
| vllm-project/vllm | 2026-11-06T00:00:00Z | off | [报告页](report-vllm-project__vllm__2026-11-06.html) · [源 MD](../reports/vllm-project__vllm__2026-11-06.md) |

## 特征卡

| 仓库 | commit | 通道 | 代码证据条数 |
|---|---|---|---|
| Dao-AILab/flash-attention | `f63c472c4dc1` | classic | 4 |
| InternLM/lmdeploy | `a0102d47967d` | classic | 11 |
| ModelTC/lightllm | `aadae840d2ee` | classic | 0 |
| deepseek-ai/DeepEP | `f6aa38fe06cd` | classic | 4 |
| deepseek-ai/FlashMLA | `395cb3afbb33` | hot | 0 |
| huggingface/text-generation-inference | `b4adbf2f6e2e` | classic | 0 |
| microsoft/onnxruntime | `fd249b559c48` | classic | 0 |
| sgl-project/sglang | `—` | classic | 0 |
| vllm-project/vllm | `11199bcb7872` | classic | 0 |

## 规律库

**规律库尚无条目（首次真实抽象未触发：inference 簇 5 < 6）**

## 抽象 run 记录

| run_id | 类型 | 簇 | 状态 | LLM 调用 |
|---|---|---|---|---|
| 32a70b9b5b85fd8c | cluster-abstraction | inference | insufficient_samples | 0 |
| 37af1a65da342b5f | cross-domain | <cross-domain> | insufficient_samples | 0 |
| 3f6e4c82e3b95f22 | cluster-abstraction | inference | insufficient_samples | 0 |
| 5e1a6cd25e4ae82b | cluster-abstraction | inference | insufficient_samples | 0 |
