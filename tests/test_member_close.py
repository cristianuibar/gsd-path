import json
import re
import shutil
import unittest
from pathlib import Path
from unittest import mock

from scripts import integration, members
from scripts.archive_milestone import ArchiveError
from scripts.pipeline_git import ship_commit_body
import tests.test_member_integration as member_integration

git = member_integration.git
ARCHIVE = member_integration.ARCHIVE
TAG = member_integration.TAG


class MemberCloseTests(unittest.TestCase):
    fixture = member_integration.MemberIntegrationTests.fixture
    remote_ref = member_integration.MemberIntegrationTests.remote_ref

    def setUp(self) -> None:
        member_integration.MemberIntegrationTests.setUp(self)
        state = self.root / ".project/STATE.md"
        state.write_bytes(state.read_text(encoding="utf-8").replace("archive: null", f"archive: {ARCHIVE}").encode("utf-8"))
        archive = self.root / ARCHIVE
        (archive / "build").mkdir(parents=True)
        (archive / "review").mkdir()
        shutil.move(str(self.root / ".project/build/members.json"), archive / "build/members.json")
        self.final = archive / "review/FINAL.md"
        self.final.write_bytes(f"# Final Review\n\nReviewed HEAD: {self.head}\n"
                              f"Member reviewed HEAD: web {self.member_tip}\n".encode("utf-8"))
        self.journal = Path(git(self.root, "rev-parse", "--path-format=absolute", "--git-common-dir")) \
            / "gsd-path/member-close/001-demo.json"

    def set_integration(self, mode: str) -> None:
        listed = self.root / ".project/MEMBERS.md"
        listed.write_bytes(re.sub(r"(?m)^Integration: .*$", f"Integration: {mode}",
                                 listed.read_text(encoding="utf-8")).encode("utf-8"))

    def test_close_members_integrates_each_locked_member_and_journals_it(self) -> None:
        result = integration.close_members(self.root)
        merge = self.remote_ref("refs/heads/main")
        row = {"name": "web", "mode": "direct", "reviewed_head": self.member_tip, "status": "integrated",
               "merge": merge, "tag": TAG}
        self.assertEqual(result["status"], "integrated")
        self.assertEqual(result["members"], [row])
        self.assertEqual(json.loads(self.journal.read_text(encoding="utf-8"))["members"], [row])
        self.assertEqual(result["body"], ship_commit_body(ARCHIVE, self.head, [row]))
        self.assertTrue(result["body"].endswith(
            f"Member-Reviewed-HEAD: web@{self.member_tip}\nMember: web {merge} {TAG}\n"))

    def test_rerun_verifies_integrated_members_without_integrating_again(self) -> None:
        first = integration.close_members(self.root)
        with mock.patch.object(integration, "integrate_member", side_effect=AssertionError("integrated twice")):
            second = integration.close_members(self.root)
        self.assertEqual(second["members"], first["members"])

    def test_journal_that_disagrees_with_the_member_origin_blocks(self) -> None:
        integration.close_members(self.root)
        journal = json.loads(self.journal.read_text(encoding="utf-8"))
        journal["members"][0]["merge"] = self.main
        self.journal.write_bytes(json.dumps(journal).encode("utf-8"))
        with self.assertRaisesRegex(ArchiveError, "differs from its member-close journal"):
            integration.close_members(self.root)

    def test_member_is_journaled_pending_before_it_moves(self) -> None:
        with mock.patch.object(integration, "integrate_member", side_effect=ArchiveError("push failed")):
            with self.assertRaisesRegex(ArchiveError, "push failed"):
                integration.close_members(self.root)
        row = json.loads(self.journal.read_text(encoding="utf-8"))["members"][0]
        self.assertEqual((row["name"], row["status"], row["reviewed_head"]), ("web", "pending", self.member_tip))

    def test_pull_request_member_waits_with_a_pending_journal_row(self) -> None:
        self.set_integration("pull-request")
        waiting = {"status": "awaiting-merge", "pull_request": "https://github.com/acme/web/pull/7"}
        with mock.patch.object(integration, "integrate_member_pull_request", return_value=waiting) as opened:
            result = integration.close_members(self.root)
        opened.assert_called_once_with(self.root.resolve(), "web", ARCHIVE, self.member_tip)
        self.assertEqual((result["status"], result["member"]), ("awaiting-merge", "web"))
        row = json.loads(self.journal.read_text(encoding="utf-8"))["members"][0]
        self.assertEqual((row["status"], row["mode"], row["pull_request"]),
                         ("pending", "pull-request", waiting["pull_request"]))

    def test_default_member_follows_the_coordinator_integration(self) -> None:
        self.set_integration("default")
        state = self.root / ".project/STATE.md"
        state.write_bytes(state.read_text(encoding="utf-8").replace(
            "archive:", "integration_default: direct\nintegration: pull-request\nintegration_source: milestone\narchive:").encode("utf-8"))
        waiting = {"status": "awaiting-merge", "pull_request": "https://github.com/acme/web/pull/7"}
        with mock.patch.object(integration, "integrate_member_pull_request", return_value=waiting):
            self.assertEqual(integration.close_members(self.root)["status"], "awaiting-merge")

    def test_final_review_must_bind_every_locked_member(self) -> None:
        self.final.write_bytes(f"# Final Review\n\nReviewed HEAD: {self.head}\n".encode("utf-8"))
        with self.assertRaisesRegex(ArchiveError, "Member reviewed HEAD"):
            integration.close_members(self.root)
        self.assertEqual(self.remote_ref("refs/heads/main"), self.main)

    def test_milestone_without_members_closes_nothing(self) -> None:
        (self.root / ARCHIVE / "build/members.json").unlink()
        self.final.write_bytes(f"# Final Review\n\nReviewed HEAD: {self.head}\n".encode("utf-8"))
        result = integration.close_members(self.root)
        self.assertEqual((result["status"], result["members"]), ("integrated", []))
        self.assertEqual(result["body"], ship_commit_body(ARCHIVE, self.head))
        self.assertFalse(self.journal.exists())


if __name__ == "__main__":
    unittest.main()
