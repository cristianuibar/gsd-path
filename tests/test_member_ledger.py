import json
import unittest
from pathlib import Path

import tests.test_member_landing as landing
from scripts import _common, build_state

git = landing.git
COMMAND = "test -f app.py"


class VerifyLedgerKeyTests(unittest.TestCase):
    def test_member_rows_never_answer_coordinator_lookups(self) -> None:
        coordinator = {"schema": _common.VERIFY_LEDGER_SCHEMA, "command": COMMAND, "commit": "a" * 40,
                       "result": "fail", "recorded_at": "t"}
        member = dict(coordinator, repo="web", result="pass")
        entries = [coordinator, member]
        self.assertEqual(_common.latest_verify_entry(entries, COMMAND, "a" * 40)["result"], "fail")
        self.assertEqual(_common.latest_verify_entry(entries, COMMAND, "a" * 40, "web")["result"], "pass")
        self.assertIsNone(_common.latest_verify_entry([coordinator], COMMAND, "a" * 40, "web"))

    def test_ledger_rejects_a_non_string_repo(self) -> None:
        row = {"schema": _common.VERIFY_LEDGER_SCHEMA, "command": COMMAND, "commit": "a" * 40,
               "result": "pass", "recorded_at": "t", "repo": 7}
        with self.assertRaisesRegex(ValueError, "invalid fields"):
            _common.parse_verify_ledger(json.dumps(row) + "\n")


class MemberVerifyRecordTests(unittest.TestCase):
    setUp = landing.MemberLandingTests.setUp
    tearDown = landing.MemberLandingTests.tearDown
    land = landing.MemberLandingTests.land
    edit = landing.MemberLandingTests.edit

    def test_member_verify_is_recorded_and_found_in_the_member(self) -> None:
        self.edit()
        member_commit = self.land()["landing"]
        recorded = build_state.verify_record(str(self.coordinator), COMMAND, member_commit, "pass",
                                             member="web")
        self.assertEqual(recorded["entry"]["repo"], "web")
        self.assertTrue(build_state.verify_lookup(str(self.coordinator), COMMAND, member_commit,
                                                  member="web")["reuse"])
        with self.assertRaisesRegex(build_state.BuildStateError, "existing commit"):
            build_state.verify_lookup(str(self.coordinator), COMMAND, member_commit)

    def test_coordinator_rows_stay_unchanged(self) -> None:
        head = git(self.coordinator, "rev-parse", "HEAD")
        recorded = build_state.verify_record(str(self.coordinator), COMMAND, head, "pass")
        self.assertNotIn("repo", recorded["entry"])
        with self.assertRaisesRegex(build_state.BuildStateError, "existing commit"):
            build_state.verify_lookup(str(self.coordinator), COMMAND, head, member="web")


if __name__ == "__main__":
    unittest.main()
