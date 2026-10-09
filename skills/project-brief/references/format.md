# 数据格式 v1

两种呈现：JSON 供 agent 读取，HTML 供人阅读。JSON 按需分片，避免一个日益膨胀的大文件。没有第三套手工维护的 Markdown 副本。

## index.json

```json
{
  "version": 1,
  "project": "项目名称",
  "snapshot_at": "2026-10-08T20:19:00+08:00",
  "headline": "现在已经能做什么，还差什么",
  "context": "项目用途及影响判断的主要限制",
  "update": "本次变化；仅改版应明确无新增实测",
  "items": [
    {"id": "A", "title": "用户能理解的能力", "status": "unverified", "summary": "目前还缺哪些证据", "detail": "items/A.json"}
  ],
  "next": {"title": "下一步可核实的结果", "owner": "谁来做", "steps": ["具体动作及通过条件"], "precondition": "未来前提，或无", "user_action_now": "现在是否需要用户操作"},
  "limitations": ["报告范围及尚未覆盖的事情"]
}
```

索引只存每项唯一的 ID、名称、状态和摘要；不要在详情重复这些字段。沿用稳定 ID，不用排序位置冒充身份。`snapshot_at` 是记录截止时间，HTML 另标生成时间。它们不能互换。

## items/A.json

```json
{
  "acceptance": "项目约定或明确标成建议的通过条件",
  "observations": [{"label": "实际观察", "text": "发生了什么"}],
  "boundary": "证据能说明到哪里，不能说明什么",
  "evidence": [{
    "id": "E1",
    "summary": "这条记录支持哪个具体结论",
    "observed_at": "2026-10-08T20:19:00+08:00",
    "source": {"path": "../project/data/test.json", "pointer": "/checks/A", "sha256": "源文件完整SHA256十六进制"}
  }]
}
```

只有没有引用证据时 `evidence` 可为空；`verified` 必须至少一条。`blocked` 额外加 `blocker: {"reason":"障碍", "owner":"解除者", "resume":"解除后做什么"}`。文本源用 `lines: [12,18]` 替代 `pointer`。SHA-256 来自实际文件字节；保留观察日期，路径变更后重新核实。证据 ID 在单项内唯一，完整定位是条目 ID 加证据 ID。

作者先检查状态是否有证据支持；验证器只能验证字段、引用和文件一致性，不能替代事实判断。`validate` 不读取原证据；加 `--sources` 才核实原片段及哈希。渲染也不打开原证据，只把摘要、定位及链接放入页面。

命令：

```sh
<python> <skill>/scripts/brief.py validate <brief>/index.json --sources
<python> <skill>/scripts/brief.py render <brief>/index.json
<python> <skill>/scripts/brief.py render <brief>/index.json --check
```

修改 JSON 后运行渲染；其摘要哈希覆盖索引、全部详情及样式模板。`--check` 对当前数据重新构造页面比较，允许原生成时间保持不变。没有原证据复核时，页面呈现历史记录，不宣称现场验证。

原证据仅记录日期时，observed_at 使用 YYYY-MM-DD，不编造时分秒；snapshot_at 仍使用带时区的报告截止时间。
