# 验证材料索引

每组提供同名前缀 `.input.json`、`.output.json`、`.trace.json`。输出为实际程序运行结果，独立 Trace 直接提取原输出，不补造模型动作。mode=mock 是离线策略，mode=live 是真实模型，mode=validation 是输入校验。真实输出在离线复现时保持不变。

## 六项必验

| 场景 | 输入 | 实际输出 | 运行记录 | 语料 |
| --- | --- | --- | --- | --- |
| 明确答案 | [normal.input](normal.input.json) | [normal.output](normal.output.json) | [normal.trace](normal.trace.json) | world |
| 文档冲突 | [conflict.input](conflict.input.json) | [conflict.output](conflict.output.json) | [conflict.trace](conflict.trace.json) | conflict.world |
| 资料外问题 | [outside.input](outside.input.json) | [outside.output](outside.output.json) | [outside.trace](outside.trace.json) | world |
| 相似问法 | [paraphrase.input](paraphrase.input.json) | [paraphrase.output](paraphrase.output.json) | [paraphrase.trace](paraphrase.trace.json) | world |
| 上下文追问 | [context.input](context.input.json) | [context.output](context.output.json) | [context.trace](context.trace.json) | world |
| 工具失败 | [tool-failure.input](tool-failure.input.json) | [tool-failure.output](tool-failure.output.json) | [tool-failure.trace](tool-failure.trace.json) | tool-failure.world |

上述场景包含正常、信息或资料不足、工具失败三类最低材料覆盖，并补齐本题全部验收点。语料全部在 [data](../data) 中，以对应名称加 `.json` 读取，内容为合成 FAQ 与制度。

## 扩展场景

- `changed-document`：D01 原文从 30 天替换为 45 天，答案与引用同步改变。
- `resolved-conflict`：D01/D02 都改为 30 天，最后 respond.kind 从 clarify 变为 answer。
- `partial-failure`：D01 成功读取、D02 失败，保留 D01 依据但不作确定回答。
- `transient-failure`：读取一次错误后由离线策略选择重试，成功后错误标记为 resolved，历史保留。
- `ambiguous`、`multi-topic`：不明确指代或复合问题需要澄清。
- `unsupported-product`：明确但资料未覆盖的产品属性归类为资料外，不误作含糊追问。
- `missing-question`：输入校验记录，不产生模型调用；`step-limit`：读完部分证据后达到上限，明确未完成。

这些扩展均有同名输入、输出和独立 Trace；预期与实际行为见 [评估文档](../docs/03-evaluation.md)。

## 真实模型路径

| 场景 | 输入 | 实际输出 | 运行记录 |
| --- | --- | --- | --- |
| 正常引用回答 | [live-normal.input](live-normal.input.json) | [live-normal.output](live-normal.output.json) | [live-normal.trace](live-normal.trace.json) |
| 两份冲突制度与补查 | [live-conflict.input](live-conflict.input.json) | [live-conflict.output](live-conflict.output.json) | [live-conflict.trace](live-conflict.trace.json) |
| 空结果后改写检索 | [live-paraphrase.input](live-paraphrase.input.json) | [live-paraphrase.output](live-paraphrase.output.json) | [live-paraphrase.trace](live-paraphrase.trace.json) |

真实调用配置的 qwen3.8-max，分别为 3、5、5 步。引用原文、版本及成功读取对应关系核对见 [live-validation-summary.json](live-validation-summary.json)，核对脚本不调用模型。

## 报告与复现

在项目根目录执行 `python tests/reproduce.py`，复现 15 个离线场景并运行 35 项测试；执行 `python tests/check_submission.py`，核查 18 组三件材料、原文引用、覆盖和文档链接。

报告：[test-results.txt](test-results.txt)、[offline-validation.json](offline-validation.json)、[run-summary.json](run-summary.json)、[submission-check.json](submission-check.json)、[delivery-status.json](delivery-status.json)。
