## Context Budget

每次读取和每条输出都占上下文。下面四条使用和维护时都生效。数字由 `.harness/config.json` 的 `context_budget` 决定；改数字属于维护，改完同步改这里。路径一律加引号。

1. 读文件先看大纲。读文件前先跑 `{{PYTHON}} scripts/harness_read.py outline "<文件>"`（启动四件除外）；已知要找的词时，也可以先用 `grep -n "<词>" "<文件>"`（Windows 用 `Select-String`）找行号；不要先用读文件工具读开头再决定。`outline` 打印总行数、总字节和标题行。总行数不超过 {{CB_FILE_LINES}}、总字节不超过 {{CB_FILE_BYTES}} 时可以整读；否则只用 `{{PYTHON}} scripts/harness_read.py lines "<文件>" <起> <止>` 读需要的行段，一条命令合计最多 {{CB_OUTPUT_LINES}} 行，不要用循环把多段拼在一起输出。
2. 输出长短不确定就先落盘。命令或查询的输出，只要不能确定在 {{CB_OUTPUT_LINES}} 行以内，就先重定向到 `{{CB_SCRATCH_DIR}}/<YYYY-MM-DD>-<主题>.txt`（目录不存在先建），再用 `{{PYTHON}} scripts/harness_read.py head "<该文件>"` 看总行数和前 {{CB_HEAD_LINES}} 行。要看更多，按行段取。不能写文件时，用命令或接口自带的限行参数只取前 {{CB_HEAD_LINES}} 行。
3. 查数据先问总数。数据源有计数接口就先计数；没有就先取前 {{CB_OUTPUT_LINES}} 条样本。明细按页取，每页不超过 {{CB_OUTPUT_LINES}} 条或 {{CB_OUTPUT_BYTES}} 字节。
4. 子代理只回结论和定位。交给子代理或外部 CLI 的批量阅读，交办时写三项：任务一句话；回什么（结论不超过 {{CB_HEAD_LINES}} 行，每条带定位，有行号给"文件:行"，没有就给段落标题或查询键）；不回什么（整段原文；任务明确要求的短引文除外，带定位）。
