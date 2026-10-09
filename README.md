# Personal Skill Hub

自己的技能目录、源码库和安装入口。按用途查找，按需加载，跨设备复用；同一份源码供 Codex 与 Claude 使用。

[浏览技能目录](docs/catalog.md) · [本地可搜索页面](docs/index.html) · [Agent 索引](catalog.json)

当前登记 19 项：2 项保留安装入口，17 项仅登记来源。已确认弃用的技能已从当前源码和目录中移除，历史版本仍可通过 Git 记录回溯。

`project-brief` 已确认在用；其余未弃用条目的使用状态仍待确认，不能从“安装目录里有文件”推断活跃使用。`agent-cli-bridge` 和 `project-harness-engineer` 的本机副本有分歧，未自动合并。盘点是 2026-10-09 的快照，官方插件缓存不在迁移范围内。标为弃用不会自动删除机器上的旧安装。

## 新设备安装

先在新设备登录有权访问本仓库的 GitHub 账号，再克隆：

```sh
gh repo clone TUSKIJAY/skill-hub
cd skill-hub
```

Hub 本身只需要 Python 3.10+ 标准库，不会自动安装技能的外部依赖。本机按既有约定使用 Homebrew Python 3.13；其他设备使用其已配置的 Python 环境。下面命令中的 `python` 表示那个明确选定的解释器。Windows 可用 `py -3`；本机请替换为 `/opt/homebrew/opt/python@3.13/bin/python3.13`。

```sh
# 目录与按用途搜索：只读元数据
python scripts/hub.py list
python scripts/hub.py list 报告 --available

# 查看来源、依赖和资源路径；需要时才读取技能正文
python scripts/hub.py show project-brief
python scripts/hub.py show project-brief --instructions

# 先预览，再安装；同一份技能可以给两个 agent 使用
python scripts/hub.py install project-brief --agent codex --agent claude --dry-run
python scripts/hub.py install project-brief --agent codex --agent claude

# 可选组合；组合中的第三方运行依赖不会随技能安装
python scripts/hub.py install --profile desktop --agent codex
```

macOS / Linux 默认用目录链接，Windows 默认复制，无需开启开发者模式。`--mode copy` 可显式使用独立副本。已在 macOS 测试链接和复制两种安装行为；Windows 原生环境尚未实测。

遇到已有同名目录，默认停止并保留原内容。先比较后，确需接管时加 `--replace`：旧目录会移到 `.local/backups/`，不会直接删除。Hub 不执行 skill 脚本、不安装依赖、不读取项目证据。

## 更新、检查和撤回

```sh
# 先把 GitHub 的变更拉到当前设备；有本地改动时先处理改动
# 链接安装会随源文件更新即时生效；复制安装需再运行 update
git pull --ff-only
python scripts/hub.py doctor
python scripts/hub.py update --dry-run
python scripts/hub.py update

# 卸载 Hub 管理的版本（移到备份），或恢复接管前的安装
python scripts/hub.py uninstall project-brief --agent codex
python scripts/hub.py uninstall project-brief --agent codex --restore-previous
```

最后两条是不同选择，不要依次执行。`update` 不联网，只同步当前设备已登记的安装；本地修改过的复制版会停止更新，避免覆盖。`doctor` 检查此 Hub 管理的安装，不推断其他技能的健康。备份和设备安装记录都在被 Git 忽略的 `.local/`，不要随意删掉，也不会推送到 GitHub。迁移或删除仓库前，先处理指向它的安装链接。

## 添加与维护技能

1. 决定是纳管源码，还是只记录来源。第三方技能先保留原作者、仓库和许可证信息；来源不明的私有快照不当成原创。
2. 纳管时把必要的 `SKILL.md`、scripts、references、assets 等放到 `skills/<id>/`。不要复制项目数据、证据、账号配置、运行日志或缓存。只登记来源则不复制源码。
3. 在 `catalog.json` 添加条目；`kind: managed` 需含 `path` 和 `requirements`，`kind: reference` 可记录上游和待整理原因。`lifecycle` 区分 `active`（已确认使用）、`unconfirmed`（待确认）、`retired`（已弃用）。新盘点条目默认待确认；弃用项禁止安装和进入组合。已有条目可作结构示例。设备组合在 `profiles.json` 中维护。
4. 验证并生成目录，检查差异后再提交：

```sh
python scripts/hub.py check
python -m unittest discover -s tests -v
python scripts/hub.py build
git diff --check
```

`check` 验证基本结构、组合引用和常见敏感文件模式，不能替代源码审阅，也不能证明技能业务功能已通过测试。Git 历史用于版本追踪；回退版本前检查依赖和影响范围。

## 渐进式披露

目录只回答“有什么、做什么、在哪里”。Agent 用 `list` 找候选，`show` 取得来源和资源路径，需要用时才读那个 skill 的 `SKILL.md`，再按其指引读取相关参考文件。不要把整座技能库都加载进上下文。`project-brief` 还提供项目概览 → 单项详情 → 证据索引 → 原始片段的独立读取入口。

## 私有范围

此仓库用于个人维护，保持 private；没有启用 GitHub Pages。`docs/index.html` 在本地打开即可使用，不会把目录发布到公网。外来技能沿用自身许可；本仓库不统一授予第三方内容的再分发许可。来源尚未确认的条目明确保留 `not-yet-recorded`，以后逐项补齐。
