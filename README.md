# 第 3 题：企业知识问答 Agent

帮助员工查找制度或产品问题的可靠依据，输出回答、文档 ID 与版本、原文引用、冲突、资料缺口和任务状态。只依据成功读取的合成文档作答；冲突时说明差异并追问，不按较新版本日期自行选答案。

本目录是独立项目根目录。若位于外层工作区，先执行 `cd .\xiaoying_test_3`；所有命令从本目录运行，上传 GitHub 时以本目录内容作为仓库根目录。代码不导入其他题目录。

已完成 **35 项测试、15 个离线场景与三条真实模型路径**。真实模型正常路径为 3 步，冲突查证与改写检索路径各为 5 步。引用原文、版本和实际读取结果已逐项核对，详见 [评估文档](docs/03-evaluation.md)。

## 项目目录

```text
xiaoying_test_3/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── src/                          # 模型、检索、原文读取、引用守卫、CLI
├── tests/                        # 可执行测试、复现和交付核查脚本
├── examples/                     # 输入、实际输出、Trace、测试报告
│   ├── README.md                 # 场景与材料索引
│   ├── normal.input.json
│   ├── normal.output.json
│   ├── normal.trace.json
│   ├── outside.*.json
│   ├── tool-failure.*.json
│   ├── conflict.*.json
│   ├── live-*.{input,output,trace}.json
│   └── test-results.txt
├── data/                         # 带 ID、日期和原文的合成 FAQ、制度
└── docs/
    ├── 01-requirements.md        # 用户、目标、范围、成功标准
    ├── 02-solution.md            # 调用流程、动态决策、技术取舍
    ├── 03-evaluation.md          # 预期、实际结果、失败与限制
    ├── 04-ai-usage.md            # AI 辅助、个人贡献及验证
    └── 05-retrospective.md       # 难点、学习收获、下一步
```

## 环境、安装与快速运行

Python 3.12+，已在 Windows / Python 3.12.3 验证。全部使用标准库，无须安装第三方包，依赖声明见 requirements.txt。无需模型配置即可复现全部离线场景：

```powershell
python --version
python tests/reproduce.py
python tests/check_submission.py
```

复现脚本实际调用 CLI，核对退出码与状态，保存成组材料并运行 35 项测试。它不会调用真实模型，也不覆盖归档的真实模型输出。交付核查检查目录、五份文档、18 组输入/输出/Trace、原文与版本、读取覆盖及文档链接。

单独运行：

```powershell
python -B -m src --mock --input examples/normal.input.json --output .runtime/normal.output.json
python -B -m src --mock --input examples/conflict.input.json --data data/conflict.world.json
python -B -m unittest discover -s tests -v
```

## 输入、输出与可靠性边界

输入示例：

```json
{
  "request_id": "qa-001",
  "question": "那在哪个平台提交？",
  "history": [
    {"role": "user", "content": "报销期限是多久？"},
    {"role": "assistant", "content": "请以制度原文为准。"}
  ]
}
```

question 必填；history 可选，只接受 user/assistant 与字符串 content。request_id 可选，未提供时按输入计算稳定标识，不用于跨请求知识缓存。历史用户问题帮助补全主题；历史 assistant 回答不能充当制度依据。明确新主题覆盖旧主题，多属性问题保守要求拆分。

输出包括 answer、citations（文档 ID、片段 ID、版本日期、完整原文）、conflicts、gaps、clarification_question、status 和 trace。确定答案直接呈现成功读取的完整原文，保留现行/旧规、条件及例外表述，避免只取一个数字。引用版本由工具返回，模型不能自行编造。

运行时要求目标主题的所有相关文档均已成功读取；只读 D01 而未读 D02，不能给出确定答案。D01=30 天、D02=15 天且适用关系未知时，结果为 needs_clarification，并列出两份原文、版本与待确认项；较新日期不代表优先适用。工具错误不等于资料不存在，成功读取的部分证据会保留。

本知识库只含合成规则。检索是可解释的关键词匹配，意图解析使用有限同义词及历史用户主题，当前支持报销期限、报销提交平台、产品离线能力三个主题。标注与原文子串一致不等于通用语义蕴含证明；复杂制度效力、多主题综合回答、开放域答案与真实企业权限管理不在当前范围。

## 六项验收与复现

| 场景 | 输入和数据 | 预期状态 |
| --- | --- | --- |
| 明确答案 | normal，world | answered，D01 原文 30 天 |
| 文档冲突 | conflict，conflict.world | needs_clarification，列 30/15 天并追问 |
| 资料外问题 | outside，world | out_of_scope，无无关引用 |
| 相似改写 | paraphrase，world | 首轮空结果后改写检索并 answered |
| 上下文追问 | context，world | 定位 D03 平台，不重复期限答案 |
| 工具失败 | tool-failure，tool-failure.world | tool_failure，明确查证缺口 |

全部文件链接见 [examples/README.md](examples/README.md)。工具失败单独复现：

```powershell
python -B -m src --mock --input examples/tool-failure.input.json --data data/tool-failure.world.json
```

工具失败返回退出码 1，是该负例的预期结果。替换文档的 changed-document、冲突消除的 resolved-conflict、部分读取失败、临时故障和步数上限等扩展记录也已归档。

## 真实模型配置与运行

参照 [.env.example](.env.example) 在本目录创建 .env，填写 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY；也可用 --env-file 指定本机配置。环境变量优先，支持单行 KEY=VALUE、整行注释和成对引号，不支持变量展开或多行值。真实密钥未纳入交付。

模型服务需支持 HTTPS、Bearer 认证和 /chat/completions JSON 协议。LLM_BASE_URL 填接口前缀，程序自动追加 /chat/completions；响应从 choices[0].message.content 读取纯 JSON 动作。默认模式需要真实模型配置，不会自动退回 Mock。

配置好后可重跑三条真实路径，不加 --mock：

```powershell
python -B -m src --input examples/live-normal.input.json --output examples/live-normal.output.json
python -B -m src --input examples/live-conflict.input.json --data data/conflict.world.json --output examples/live-conflict.output.json
python -B -m src --input examples/live-paraphrase.input.json --output examples/live-paraphrase.output.json
python -B tests/check_live_outputs.py
python tests/reproduce.py
```

最后的离线复现仅重新提取真实输出中的 Trace，不再次调用模型。真实路径与 Mock 各自标记，不把离线动作说成模型结果。首次检索空结果后由模型选择改写；冲突时模型读取两份原文并补查范围/优先级，运行时只负责核验，不预设虚假模型日志。

每次模型请求超时 30 秒，响应上限 1 MiB；默认最多 16 个模型动作（--max-steps 可设 1..100）。非法动作或上限返回 incomplete，并保留已读取证据与日志。引用校验不通过时把错误反馈给模型继续选择下一动作，不无界重试。

退出码：0 表示 answered、needs_clarification、out_of_scope 或 needs_information；1 表示 tool_failure 或 incomplete；2 表示输入、配置或语料错误。退出码 0 不表示一定已获得答案，应同时查看 status。

## 评审入口与提交信息

| 检查项 | 入口 |
| --- | --- |
| 用户、范围、成功标准 | [01-requirements.md](docs/01-requirements.md) |
| 动态决策、引用与冲突设计 | [02-solution.md](docs/02-solution.md) |
| 预期、实际结果、失败与限制 | [03-evaluation.md](docs/03-evaluation.md) |
| AI 辅助与个人贡献 | [04-ai-usage.md](docs/04-ai-usage.md) |
| 难点、用时、下一步 | [05-retrospective.md](docs/05-retrospective.md) |
| 验证材料索引 | [examples/README.md](examples/README.md) |
| 交付核查 | [submission-check.json](examples/submission-check.json) |

题号：3。GitHub URL、最终 commit SHA、私有仓库评审权限待最终提交时填写，当前未远程发布。本人实际用时、独立修改和亲自复核内容应在提交前如实补充。
