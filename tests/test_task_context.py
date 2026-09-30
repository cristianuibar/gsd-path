import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import dispatch_driver, task_context


ROOT = Path(__file__).resolve().parents[1]


class TaskContextTests(unittest.TestCase):
    def test_dispatch_supplies_context_without_a_second_intent_read(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            intent = repo / '.project/intent/INTENT.md'
            intent.parent.mkdir(parents=True)
            intent.write_bytes('## Success criteria\n\n1. First outcome.\n2. Other outcome.\n\n'
                              '## Constraints\n\nKeep the wire format.\n'.encode("utf-8"))
            task = repo / 'T001.md'
            task.write_bytes('## Intent coverage\n\n- SC1\n'.encode("utf-8"))
            brief = dispatch_driver.brief_text(
                dict(worktree=str(repo), task_id='T001', task_file='T001.md',
                     base='a' * 40, mode='serial'),
                ROOT / 'skills/gsd-path/references/coder.md',
                ROOT / 'skills/gsd-path/templates/task.md')
            self.assertIn('1. First outcome.', brief)
            self.assertIn('Keep the wire format.', brief)
            self.assertNotIn('2. Other outcome.', brief)
            self.assertIn('Mode: owned-criteria', brief)

    def test_cli_preserves_global_rules_and_only_projects_owned_criteria(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            intent = repo / '.project/intent/INTENT.md'
            intent.parent.mkdir(parents=True)
            task = repo / 'T001.md'
            task.write_bytes('# Task\n\n## Intent coverage\n\n- SC2\n'.encode("utf-8"))
            prefix = '# Intent\n\n## Summary\n\nKeep existing callers working.\n\n'
            suffix = ('## Scope: out (vetoes)\n\nNever publish customer data.\n\n'
                      '## Constraints\n\nUse the standard library.\n\n'
                      '## Corrections\n\nKeep compatibility.\n\n'
                      '## Owner extension\n\nPreserve this unknown section verbatim.\n')
            criteria = '## Success criteria\n\n1. Unrelated export works.\n2. Assigned command works.\n   Preserve multiline detail.\n\n'
            original = prefix + criteria + suffix
            intent.write_bytes(original.encode("utf-8"))
            command = [sys.executable, '-B', str(ROOT / 'scripts/task_context.py'),
                       '--repo', str(repo), '--task', str(task)]
            result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(prefix, result.stdout)
            self.assertIn(suffix, result.stdout)
            self.assertIn('2. Assigned command works.\n   Preserve multiline detail.', result.stdout)
            self.assertNotIn('1. Unrelated export works.', result.stdout)
            self.assertIn(hashlib.sha256(original.encode()).hexdigest(), result.stdout)
            self.assertIn(str(intent.resolve()), result.stdout)  # the CLI prints resolved paths
            self.assertIn('Mode: owned-criteria', result.stdout)
            self.assertEqual(intent.read_text(encoding="utf-8"), original)

            # Bundled commands must work outside the source repository, too.
            for skill in ('gsd-path', 'gsd-path-build', 'path'):
                bundled = command.copy()
                bundled[2] = str(ROOT / 'skills' / skill / 'scripts/task_context.py')
                installed = subprocess.run(bundled, cwd=repo, capture_output=True, encoding="utf-8", errors="replace")
                self.assertEqual(installed.returncode, 0, installed.stderr)
                self.assertEqual(installed.stdout, result.stdout)

            intent.write_bytes(original.replace('Keep compatibility.', 'Keep SC1 unchanged.').encode("utf-8"))
            result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('1. Unrelated export works.', result.stdout)

            # Unstructured text could carry a constraint: retain the complete input.
            ambiguous = original.replace('1. Unrelated', 'Never remove any command.\n1. Unrelated')
            intent.write_bytes(ambiguous.encode("utf-8"))
            result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Mode: full-intent', result.stdout)
            self.assertIn(ambiguous, result.stdout)

            # Provenance hashes use normalized text (CRLF on disk becomes LF before hash).
            windows_source = original.replace('\n', '\r\n').encode()
            intent.write_bytes(windows_source)
            result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(hashlib.sha256(original.encode()).hexdigest(), result.stdout)

            task.write_bytes('## Intent coverage\n\n- SC99\n'.encode("utf-8"))
            result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('SC99', result.stderr)
            self.assertEqual(result.stdout, '')

    def test_crlf_intent_is_normalized_without_stray_carriage_returns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            intent = repo / ".project/intent/INTENT.md"
            intent.parent.mkdir(parents=True)
            intent.write_bytes(b"## Success criteria\r\n\r\n1. First.\r\n2. Second.\r\n")
            task = repo / "T001.md"
            task.write_bytes(b"## Intent coverage\n\n- SC1\n")
            command = [
                sys.executable,
                "-B",
                str(ROOT / "scripts/task_context.py"),
                "--repo",
                str(repo),
                "--task",
                str(task),
            ]
            result = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("\r", result.stdout)
            self.assertIn("1. First.", result.stdout)


    def test_probe_tables_name_every_criterion_without_selecting_them(self):
        criteria = ('## Success criteria\n\n1. First outcome text.\n'
                    '2. Second outcome text.\n3. Third outcome text.\n\n')

        def edges(sc1_disposition):
            return ('## Edge coverage\n\n'
                    '| Edge | Criterion | Category | Disposition | Detail |\n'
                    '|------|-----------|----------|-------------|--------|\n'
                    f'| E1 | SC1 | boundary | {sc1_disposition} | stated there |\n'
                    '| E2 | SC2 | none | dismissed | static |\n'
                    '| E3 | SC3 | none | dismissed | static |\n')

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            intent = repo / '.project/intent/INTENT.md'
            intent.parent.mkdir(parents=True)
            task = repo / 'T001.md'
            task.write_bytes('## Intent coverage\n\n- SC1\n'.encode('utf-8'))

            intent.write_bytes(('# Intent\n\n' + criteria + edges('dismissed')).encode('utf-8'))
            rendered = task_context.render(repo, task)
            self.assertIn('Mode: owned-criteria', rendered)
            self.assertIn('1. First outcome text.', rendered)
            self.assertNotIn('2. Second outcome text.', rendered)
            self.assertNotIn('3. Third outcome text.', rendered)

            intent.write_bytes(('# Intent\n\n' + criteria + edges('criterion SC3')).encode('utf-8'))
            rendered = task_context.render(repo, task)
            self.assertIn('Mode: owned-criteria', rendered)
            self.assertIn('1. First outcome text.', rendered)
            self.assertIn('3. Third outcome text.', rendered)
            self.assertNotIn('2. Second outcome text.', rendered)


if __name__ == '__main__':
    unittest.main()
