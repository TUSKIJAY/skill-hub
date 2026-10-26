"""Development-only regressions for the restored hard rules and the opt-in task-card component; never installed into projects."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
HEADER = ('ID', '方式', '步骤或命令', '预期', '证据位置', '状态', '记录人', '时间')

SCRIPT_RUN = ('A1', 'script', '`run-check`', '输出 ok', 'logs/a1.txt', '已执行', '', '')
SCRIPT_PASSED = ('A1', 'script', '`run-check`', '输出 ok', 'logs/a1.txt', '已通过', '', '')
HUMAN_PENDING = ('A2', 'human', '上板观察', '灯亮', '', '待人工验收', '', '')
HUMAN_PASSED = ('A2', 'human', '上板观察', '灯亮', 'photos/a2.jpg', '已通过', '王工', '2026-10-23')


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def card(status='实施中', rows=(), header=HEADER, status_line=True):
    """A task card in the template's shape; each row is a tuple of cells matching `header`."""
    table = ['| ' + ' | '.join(header) + ' |', '| ' + ' | '.join('---' for _ in header) + ' |']
    table += ['| ' + ' | '.join(row) + ' |' for row in rows]
    lines = ['# TASK-001-demo：演示', '']
    if status_line:
        lines.append(f'status: {status}')
    lines += ['requirements: REQ-1（需求.md §1）', 'acceptance_owner: 王工', '',
              '## 目标', '', '演示。', '', '## 验收项', '', *table, '', '- 状态取值见模板。', '',
              '## 尝试记录', '', '| 次 | 现象 | 证据 | 处理 |', '| --- | --- | --- | --- |', '| 1 | x | y | z |', '',
              '## 结论', '', '待定。', '']
    return '\n'.join(lines)


class TaskCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='task-cards-')
        self.root = Path(self.tmp.name) / 'project'
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    # -- helpers -----------------------------------------------------------------
    def run_script(self, path, *args, expected=0):
        env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
        result = subprocess.run([sys.executable, str(path), *map(str, args)], capture_output=True,
                                text=True, encoding='utf-8', cwd=self.root, env=env)
        self.assertEqual(result.returncode, expected, (result.stdout or '') + (result.stderr or ''))
        return result

    def apply(self, *args, expected=0):
        return self.run_script(SKILL / 'scripts/apply_harness.py', '--target', self.root, '--json', *args,
                               expected=expected)

    def install(self, *args):
        return self.apply('--acceptance-check', '逐项核对输出与来源', '--apply', *args)

    def validate(self, *args, expected=0):
        return self.run_script(SKILL / 'scripts/validate_harness.py', '--target', self.root, *args, expected=expected)

    def lint(self, expected=0):
        return self.run_script(self.root / 'scripts/check-project-harness.py', '--root', self.root, expected=expected)

    def read(self, relative):
        return (self.root / relative).read_text(encoding='utf-8')

    def put_card(self, name, text, newline='\n', directory='docs/tasks'):
        path = self.root / directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.replace('\n', newline).encode('utf-8'))

    def enable(self, *args):
        self.install('--task-cards', *args)

    def assert_lint_fails(self, needle):
        labels = json.loads(self.lint(expected=1).stdout)['lint_failures']
        self.assertTrue(any(needle in label for label in labels), labels)

    # -- default off -------------------------------------------------------------
    def test_default_install_has_no_task_cards(self):
        self.assertIsNone(json.loads(self.apply().stdout)['task_cards'])
        self.install()
        self.assertFalse((self.root / 'docs/tasks').exists())
        self.assertNotIn('task_cards', json.loads(self.read('.harness/config.json')))
        agents = self.read('AGENTS.md')
        self.assertNotIn('Task Cards', agents)
        self.assertNotIn('{{', agents)
        self.assertNotIn('\n\n\n', agents)
        validation = json.loads(self.validate('--min-score', 90, '--json').stdout)
        self.assertNotIn('task_cards', validation['categories'])
        self.assertEqual(validation['overall_score'], 100)
        self.lint()

    def test_cards_ignored_when_component_not_enabled(self):
        self.install()
        self.put_card('TASK-001-bad.md', card('进行中'))
        self.lint()
        self.validate('--min-score', 90)

    def test_task_cards_dir_requires_task_cards(self):
        self.apply('--task-cards-dir', 'docs/cards', '--apply', expected=2)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_unsafe_task_cards_dir_is_rejected_before_any_write(self):
        for bad in ['../outside', '/abs/path', 'C:/x', '', 'a/../../b', '.git/x']:
            with self.subTest(bad=bad):
                self.apply('--task-cards', '--task-cards-dir', bad, '--apply', expected=2)
                self.assertEqual(list(self.root.iterdir()), [])

    # -- opt-in install ----------------------------------------------------------
    def test_preview_with_task_cards_writes_nothing(self):
        (self.root / 'notes.txt').write_text('owned input')
        before = snapshot(self.root)
        result = json.loads(self.apply('--task-cards').stdout)
        self.assertEqual(result['mode'], 'preview')
        self.assertEqual(snapshot(self.root), before)
        status = {item['path']: item['status'] for item in result['plan']}
        self.assertEqual(status['docs/tasks/index.md'], 'create')
        self.assertEqual(status['docs/tasks/task-card-template.md'], 'create')
        self.assertEqual(result['task_cards']['dir'], 'docs/tasks')

    def test_install_creates_files_config_and_agents_section(self):
        self.enable()
        config = json.loads(self.read('.harness/config.json'))
        self.assertEqual(config['task_cards'], {'dir': 'docs/tasks', 'max_active': 1})
        self.assertEqual(config['acceptance_checks'], ['逐项核对输出与来源'])
        index = self.read('docs/tasks/index.md')
        for text in ['同一时间最多一张卡为实施中', '| ID | 标题 | 状态 | 覆盖需求 | 最后更新 |', '只检查卡片字段与状态的一致性，不能证明内容真实']:
            self.assertIn(text, index)
        template = self.read('docs/tasks/task-card-template.md')
        for text in ['status:', 'requirements:', 'acceptance_owner:', '## 目标', '## 范围', '## 声明改动的文件',
                     '## 约束与风险', '## 实施契约', '## 验收项', '## 尝试记录', '## 结论',
                     '| ID | 方式 | 步骤或命令 | 预期 | 证据位置 | 状态 | 记录人 | 时间 |',
                     '草稿', '已批准', '实施中', '待验收', '已完成', '未通过', '阻塞',
                     '待执行', '已执行', '待人工验收', '已通过', '风险', '测试计划', '回滚', '需人确认的项',
                     '模板，本身不授权执行']:
            self.assertIn(text, template)
        agents = self.read('AGENTS.md')
        self.assertIn('\n## Task Cards\n', agents)
        self.assertIn('docs/tasks/', agents)
        for rule in ['只实施状态为“实施中”的那张卡', '`task_cards.max_active`', '“已完成”“未通过”或“阻塞”',
                     '只改卡片“声明改动的文件”', '先更新卡片并写明原因', 'script 验收项设为“已执行”',
                     '只能由人设为“已通过”或“未通过”', 'agent 不得代填', '所有验收项“已通过”才能把卡片设为“已完成”',
                     '卡片保持“待验收”', '分清哪些项是人验过的、哪些只是脚本执行过']:
            self.assertIn(rule, agents)
        self.assertNotIn('{{', agents)
        self.assertLess(agents.index('## Hard Rules'), agents.index('## Task Cards'))
        self.assertLess(agents.index('## Task Cards'), agents.index('## Verification'))
        validation = json.loads(self.validate('--min-score', 90, '--json').stdout)
        self.assertEqual(validation['categories']['task_cards']['score'], 100)
        self.assertEqual(validation['overall_score'], 100)
        self.lint()

    def test_custom_task_cards_dir_is_honoured(self):
        self.enable('--task-cards-dir', './work\\cards/')
        self.assertFalse((self.root / 'docs/tasks').exists())
        self.assertTrue((self.root / 'work/cards/index.md').is_file())
        self.assertTrue((self.root / 'work/cards/task-card-template.md').is_file())
        self.assertEqual(json.loads(self.read('.harness/config.json'))['task_cards']['dir'], 'work/cards')
        self.assertIn('work/cards/', self.read('AGENTS.md'))
        self.validate('--min-score', 90)
        self.lint()
        self.put_card('TASK-001-x.md', card('进行中'), directory='work/cards')
        self.assert_lint_fails('work/cards/TASK-001-x.md')

    def test_existing_files_are_never_overwritten(self):
        (self.root / 'docs/tasks').mkdir(parents=True)
        (self.root / 'docs/tasks/index.md').write_text('用户自己的清单\n', encoding='utf-8')
        self.enable()
        self.assertEqual(self.read('docs/tasks/index.md'), '用户自己的清单\n')
        self.assertTrue((self.root / 'docs/tasks/task-card-template.md').is_file())
        before = snapshot(self.root)
        result = json.loads(self.install('--task-cards').stdout)
        self.assertEqual(result['summary']['create'], 0)
        self.assertEqual(snapshot(self.root), before)

    def test_retrofit_adds_only_missing_files_and_names_manual_merges(self):
        self.install()
        lint_path = self.root / 'scripts/check-project-harness.py'
        lint_path.write_text(lint_path.read_text(encoding='utf-8').replace('lint_task_cards', 'older_lint'), encoding='utf-8')
        before = snapshot(self.root)
        result = json.loads(self.install('--task-cards').stdout)
        after = snapshot(self.root)
        self.assertEqual(set(after) - set(before), {'docs/tasks/index.md', 'docs/tasks/task-card-template.md'})
        self.assertTrue(all(after[name] == digest for name, digest in before.items()))
        hints = ' '.join(result['task_cards']['manual_merge'])
        for name in ['.harness/config.json', 'AGENTS.md', 'scripts/check-project-harness.py']:
            self.assertIn(name, hints)
        # Not configured yet, so the validator still ignores the component.
        self.assertNotIn('task_cards', json.loads(self.validate('--json').stdout)['categories'])
        config_path = self.root / '.harness/config.json'
        config = json.loads(config_path.read_text(encoding='utf-8'))
        config['task_cards'] = {'dir': 'docs/tasks', 'max_active': 1}
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
        checks = json.loads(self.validate('--json').stdout)['categories']['task_cards']['checks']
        self.assertEqual([c['passed'] for c in checks], [True, True, False])
        agents = self.root / 'AGENTS.md'
        agents.write_text(agents.read_text(encoding='utf-8') + '\n## Task Cards\n', encoding='utf-8')
        self.assertEqual(json.loads(self.validate('--json').stdout)['categories']['task_cards']['score'], 100)

    # -- restored hard rules -----------------------------------------------------
    def test_rendered_agents_carries_baseline_scope_and_definition_of_done(self):
        for profile in ['minimal', 'governed']:
            with self.subTest(profile=profile):
                self.root = Path(self.tmp.name) / profile
                self.root.mkdir()
                self.install('--profile', profile)
                agents = self.read('AGENTS.md')
                startup = agents.split('## Use / Maintain')[0]
                for text in ['git status --short --branch', '写入/修改之前还须确认基线', '项目原生的构建/测试命令',
                             '`acceptance_checks` 声明的核对方式', '先记录现状和影响，不得把既有失败误报为本次回归',
                             '只读查询可跳过基线确认']:
                    self.assertIn(text, startup)
                hard = agents.split('## Hard Rules')[1].split('## Verification')[0]
                for text in ['只修改当前请求与已批准范围内的输入、产物或维护文件',
                             '遇到范围歧义时，选择保守、可回滚的解释继续执行并把该假设记录进状态文件',
                             '仅当涉及破坏性/不可逆操作或明显超出请求范围时才暂停请求方向']:
                    self.assertIn(text, hard)
                verification = agents.split('## Verification')[1].split('## Definition of Done')[0]
                self.assertIn('不触发重跑已通过的业务校验', verification)
                self.assertIn('宣称完成前，凡本次改动影响其输入的验证，必须在最终状态上重新运行', verification)
                self.assertIn('必须在最终状态上重新运行', self.read('INSTRUCTIONS.md'))
                self.assertIn('\n## Definition of Done\n', agents)
                done = agents.split('## Definition of Done')[1]
                self.assertEqual(len([line for line in done.splitlines() if line.startswith('- ')]), 5)
                for text in ['目标行为或交付物已实现', '相关验证实际运行并记录证据；结构检查分数不算',
                             '需要人工验收的项在人记录结果前保持“待验收”，不得标为完成',
                             '`PROGRESS.md` 反映当前真相，`HANDOFF.md` 已整体重写为最新交接包，账本已追加对应条目',
                             '未混入无关改动', 'Git 项目按本仓库提交策略形成可恢复的干净边界；非 Git 项目记录可恢复的版本']:
                    self.assertIn(text, done)
                self.assertNotIn('Task Cards', agents)

    # -- lint --------------------------------------------------------------------
    def test_lint_passes_with_only_template_and_ignores_it(self):
        self.enable()
        self.lint()
        template = self.root / 'docs/tasks/task-card-template.md'
        template.write_text(card('进行中', [HUMAN_PASSED[:6] + ('', '')]), encoding='utf-8')
        (self.root / 'docs/tasks/notes.md').write_text(card('进行中'), encoding='utf-8')
        self.lint()

    def test_two_cards_in_progress_fail_unless_limit_raised(self):
        self.enable()
        self.put_card('TASK-001-a.md', card('实施中', [SCRIPT_RUN]))
        self.put_card('TASK-002-b.md', card('实施中', [SCRIPT_RUN]))
        self.assert_lint_fails('at most 1 task card(s) are 实施中 (found 2')
        config_path = self.root / '.harness/config.json'
        config = json.loads(config_path.read_text(encoding='utf-8'))
        config['task_cards']['max_active'] = 2
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
        self.lint()

    def test_human_result_requires_recorder_and_evidence(self):
        self.enable()
        cases = [
            ('记录人', HUMAN_PASSED[:6] + ('', '2026-10-23')),
            ('记录人', HUMAN_PASSED[:6] + ('—', '2026-10-23')),
            ('证据位置', HUMAN_PASSED[:4] + ('', '已通过', '王工', '')),
            ('证据位置', HUMAN_PASSED[:4] + ('<照片路径>', '未通过', '王工', '')),
        ]
        for needle, row in cases:
            with self.subTest(needle=needle, row=row):
                self.put_card('TASK-001-demo.md', card('待验收', [row]))
                self.assert_lint_fails(needle)
        self.put_card('TASK-001-demo.md', card('待验收', [HUMAN_PASSED]))
        self.lint()

    def test_script_result_requires_evidence(self):
        self.enable()
        for state in ['已执行', '已通过']:
            with self.subTest(state=state):
                self.put_card('TASK-001-demo.md', card('实施中', [SCRIPT_RUN[:4] + ('', state, '', '')]))
                self.assert_lint_fails('证据位置')
        self.put_card('TASK-001-demo.md', card('实施中', [SCRIPT_RUN[:4] + ('', '待执行', '', '')]))
        self.lint()

    def test_done_card_needs_every_item_passed(self):
        self.enable()
        self.put_card('TASK-001-demo.md', card('已完成', [SCRIPT_PASSED, HUMAN_PENDING]))
        self.assert_lint_fails('card is 已完成 but acceptance A2 is 待人工验收')
        self.put_card('TASK-001-demo.md', card('已完成', [SCRIPT_PASSED, HUMAN_PASSED[:5] + ('未通过', '王工', '')]))
        self.assert_lint_fails('card is 已完成 but acceptance A2 is 未通过')
        self.put_card('TASK-001-demo.md', card('已完成', []))
        self.assert_lint_fails('has no acceptance items')
        self.put_card('TASK-001-demo.md', card('已完成', [SCRIPT_PASSED, HUMAN_PASSED]))
        self.lint()

    def test_valid_cards_in_every_state_pass(self):
        self.enable()
        piped = ('A3', 'script', '`cat x \\| grep y`', '有输出', 'logs/a3.txt', '已通过', '', '')
        self.put_card('TASK-001-done.md', card('已完成', [SCRIPT_PASSED, HUMAN_PASSED, piped]))
        self.put_card('TASK-002-wait.md', card('待验收', [SCRIPT_RUN, HUMAN_PENDING]))
        self.put_card('TASK-003-wip.md', card('实施中', [SCRIPT_RUN[:4] + ('', '待执行', '', ''), HUMAN_PENDING]))
        for number, status in [(4, '草稿'), (5, '已批准'), (6, '未通过'), (7, '阻塞')]:
            self.put_card(f'TASK-00{number}-x.md', card(status, [HUMAN_PENDING]))
        result = json.loads(self.lint().stdout)
        self.assertEqual(result['lint_failures'], [])
        self.assertTrue(result['passed'])

    def test_vocabulary_and_structure_errors_are_reported(self):
        self.enable()
        cases = [
            ('status', card('进行中', [HUMAN_PENDING])),
            ('status', card(status_line=False)),
            ('状态', card('实施中', [HUMAN_PENDING[:5] + ('完成', '', '')])),
            ('方式', card('实施中', [('A1', 'robot', 'x', 'y', '', '待执行', '', '')])),
            ('missing column', card('实施中', [], header=('ID', '方式', '步骤或命令', '预期', '证据位置', '状态', '时间'))),
        ]
        for needle, text in cases:
            with self.subTest(needle=needle, text=text[:60]):
                self.put_card('TASK-001-demo.md', text)
                self.assert_lint_fails(needle)

    def test_crlf_cards_are_parsed(self):
        self.enable()
        self.put_card('TASK-001-demo.md', card('已完成', [SCRIPT_PASSED, HUMAN_PASSED]), newline='\r\n')
        self.lint()
        self.put_card('TASK-001-demo.md', card('已完成', [SCRIPT_PASSED, HUMAN_PENDING]), newline='\r\n')
        self.assert_lint_fails('card is 已完成')

    def test_config_directory_outside_project_is_rejected(self):
        self.enable()
        config_path = self.root / '.harness/config.json'
        config = json.loads(config_path.read_text(encoding='utf-8'))
        config['task_cards']['dir'] = '../outside'
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
        self.assert_lint_fails('task_cards.dir')
        self.validate(expected=1)

    # -- validator ---------------------------------------------------------------
    def test_validator_requires_index_and_template_only_when_enabled(self):
        self.enable()
        for name, label in [('index.md', 'Task card index exists'), ('task-card-template.md', 'Task card template exists')]:
            with self.subTest(name=name):
                path = self.root / 'docs/tasks' / name
                original = path.read_text(encoding='utf-8')
                path.unlink()
                self.assertIn(f'FAIL: {label}', self.validate('--min-score', 90, expected=1).stdout)
                path.write_text(original, encoding='utf-8')
        self.validate('--min-score', 90)


if __name__ == '__main__':
    unittest.main()
