import unittest
from unittest import mock

import tests.test_member_landing as landing
from scripts import pipeline_undo

git = landing.git


class MemberUndoTests(unittest.TestCase):
    setUp = landing.MemberLandingTests.setUp
    tearDown = landing.MemberLandingTests.tearDown
    land = landing.MemberLandingTests.land
    edit = landing.MemberLandingTests.edit
    bound_tip = landing.MemberLandingTests.bound_tip

    def landed(self) -> dict:
        self.edit()
        return self.land()

    def test_member_record_undo_resets_the_member_landing_then_the_record(self) -> None:
        result = self.landed()
        target = pipeline_undo.preview(self.coordinator)["target"]
        self.assertEqual((target["kind"], target["member"], target["landing"]),
                         ("member-task", "web", result["landing"]))
        pipeline_undo.apply_undo(self.coordinator, "member-task", result["commit"])
        self.assertEqual(git(self.coordinator, "rev-parse", "HEAD"), self.base)
        self.assertEqual(self.bound_tip(), self.member_base)
        self.assertEqual(git(self.bound, "status", "--porcelain"), "")

    def test_interrupted_member_undo_resumes_after_the_member_reset(self) -> None:
        result = self.landed()
        with mock.patch.object(pipeline_undo, "_reset_to", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                pipeline_undo.apply_undo(self.coordinator, "member-task", result["commit"])
        self.assertEqual(self.bound_tip(), self.member_base)
        self.assertEqual(git(self.coordinator, "rev-parse", "HEAD"), result["commit"])
        pipeline_undo.apply_undo(self.coordinator, "member-task", result["commit"])
        self.assertEqual(git(self.coordinator, "rev-parse", "HEAD"), self.base)

    def test_member_landing_on_origin_main_is_not_undone(self) -> None:
        result = self.landed()
        git(self.member, "update-ref", "refs/remotes/origin/main", result["landing"])
        target = pipeline_undo.preview(self.coordinator)["target"]
        self.assertIsNone(target["kind"])
        self.assertRegex(" ".join(target["blocked"]), "origin/main")
        self.assertEqual(self.bound_tip(), result["landing"])

    def test_member_bound_branch_moved_past_the_landing_blocks(self) -> None:
        result = self.landed()
        (self.bound / "extra.txt").write_text("x\n", encoding="utf-8")
        git(self.bound, "add", "-A")
        git(self.bound, "commit", "-q", "--no-verify", "-m", "extra")
        tip = self.bound_tip()
        target = pipeline_undo.preview(self.coordinator)["target"]
        self.assertIsNone(target["kind"])
        self.assertRegex(" ".join(target["blocked"]), "moved")
        self.assertEqual(self.bound_tip(), tip)


if __name__ == "__main__":
    unittest.main()
