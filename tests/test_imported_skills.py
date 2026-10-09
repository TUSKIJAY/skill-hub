"""Offline checks for the imported skills; no real agent calls or project edits."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ImportedSkillTests(unittest.TestCase):
    def run_ok(self, args, **kwargs):
        result = subprocess.run(args, capture_output=True, text=True, timeout=20, **kwargs)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_harness_profiles_preserve_existing_files_and_support_history(self):
        scripts = ROOT / 'skills/project-harness-engineer/scripts'
        for profile in ('minimal', 'governed'):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as directory:
                target = Path(directory)
                apply = [sys.executable, str(scripts / 'apply_harness.py'),
                         '--target', directory, '--profile', profile, '--json']
                self.run_ok(apply)
                self.assertEqual(list(target.iterdir()), [], 'preview wrote files')
                self.run_ok(apply + ['--apply'])
                self.run_ok([sys.executable, str(scripts / 'validate_harness.py'),
                             '--target', directory, '--profile', profile, '--json'])
                self.run_ok([sys.executable, str(target / 'scripts/check-project-harness.py'),
                             '--root', directory, '--profile', profile])
                self.run_ok([sys.executable, str(target / 'scripts/check-startup-doc-budget.py'),
                             '--root', directory])
                progress = target / 'PROGRESS.md'
                progress.write_text(progress.read_text() + '\nUser-owned fact.\n')
                before = progress.read_bytes()
                result = json.loads(self.run_ok(apply + ['--apply']).stdout)
                self.assertEqual(result['summary']['create'], 0)
                self.assertEqual(progress.read_bytes(), before)
                ledger = [sys.executable, str(target / 'scripts/harness_log.py')]
                self.run_ok(ledger + ['append', '--type', 'verification', '--summary', 'fixture verified'])
                found = self.run_ok(ledger + ['query', '--grep', 'fixture', '--format', 'json'])
                self.assertEqual(json.loads(found.stdout)['summary'], 'fixture verified')

    def test_bridge_forwards_literal_prompt_closes_stdin_and_cleans_tempfiles(self):
        bridge = ROOT / 'skills/agent-cli-bridge/scripts/agent_print.sh'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scratch = root / 'temporary files'
            scratch.mkdir()
            stub = root / 'claude'
            stub.write_text('#!/bin/bash\n'
                            'if read -r unwanted; then exit 91; fi\n'
                            'printf "%s\\0" "$@" > "$BRIDGE_TEST_ARGS"\n'
                            'printf "fixture answer\\n"\n'
                            'exit "${BRIDGE_TEST_EXIT:-0}"\n')
            stub.chmod(0o755)
            captured = root / 'args'
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'],
                       TMPDIR=str(scratch), BRIDGE_TEST_ARGS=str(captured))
            prompt = 'literal $HOME `command` $(command); 中文'
            call = ['/bin/bash', str(bridge), '--cli', 'claude', '--prompt', prompt,
                    '--dir', 'directory with spaces']
            result = self.run_ok(call, env=env, input='must not reach the CLI\n')
            self.assertEqual(result.stdout, 'fixture answer\n')
            self.assertEqual(captured.read_bytes().split(b'\0')[:-1],
                             [b'--print', prompt.encode(), b'--add-dir', b'directory with spaces'])
            self.assertEqual(list(scratch.iterdir()), [])
            env['BRIDGE_TEST_EXIT'] = '7'
            failed = subprocess.run(call, env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(failed.returncode, 7)
            self.assertEqual(list(scratch.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
