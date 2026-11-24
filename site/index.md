# osslens 静态站点索引

- 基准时间 (as-of)：2026-11-24T13:49:15Z
- 产物：纯静态 HTML/MD；无后端、无外部 JS/CDN、零 LLM、零网络
- 真源：`reports/*.md` · `data/featcards/` · `patterns/library.yaml` · `data/costs/costs.jsonl` · `data/abstract/runs.jsonl`（站点只读）

## 页面

- [首页](index.html)
- [报告](reports.html)
- [时间线](timeline.html)
- [特征卡](featcards.html)
- [规律库](patterns.html)
- [成本](costs.html)
- [抽象 run](runs.html)
- [检索](search.html)
- [范式标签](tags.html)
- [并排对比](compare.html)
- [技术选型](selection.html)
- [本索引（纯 MD，可脱离站点阅读）](index.md)

## 项目清单（按仓库 / 基准时间 / 档位确定性排序）

| 仓库 | 基准时间 (as-of) | 实际档位 | 报告 |
|---|---|---|---|
| Dao-AILab/flash-attention | 2026-11-18T00:00:00Z | fast | [报告页](report-Dao-AILab__flash-attention__2026-11-18.html) · [源 MD](../reports/Dao-AILab__flash-attention__2026-11-18.md) |
| InternLM/lmdeploy | 2026-11-18T00:00:00Z | fast | [报告页](report-InternLM__lmdeploy__2026-11-18.html) · [源 MD](../reports/InternLM__lmdeploy__2026-11-18.md) |
| ModelTC/lightllm | 2026-11-18T00:00:00Z | fast | [报告页](report-ModelTC__lightllm__2026-11-18.html) · [源 MD](../reports/ModelTC__lightllm__2026-11-18.md) |
| Tencent/ncnn | 2026-11-22T11:30:17Z | off（降级：本周配额已用满） | [报告页](report-Tencent__ncnn__2026-11-22.html) · [源 MD](../reports/Tencent__ncnn__2026-11-22.md) |
| deepseek-ai/DeepEP | 2026-11-18T00:00:00Z | fast | [报告页](report-deepseek-ai__DeepEP__2026-11-18.html) · [源 MD](../reports/deepseek-ai__DeepEP__2026-11-18.md) |
| deepseek-ai/FlashMLA | 2026-11-18T00:00:00Z | fast | [报告页](report-deepseek-ai__FlashMLA__2026-11-18.html) · [源 MD](../reports/deepseek-ai__FlashMLA__2026-11-18.md) |
| deepspeedai/DeepSpeed | 2026-11-21T11:09:11Z | off（降级：本周配额已用满） | [报告页](report-deepspeedai__DeepSpeed__2026-11-21.html) · [源 MD](../reports/deepspeedai__DeepSpeed__2026-11-21.md) |
| gvergnaud/ts-pattern | 2026-11-23T12:52:56Z | fast | [报告页](report-gvergnaud__ts-pattern__2026-11-23.html) · [源 MD](../reports/gvergnaud__ts-pattern__2026-11-23.md) |
| huggingface/text-generation-inference | 2026-11-18T00:00:00Z | fast | [报告页](report-huggingface__text-generation-inference__2026-11-18.html) · [源 MD](../reports/huggingface__text-generation-inference__2026-11-18.md) |
| huggingface/transformers | 2026-11-19T15:09:20Z | fast | [报告页](report-huggingface__transformers__2026-11-19.html) · [源 MD](../reports/huggingface__transformers__2026-11-19.md) |
| microsoft/onnxruntime | 2026-11-17T00:00:00Z | fast | [报告页](report-microsoft__onnxruntime__2026-11-17.html) · [源 MD](../reports/microsoft__onnxruntime__2026-11-17.md) |
| nsqio/nsq | 2026-11-24T13:49:15Z | fast | [报告页](report-nsqio__nsq__2026-11-24.html) · [源 MD](../reports/nsqio__nsq__2026-11-24.md) |
| sgl-project/sglang | 2026-11-18T00:00:00Z | fast | [报告页](report-sgl-project__sglang__2026-11-18.html) · [源 MD](../reports/sgl-project__sglang__2026-11-18.md) |
| vercel/turborepo | 2026-11-22T11:29:53Z | off（降级：本周配额已用满） | [报告页](report-vercel__turborepo__2026-11-22.html) · [源 MD](../reports/vercel__turborepo__2026-11-22.md) |
| vllm-project/vllm | 2026-11-18T00:00:00Z | fast | [报告页](report-vllm-project__vllm__2026-11-18.html) · [源 MD](../reports/vllm-project__vllm__2026-11-18.md) |

## 特征卡

| 仓库 | commit | 通道 | 代码证据条数 |
|---|---|---|---|
| Dao-AILab/flash-attention | `68bd095cdd33` | classic | 5 |
| Dao-AILab/flash-attention | `f63c472c4dc1` | classic | 4 |
| InternLM/lmdeploy | `6ddd906bfa91` | classic | 11 |
| InternLM/lmdeploy | `a0102d47967d` | classic | 11 |
| ModelTC/lightllm | `aadae840d2ee` | classic | 0 |
| ModelTC/lightllm | `fa852748dcc9` | classic | 7 |
| Tencent/ncnn | `eb8a50d2eddc` | classic | 0 |
| deepseek-ai/DeepEP | `f6aa38fe06cd` | classic | 4 |
| deepseek-ai/FlashMLA | `395cb3afbb33` | hot | 0 |
| deepspeedai/DeepSpeed | `7681845b3e20` | classic | 13 |
| gvergnaud/ts-pattern | `05e20b669822` | classic | 0 |
| huggingface/text-generation-inference | `b4adbf2f6e2e` | classic | 8 |
| huggingface/transformers | `c52179d2cfe2` | classic | 0 |
| microsoft/onnxruntime | `5e289356eff2` | classic | 0 |
| microsoft/onnxruntime | `fd249b559c48` | classic | 0 |
| nsqio/nsq | `85cf10c09c6c` | classic | 0 |
| sgl-project/sglang | `—` | classic | 0 |
| sgl-project/sglang | `e0decbc3388f` | classic | 19 |
| vercel/turborepo | `b911d19d45f6` | classic | 0 |
| vllm-project/vllm | `11199bcb7872` | classic | 0 |
| vllm-project/vllm | `4dbd382be7e2` | classic | 20 |

## 规律库

共 3 条，见 [规律库页](patterns.html)。

## 抽象 run 记录

| run_id | 类型 | 簇 | 状态 | LLM 调用 |
|---|---|---|---|---|
| 20c90f393e9782ef | cluster-abstraction | inference | degraded | 1 |
| 32a70b9b5b85fd8c | cluster-abstraction | inference | insufficient_samples | 0 |
| 37af1a65da342b5f | cross-domain | <cross-domain> | insufficient_samples | 0 |
| 3f6e4c82e3b95f22 | cluster-abstraction | inference | insufficient_samples | 0 |
| 587ab7f782f8d988 | cluster-abstraction | inference | insufficient_samples | 0 |
| 5e1a6cd25e4ae82b | cluster-abstraction | inference | insufficient_samples | 0 |
| 8c092d942c8310a6 | cluster-abstraction | inference | degraded | 1 |
| 9d48b541b01c45bb | cluster-abstraction | inference | insufficient_samples | 0 |
| b5cb3f5d0c537be6 | cluster-abstraction | inference | insufficient_samples | 0 |
| c43d3a8ae4f71995 | cluster-abstraction | inference | completed | 1 |
| c4b2b75475267dea | cluster-abstraction | inference | insufficient_samples | 0 |
| fc75b5c9e4428a22 | cluster-abstraction | inference | insufficient_samples | 0 |
