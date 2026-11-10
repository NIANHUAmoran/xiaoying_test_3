# 测试预期、实际结果、失败与限制

环境为 Windows / Python 3.12.3。通过 `python tests/reproduce.py` 实际调用 CLI 复现 15 个离线场景，再运行全部测试；**35 项通过，0 失败、0 错误**。原始记录见 [test-results.txt](../examples/test-results.txt)、[offline-validation.json](../examples/offline-validation.json) 和 [run-summary.json](../examples/run-summary.json)。

目录按 GitHub 规范组织，docs 为五份指定文档；验证脚本在 tests，合成语料在 data，输入/输出/Trace 与测试报告在 examples。交付核查见 [submission-check.json](../examples/submission-check.json)，逐项确认引用来自该次成功读取的原文，而不只是检查文件是否存在。

## 必验场景：预期与实际

| 场景 | 预期 | 实际结果 | 输入 | 输出 | Trace |
| --- | --- | --- | --- | --- | --- |
| 明确答案 | D01 无冲突时引用 30 天原文 | answered，D01/P1，版本与原文一致 | [输入](../examples/normal.input.json) | [输出](../examples/normal.output.json) | [记录](../examples/normal.trace.json) |
| 文档冲突 | 读取 30/15 天两份制度，不能擅选新版 | needs_clarification，列两条引用及待确认项，补查范围/优先级 | [输入](../examples/conflict.input.json) | [输出](../examples/conflict.output.json) | [记录](../examples/conflict.trace.json) |
| 资料外问题 | 补查后无依据，说明缺口 | out_of_scope，无无关引用和猜测股价 | [输入](../examples/outside.input.json) | [输出](../examples/outside.output.json) | [记录](../examples/outside.trace.json) |
| 相似改写 | 字面检索空结果后调整查询 | 从“费用单据最晚什么时候交”改为“报销期限”，读取 D01 后 answered | [输入](../examples/paraphrase.input.json) | [输出](../examples/paraphrase.output.json) | [记录](../examples/paraphrase.trace.json) |
| 上下文追问 | 从历史报销主题转向本轮平台属性 | answered，引用 D03“财务自助服务平台”，不重复期限答案 | [输入](../examples/context.input.json) | [输出](../examples/context.output.json) | [记录](../examples/context.trace.json) |
| 工具失败 | 不把读取失败解释成文档不存在 | tool_failure，列出缺口，不给确定答案 | [输入](../examples/tool-failure.input.json) | [输出](../examples/tool-failure.output.json) | [记录](../examples/tool-failure.trace.json) |

这六组为显式 Mock，用于验证流程和确定性守卫，不冒充真实模型效果。正常、资料不足、工具失败三类最低要求均有实际输入、输出和运行记录。缺问题的 validation 记录由运行时产生，不伪装为模型决策。

## 文档替换与对抗检查

| 场景 | 实际结果 |
| --- | --- |
| [changed-document](../examples/changed-document.output.json) | D01 原文与标注改成 45 天后，回答与引用都变为 45 天 |
| [resolved-conflict](../examples/resolved-conflict.output.json) | D01、D02 都为 30 天后，最终动作从 clarify 转为 answer |
| [partial-failure](../examples/partial-failure.output.json) | D01 已读、D02 失败；保留 D01 引用但状态为 tool_failure，不凭单份制度回答 |
| [transient-failure](../examples/transient-failure.output.json) | 同参数读取恢复后允许回答，错误历史保留并标为 resolved |
| [unsupported-product](../examples/unsupported-product.output.json) | 明确的支付方式问题归为资料外，不错误要求补充模糊主题 |
| [multi-topic](../examples/multi-topic.output.json) | 期限和平台两个属性不只答一半，保守追问 |
| [step-limit](../examples/step-limit.output.json) | 部分证据已读时达到上限，仍为 incomplete，保留已读依据 |

单元测试还检查：错误引用字段类型不崩溃；伪造文档或 quote、未读取来源、无引用和跨主题引用被拒；更晚日期不覆盖另一制度；历史 assistant 的“999 天”不是依据；新主题覆盖旧主题；报销系统离线问题不套用产品离线 FAQ；一次检索错误恢复后不被永久视为工具失败。

特别验证原文同时写“旧的 30 天规定已废止，现行期限为 15 天”而旧标注仍出现时，回答保留完整现行限定，不仅输出旧值 30 天。这个测试证明完整引用不会被短答截断，不代表已经实现对任意自然语言的废止、条件或优先级推理。

## 真实模型观察

2026 年 11 月 11 日（Asia/Shanghai），使用用户本地配置的 qwen3.8-max 实际运行：

| 场景 | 模型动作与观察结果 | 实际输出 | 独立 Trace |
| --- | --- | --- | --- |
| 正常，3 步 | search → read D01 → respond(answer)，原文 30 天与版本正确 | [live-normal](../examples/live-normal.output.json) | [记录](../examples/live-normal.trace.json) |
| 冲突，5 步 | search → read D01 → read D02 → 补查范围/优先级 → respond(clarify)，列 30/15 天与确认问题，不按新版选15 | [live-conflict](../examples/live-conflict.output.json) | [记录](../examples/live-conflict.trace.json) |
| 改写，5 步 | 原句搜索空 → 改“报销期限” → read D01 → read D03 → respond(answer)，只引用相关 D01 | [live-paraphrase](../examples/live-paraphrase.output.json) | [记录](../examples/live-paraphrase.trace.json) |

三条输入和语料对应关系见 [材料索引](../examples/README.md)。[check_live_outputs.py](../tests/check_live_outputs.py) 已将每条引用与源文件及成功 read 的返回结果核对，结果见 [live-validation-summary.json](../examples/live-validation-summary.json)。本次实际模型在改写路径中额外读取了平台 D03，但最终未将无关片段当作期限依据，按实际五步记录保留。

真实模型路径与离线路径分别归档，未改写日志使两者看起来一致。默认 16 步上限、引用失败反馈和明确未完成状态由程序保证；三次真实样例通过不能证明未来每次模型都能成功。

## 已知局限与未完成事项

- 知识库仅有三个预定义主题、少量合成文档；字面关键词检索和有限同义词解析不等价于通用中文语义检索。未知表达可能漏召回或触发保守澄清。
- “标注值出现在原文中”只能约束结构一致性，不能自动证明任意复杂语义。完整原文保留限定，冲突分组仍依赖人工维护的受控事实标注。
- 相关文档覆盖针对这份有限、可枚举语料，不表示搜索了全企业或互联网。没有长文切片、向量索引和跨库证据融合。
- 不自动裁决制度效力、scope 或 priority；范围不同或优先关系不明时应向用户确认，日期不是授权。复合问题要求拆分，暂不生成多属性综合答案。
- 历史由调用方提供；只有 user/assistant 两类数据，不提供持久化会话、身份认证、真实企业授权或生产级文档治理。
- 没有测大样本成功率、真实延迟统计、系统性提示注入攻击或复杂自然语言蕴含。其他工具失败场景由离线测试验证，本轮未另行执行真实模型故障用例。
- 默认单模型请求 30 秒超时、最多 16 步，没有全任务墙钟超时；协议非法时明确未完成，不做隐式格式修复。
- GitHub URL、最终 commit SHA 与私有仓库评审权限尚待提交时填写，未完成远程发布。
