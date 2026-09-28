import json
import shutil
import unittest
from pathlib import Path

from scripts import archive_milestone, discussion_validate, lean_verification
from scripts import check_handoffs as contracts
import tests.test_handoffs as test_handoffs
import tests.test_member_project_verify as member_verify

git = member_verify.git


class MemberFinalReviewTests(unittest.TestCase):
    setUp = member_verify.MemberProjectVerifyTests.setUp
    fixture = member_verify.MemberProjectVerifyTests.fixture
    use_member_verify_command = member_verify.MemberProjectVerifyTests.use_member_verify_command

    def write_final(self, *member_lines: str, keep_gap: bool = False) -> Path:
        review = self.root / ".project/review"
        kept = (review / "final-gap-1.md").read_text(encoding="utf-8") if keep_gap else None
        test_handoffs.HandoffValidationTests().write_final_review(self.root)
        # The helper writes FINAL.md and a matching gap; both carry the member lines.
        for path in (review / "FINAL.md", review / "final-gap-1.md"):
            text = path.read_text(encoding="utf-8")
            end = text.index("\n", text.index("Reviewed HEAD:"))
            path.write_text(text[:end] + "".join(f"\n{line}" for line in member_lines) + text[end:],
                            encoding="utf-8")
        if kept is not None:
            (review / "final-gap-1.md").write_text(kept, encoding="utf-8")
        return review / "FINAL.md"

    def test_final_review_must_name_each_locked_member_head(self) -> None:
        self.write_final()
        with self.assertRaisesRegex(contracts.HandoffError, "Member reviewed HEAD"):
            contracts.validate_final(self.root)
        self.write_final(f"Member reviewed HEAD: web {self.member_tip}")
        self.assertEqual(contracts.validate_final(self.root)["verdict"], "pass")

    def test_stale_member_head_is_refused(self) -> None:
        self.write_final(f"Member reviewed HEAD: web {git(self.member, 'rev-parse', 'main')}")
        with self.assertRaisesRegex(contracts.HandoffError, "Member reviewed HEAD"):
            contracts.validate_final(self.root)

    def test_member_head_without_a_lock_is_refused(self) -> None:
        (self.root / ".project/build/members.json").unlink()
        self.write_final(f"Member reviewed HEAD: web {self.member_tip}")
        with self.assertRaisesRegex(contracts.HandoffError, "Member reviewed HEAD"):
            contracts.validate_final(self.root)

    def test_project_verify_gap_carries_member_heads_and_must_match_final(self) -> None:
        self.use_member_verify_command()
        self.assertTrue(lean_verification.verify_project(self.root, self.head)["passed"])
        self.write_final(f"Member reviewed HEAD: web {self.member_tip}", keep_gap=True)
        self.assertEqual(contracts.validate_final(self.root)["verdict"], "pass")
        gap = self.root / ".project/review/final-gap-1.md"
        gap.write_text(gap.read_text(encoding="utf-8").replace(
            f"Member reviewed HEAD: web {self.member_tip}\n", ""), encoding="utf-8")
        with self.assertRaisesRegex(contracts.HandoffError, "final-gap-1.md Member reviewed HEAD"):
            contracts.validate_final(self.root)

    def test_member_head_in_quoted_output_does_not_bind(self) -> None:
        final = self.write_final(f"Member reviewed HEAD: web {self.member_tip}")
        final.write_text(final.read_text(encoding="utf-8") + "\n## Output\n\nMember reviewed HEAD: api " + "0" * 40 + "\n",
                         encoding="utf-8")
        self.assertEqual(contracts.validate_final(self.root)["verdict"], "pass")

    def archive(self) -> Path:
        self.use_member_verify_command()
        self.assertTrue(lean_verification.verify_project(self.root, self.head)["passed"])
        archive = self.root / "archived"
        (archive / "build").mkdir(parents=True)
        shutil.copytree(self.root / ".project/review", archive / "review")
        shutil.copy(self.root / ".project/build/members.json", archive / "build/members.json")
        (archive / "review/FINAL.md").write_text("# Final Review\n", encoding="utf-8")
        return archive

    def test_archived_final_review_names_each_locked_member(self) -> None:
        archive = self.archive()
        with self.assertRaisesRegex(archive_milestone.ArchiveError, "Member reviewed HEAD"):
            discussion_validate.validate_gap_reviews(archive, self.head)
        final = archive / "review/FINAL.md"
        final.write_text(f"Member reviewed HEAD: web {self.member_tip}\n", encoding="utf-8")
        discussion_validate.validate_gap_reviews(archive, self.head)
        lock = archive / "build/members.json"
        lock.write_text(json.dumps({"schema": "gsd-path/member-lock/v1", "members": []}), encoding="utf-8")
        with self.assertRaisesRegex(archive_milestone.ArchiveError, "Member reviewed HEAD"):
            discussion_validate.validate_gap_reviews(archive, self.head)

    def test_archived_gap_must_repeat_final_member_heads(self) -> None:
        archive = self.archive()
        (archive / "review/FINAL.md").write_text(
            f"Member reviewed HEAD: web {self.member_tip}\n", encoding="utf-8")
        gap = archive / "review/final-gap-1.md"
        gap.write_text(gap.read_text(encoding="utf-8").replace(self.member_tip, "0" * 40), encoding="utf-8")
        with self.assertRaisesRegex(archive_milestone.ArchiveError, "final-gap-1.md Member reviewed HEAD"):
            discussion_validate.validate_gap_reviews(archive, self.head)


if __name__ == "__main__":
    unittest.main()
