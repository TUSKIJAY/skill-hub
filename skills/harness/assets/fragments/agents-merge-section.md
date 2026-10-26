## 状态与交接（harness）

本节把 harness 的启动、状态和完成标准接到本文件。本文件上面的项目规则照常有效，两者冲突时以更严格的为准。

- 启动：读 `INSTRUCTIONS.md` 和 `PROGRESS.md`。`HANDOFF.md` 只读一次，开工即过期，它不覆盖本次用户请求。事实冲突的优先级：当前权威材料和交付物核验 > `PROGRESS.md` > `HANDOFF.md` > 聊天记忆。
- 使用与维护：默认按现有流程完成本次请求。只有用户明确要求改流程、规则或验收方式时才进入维护，并读 `docs/harness-maintenance.md`。
- 任务分级：小型、明确请求的改动直接执行并验收，不另建计划或评审文件。
- 写入前确认基线：按 `INSTRUCTIONS.md` 的验收方式或项目原生检查，先核对现状。基线已失败时先记录现状和影响，不把既有失败当成本次回归。{{GIT_RULE}}
- 保留无关改动和用户已有改动，只改本次请求范围内的文件。范围有歧义时，取保守、可回滚的理解继续，并把假设写进状态文件；只读问答在回答里说明假设即可。
- 账本只经 `{{PYTHON}} scripts/harness_log.py` 读写：`append --type <milestone|verification|handoff|decision|incident|intent> --summary "..." --evidence "..."` 追加，`show --seq <N>` 查单条，`query --grep <关键词>` 按需检索。`PROGRESS.md` 只留指向账本的索引，开工不整卷读取历史。只读问答不写状态和账本。
- 外部写入两段记账：会改变外部系统状态的操作（对外提交、发送、发布、下单、调用写接口），动手前先 `{{PYTHON}} scripts/harness_log.py append --type intent --summary "准备做 X" --evidence "<操作标识/幂等键/目标位置>"`，完成后用 `--closes <那条 seq>` 追加 `milestone`（成功，写回执）或 `incident`（失败或不确定）。写入前和接手时先跑 `{{PYTHON}} scripts/harness_log.py pending`，有未闭合意图先核实外部状态，核实前不得重做；能带幂等键的操作必须带。
- 恢复前闸门：接手或续接时，昂贵（长时间运行、占用大量算力或配额）、不可逆、或 `HANDOFF.md` `do_not` 点名的动作，动手前必须向用户出示要做什么、预计成本、现有产物或状态为何不够，等用户确认后再做；不得因为「上次的任务已不在」「时间过去很久」或「状态文件过期」就自行解除 `do_not`，它只由用户解除。确认前只核实和报告，不启动后台进程、不建计划任务、不把状态改写成进行中。
- 读取和输出按 `INSTRUCTIONS.md` 的 Context Budget 执行：读文件先 `outline`（启动四件除外），超预算只读行段；输出长短不确定先落盘再 `head`；交给子代理时写明只回结论（不超过 {{CB_HEAD_LINES}} 行，每条带"文件:行"），不回原文。

### 完成标准（Definition of Done）

有交付或改动时，以下都满足才算完成：

- 交付物已实现。
- 相关验证在最终状态上实际运行，并留下证据。结构检查分数不算验证。需要人工验收的项，在人记录结果前保持"待验收"。
- `PROGRESS.md` 只写已为真的事实，`HANDOFF.md` 整体重写，账本已追加对应条目，本次的 intent 条目均已闭合。
- 没有混入无关改动。
- {{RECOVERY_RULE}}
