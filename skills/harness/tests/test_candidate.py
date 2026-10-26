"""Development-only integration regressions; never installed into projects."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='harness-regression-')
        self.root = Path(self.tmp.name) / 'project'
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, path, *args, expected=0):
        result = subprocess.run([sys.executable, str(path), *map(str, args)],
                                capture_output=True, text=True, encoding='utf-8', cwd=self.root)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def apply(self, *args, expected=0):
        return self.run_script(SKILL / 'scripts/apply_harness.py', '--target', self.root,
                               '--json', *args, expected=expected)

    def install(self, *args):
        return self.apply('--acceptance-check', 'Compare each output claim to sources.txt',
                          '--workflow-entry', 'workflow.md', '--apply', *args)

    def test_preview_and_audit_write_nothing(self):
        (self.root / 'notes.txt').write_text('owned input', encoding='utf-8')
        before = snapshot(self.root)
        result = json.loads(self.apply().stdout)
        self.assertEqual(result['mode'], 'preview')
        self.run_script(SKILL / 'scripts/audit_harness.py', '--target', self.root, '--json')
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(list(self.root.iterdir()), [self.root / 'notes.txt'])

    def test_nonsoftware_install_with_real_manual_acceptance(self):
        (self.root / 'sources.txt').write_text('Fact: population is 42.', encoding='utf-8')
        (self.root / 'workflow.md').write_text('Summarize sources with citations.', encoding='utf-8')
        self.install('--project-type', 'Research')
        config = json.loads((self.root / '.harness/config.json').read_text(encoding='utf-8'))
        self.assertEqual(config['project_type'], 'Research')
        self.assertEqual(config['verification_commands'], [])
        self.assertEqual(config['acceptance_checks'], ['Compare each output claim to sources.txt'])
        self.assertEqual(config['workflow_entry'], 'workflow.md')
        for path in ['.git', 'src', 'tests', 'package.json', 'pyproject.toml']:
            self.assertFalse((self.root / path).exists())
        self.assertEqual((self.root / 'sources.txt').read_text(encoding='utf-8'), 'Fact: population is 42.')

    def test_acceptance_text_is_never_executed_and_json_roundtrips(self):
        text = 'Check "quoted" fields; $(touch unexpected); 中文'
        self.apply('--acceptance-check', text, '--apply')
        conf = json.loads((self.root / '.harness/config.json').read_text(encoding='utf-8'))
        self.assertEqual(conf['acceptance_checks'], [text])
        self.assertFalse((self.root / 'unexpected').exists())

    def test_software_inference_preserved(self):
        (self.root / 'package.json').write_text(json.dumps({'scripts': {'test': 'node test.js', 'build': 'node build.js'}}), encoding='utf-8')
        self.apply('--apply')
        conf = json.loads((self.root / '.harness/config.json').read_text(encoding='utf-8'))
        self.assertEqual(conf['verification_commands'], ['npm test', 'npm run build'])
        self.assertEqual(conf['acceptance_checks'], [])

    def test_explicit_check_override(self):
        (self.root / 'package.json').write_text('{"scripts":{"test":"incorrect-default"}}', encoding='utf-8')
        self.apply('--verification-command', 'documented-runner verify', '--apply')
        conf = json.loads((self.root / '.harness/config.json').read_text(encoding='utf-8'))
        self.assertEqual(conf['verification_commands'], ['documented-runner verify'])

    def test_no_overwrite_on_repeat_or_manual_existing_file(self):
        instructions = self.root / 'INSTRUCTIONS.md'
        instructions.write_text('User-owned instructions\n', encoding='utf-8')
        self.install()
        self.assertEqual(instructions.read_text(encoding='utf-8'), 'User-owned instructions\n')
        before = snapshot(self.root)
        result = json.loads(self.install().stdout)
        self.assertEqual(result['summary']['create'], 0)
        self.assertEqual(snapshot(self.root), before)

    def test_both_profiles_structural_and_budget_checks(self):
        for profile in ['minimal', 'governed']:
            with self.subTest(profile=profile):
                self.root = Path(self.tmp.name) / profile
                self.root.mkdir()
                self.install('--profile', profile)
                validation = json.loads(self.run_script(SKILL / 'scripts/validate_harness.py', '--target', self.root, '--min-score', '90', '--json').stdout)
                self.assertEqual(validation['overall_score'], 100)
                self.run_script(self.root / 'scripts/check-project-harness.py', '--root', self.root)
                budget = json.loads(self.run_script(self.root / 'scripts/check-startup-doc-budget.py', '--root', self.root).stdout)
                self.assertFalse(budget['archive_required'])

    def test_legacy_config_optional_fields_not_required(self):
        self.install()
        p = self.root / '.harness/config.json'
        c = json.loads(p.read_text(encoding='utf-8')); c.pop('acceptance_checks'); c.pop('workflow_entry')
        c['verification_commands'] = ['existing-native-check']
        p.write_text(json.dumps(c), encoding='utf-8')
        self.run_script(self.root / 'scripts/check-project-harness.py', '--root', self.root)
        self.run_script(SKILL / 'scripts/validate_harness.py', '--target', self.root, '--min-score', '90')

    def test_missing_acceptance_not_claimed_as_declared(self):
        # An uncalibrated install (no acceptance, no commands, placeholder entry) must not pass.
        self.apply('--apply')
        result = json.loads(self.run_script(SKILL / 'scripts/validate_harness.py', '--target', self.root, '--json',
                                            expected=1).stdout)
        check = next(c for c in result['categories']['verification']['checks'] if c['label'].startswith('Domain acceptance'))
        self.assertFalse(check['passed'])
        self.assertTrue(check['critical'])
        self.assertFalse(result['passed'])
        self.assertTrue(any('workflow entry' in w for w in result['warnings']))

    def test_direct_symlink_blocked_without_any_installation(self):
        outside = Path(self.tmp.name) / 'outside.txt'; outside.write_text('preserve', encoding='utf-8')
        (self.root / 'AGENTS.md').symlink_to(outside)
        self.apply('--apply', expected=2)
        self.assertEqual(outside.read_text(encoding='utf-8'), 'preserve')
        self.assertFalse((self.root / 'PROGRESS.md').exists())

    def test_parent_escape_blocked_before_writes(self):
        outside = Path(self.tmp.name) / 'outside'; outside.mkdir()
        (self.root / 'scripts').symlink_to(outside, target_is_directory=True)
        self.apply('--apply', expected=2)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.root / 'AGENTS.md').exists())

    def test_directory_collision_blocks_before_writes(self):
        (self.root / 'INSTRUCTIONS.md').mkdir()
        self.apply('--apply', expected=2)
        self.assertFalse((self.root / 'AGENTS.md').exists())

    def test_dirty_git_requires_explicit_flag_and_preserves_user_file(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        owned = self.root / 'user.txt'; owned.write_text('uncommitted user data', encoding='utf-8')
        self.apply('--apply', expected=2)
        self.assertFalse((self.root / 'AGENTS.md').exists())
        self.install('--allow-dirty')
        self.assertEqual(owned.read_text(encoding='utf-8'), 'uncommitted user data')

    def test_ledger_roundtrip_compatible_and_bounded(self):
        self.install()
        script = self.root / 'scripts/harness_log.py'
        for index in range(3):
            self.run_script(script, '--root', self.root, 'append', '--type', 'verification', '--summary', f'case {index}', '--evidence', f'check-{index}')
        result = self.run_script(script, '--root', self.root, 'query', '--grep', 'case 1')
        self.assertIn('check-1', result.stdout)
        self.assertNotIn('case 0', result.stdout)
        self.assertNotIn('case 2', result.stdout)

    def test_broken_transfer_packet_is_rejected(self):
        self.install()
        p = self.root / 'HANDOFF.md'
        p.write_text(p.read_text(encoding='utf-8').replace('first_action:', 'missing_action:'), encoding='utf-8')
        result = self.run_script(self.root / 'scripts/check-project-harness.py', '--root', self.root, expected=1)
        self.assertIn('first_action', result.stdout)

    def test_legacy_governance_uses_real_indexes_and_linked_guard(self):
        self.install('--profile', 'governed')
        (self.root / 'docs/exec-plans/roadmap.md').write_text('# 旧路线图\n阶段及闸门保留。', encoding='utf-8')
        (self.root / 'docs/optimization/SOP.md').write_text('# 常规操作\n业务入口。', encoding='utf-8')
        validator = SKILL / 'scripts/validate_harness.py'
        self.run_script(validator, '--target', self.root, '--min-score', 90)
        # All lifecycle indexes matter; a missing stage cannot be waved through.
        (self.root / 'docs/exec-plans/active/index.md').unlink()
        result = self.run_script(validator, '--target', self.root, expected=1)
        self.assertIn('FAIL: Plan lifecycle', result.stdout)

    def test_unlinked_or_missing_authority_guard_still_fails(self):
        self.install('--profile', 'governed')
        (self.root / 'docs/optimization/SOP.md').write_text('# 常规操作', encoding='utf-8')
        p = self.root / 'AGENTS.md'
        p.write_text(p.read_text(encoding='utf-8').replace('docs/harness-maintenance.md', 'docs/unrelated.md'), encoding='utf-8')
        result = self.run_script(SKILL / 'scripts/validate_harness.py', '--target', self.root, expected=1)
        self.assertIn('FAIL: Optimization intake', result.stdout)
        p.write_text(p.read_text(encoding='utf-8') + '\n维护入口 docs/harness-maintenance.md\n', encoding='utf-8')
        (self.root / 'docs/harness-maintenance.md').write_text('# 维护说明\n只有标题，没有授权规则。', encoding='utf-8')
        result = self.run_script(SKILL / 'scripts/validate_harness.py', '--target', self.root, expected=1)
        self.assertIn('FAIL: Optimization intake', result.stdout)

    def test_default_roadmap_does_not_mask_missing_indexes_or_sop(self):
        self.install('--profile', 'governed')
        validator = SKILL / 'scripts/validate_harness.py'
        for name in ['docs/exec-plans/active/index.md', 'docs/optimization/SOP.md']:
            p = self.root / name
            original = p.read_text(encoding='utf-8'); p.unlink()
            self.run_script(validator, '--target', self.root, expected=1)
            p.write_text(original, encoding='utf-8')
        (self.root / 'docs/optimization/SOP.md').write_text('优化记录自动授权实施。', encoding='utf-8')
        self.run_script(validator, '--target', self.root, expected=1)

    def test_parent_obstructions_block_audit_preview_and_apply_without_writes(self):
        for kind in ['file', 'inside-link', 'outside-link', 'dangling-link']:
            with self.subTest(kind=kind):
                self.root = Path(self.tmp.name) / kind
                self.root.mkdir()
                p = self.root / 'docs'
                if kind == 'file':
                    p.write_text('owned', encoding='utf-8')
                else:
                    dest = (self.root / 'real-docs') if kind == 'inside-link' else Path(self.tmp.name) / (kind + '-target')
                    if kind != 'dangling-link': dest.mkdir()
                    p.symlink_to(dest, target_is_directory=True)
                before = snapshot(self.root)
                preview = json.loads(self.apply().stdout)
                self.assertGreater(preview['summary']['blocked'], 0)
                audit = self.run_script(SKILL / 'scripts/audit_harness.py', '--target', self.root, '--json')
                self.assertEqual(json.loads(audit.stdout)['summary']['blocked'], preview['summary']['blocked'])
                self.apply('--apply', expected=2)
                self.assertEqual(snapshot(self.root), before)
                self.assertFalse((self.root / '.harness').exists())
                if kind != 'file' and kind != 'dangling-link': self.assertEqual(list(dest.iterdir()), [])

    def test_profile_migration_requires_alignment_before_any_write(self):
        self.install('--profile', 'minimal')
        before = snapshot(self.root)
        preview = json.loads(self.apply('--profile', 'governed').stdout)
        self.assertIn('profile mismatch', preview['profile_mismatch'])
        self.apply('--profile', 'governed', '--apply', expected=2)
        self.assertEqual(snapshot(self.root), before)
        validator = SKILL / 'scripts/validate_harness.py'
        self.run_script(validator, '--target', self.root, '--profile', 'governed', expected=1)
        p = self.root / '.harness/config.json'
        config = json.loads(p.read_text(encoding='utf-8')); config['profile'] = 'governed'; p.write_text(json.dumps(config), encoding='utf-8')
        self.install('--profile', 'governed')
        self.run_script(validator, '--target', self.root, '--profile', 'governed', '--min-score', 90)
        self.run_script(self.root / 'scripts/check-project-harness.py', '--root', self.root, '--profile', 'governed')

    def test_decision_warning_only_for_unindexed_records(self):
        self.install('--profile', 'governed')
        script = self.root / 'scripts/check-project-harness.py'
        self.assertEqual(json.loads(self.run_script(script, '--root', self.root).stdout)['warnings'], [])
        (self.root / 'docs/decisions/0001-example.md').write_text('# Decision', encoding='utf-8')
        self.assertTrue(json.loads(self.run_script(script, '--root', self.root).stdout)['warnings'])


if __name__ == '__main__':
    unittest.main()
