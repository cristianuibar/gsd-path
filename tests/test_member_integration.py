import unittest
from pathlib import Path

from scripts import integration, members
from scripts.archive_milestone import ArchiveError
import tests.test_member_project_verify as member_verify

git = member_verify.git
ARCHIVE = ".project/archive/001-demo"
SUBJECT = "integrate: demo M001 — merge gsd-path/demo-M001 into main"
TAG = "milestone/demo-001-demo"


class MemberIntegrationTests(unittest.TestCase):
    fixture = member_verify.MemberProjectVerifyTests.fixture

    def setUp(self) -> None:
        member_verify.MemberProjectVerifyTests.setUp(self)
        # The member keeps its GitHub origin URL; Git rewrites it to a local bare remote.
        self.remote = self.root.parent / "web-remote.git"
        git(self.root.parent, "init", "-q", "--bare", str(self.remote))
        git(self.member, "config", "url." + str(self.remote) + ".insteadOf", "https://github.com/acme/web.git")
        git(self.member, "push", "-q", "origin", "main")
        git(self.member, "fetch", "-q", "origin")
        self.main = git(self.member, "rev-parse", "main")

    def remote_ref(self, ref: str) -> str:
        return git(self.remote, "rev-parse", "--verify", "--quiet", ref, check=False)

    def integrate(self) -> dict:
        return integration.integrate_member(self.root, "web", ARCHIVE, self.member_tip)

    def test_direct_member_integration_publishes_bound_branch_merge_and_tag(self) -> None:
        result = self.integrate()
        merge = self.remote_ref("refs/heads/main")
        self.assertEqual(result["merge"], merge)
        self.assertEqual(git(self.remote, "rev-list", "--parents", "-n", "1", merge).split()[1:],
                         [self.main, self.member_tip])
        self.assertEqual(git(self.remote, "show", "-s", "--format=%s", merge), SUBJECT)
        self.assertEqual(git(self.remote, "show", "-s", "--format=%b", merge).strip(),
                         f"Archive: {ARCHIVE}\nMember: web\nReviewed-HEAD: {self.member_tip}")
        self.assertEqual(self.remote_ref("refs/heads/gsd-path/demo-M001"), self.member_tip)
        self.assertEqual(git(self.remote, "cat-file", "-t", f"refs/tags/{TAG}"), "tag")
        self.assertEqual(self.remote_ref(f"refs/tags/{TAG}^{{commit}}"), merge)
        self.assertEqual(result["tag"], TAG)
        tag_object = self.remote_ref(f"refs/tags/{TAG}")
        for ref, sha in (("refs/heads/gsd-path/demo-M001", self.member_tip),
                         ("refs/heads/main", merge), (f"refs/tags/{TAG}", tag_object)):
            self.assertTrue(members.authorized(self.member, "demo", "push", ref, sha), ref)
        self.assertEqual(git(self.member, "branch", "--list", "gsd-path-integrate/*"), "")
        self.assertEqual(git(self.member, "worktree", "list", "--porcelain").count("worktree "), 1)

    def test_rerun_never_integrates_a_member_twice(self) -> None:
        first = self.integrate()
        second = self.integrate()
        self.assertEqual(second["merge"], first["merge"])
        self.assertEqual(self.remote_ref("refs/heads/main"), first["merge"])

    def test_resume_publishes_only_the_missing_tag(self) -> None:
        first = self.integrate()
        git(self.remote, "tag", "-d", TAG)
        git(self.member, "tag", "-d", TAG)
        result = self.integrate()
        self.assertEqual(result["merge"], first["merge"])
        self.assertEqual(self.remote_ref("refs/heads/main"), first["merge"])
        self.assertEqual(self.remote_ref(f"refs/tags/{TAG}^{{commit}}"), first["merge"])

    def test_moved_bound_branch_is_refused_before_publishing(self) -> None:
        with self.assertRaisesRegex(ArchiveError, "gsd-path/demo-M001"):
            integration.integrate_member(self.root, "web", ARCHIVE, self.main)
        self.assertEqual(self.remote_ref("refs/heads/main"), self.main)
        self.assertEqual(self.remote_ref("refs/heads/gsd-path/demo-M001"), "")

    def test_moved_remote_bound_branch_blocks(self) -> None:
        git(self.member, "push", "-q", "origin", "main:refs/heads/gsd-path/demo-M001")
        with self.assertRaisesRegex(ArchiveError, "moved"):
            self.integrate()
        self.assertEqual(self.remote_ref("refs/heads/main"), self.main)

    def test_stale_unpublished_merge_is_rebuilt_on_the_advanced_main(self) -> None:
        stale = self.root.parent / "stale"
        git(self.member, "worktree", "add", "-q", "-b", "gsd-path-integrate/demo-M001", str(stale), self.main)
        git(stale, "merge", "-q", "--no-ff", "-m", SUBJECT, "-m",
            f"Archive: {ARCHIVE}\nMember: web\nReviewed-HEAD: {self.member_tip}", self.member_tip)
        stale_merge = git(stale, "rev-parse", "HEAD")
        git(self.member, "worktree", "remove", str(stale))
        other = self.root.parent / "other"
        git(self.root.parent, "clone", "-q", str(self.remote), str(other))
        (other / "team.txt").write_text("team work\n", encoding="utf-8")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "team work")
        git(other, "push", "-q", "origin", "main")
        advanced = git(other, "rev-parse", "HEAD")
        result = self.integrate()
        self.assertNotEqual(result["merge"], stale_merge)
        self.assertEqual(git(self.remote, "rev-list", "--parents", "-n", "1", result["merge"]).split()[1:],
                         [advanced, self.member_tip])

    def test_validate_requires_the_published_merge_and_tag(self) -> None:
        with self.assertRaisesRegex(ArchiveError, "integrate: demo M001"):
            integration.validate_member_integrated(self.root, "web", ARCHIVE, self.member_tip)
        result = self.integrate()
        self.assertEqual(integration.validate_member_integrated(self.root, "web", ARCHIVE, self.member_tip),
                         result)
        git(self.remote, "tag", "-f", "-a", "-m", "wrong", TAG, self.main)
        with self.assertRaisesRegex(ArchiveError, "integration merge"):
            integration.validate_member_integrated(self.root, "web", ARCHIVE, self.member_tip)
        git(self.remote, "tag", "-d", TAG)
        with self.assertRaisesRegex(ArchiveError, TAG):
            integration.validate_member_integrated(self.root, "web", ARCHIVE, self.member_tip)


if __name__ == "__main__":
    unittest.main()
