import json
import subprocess
import unittest
from unittest import mock

from scripts import integration, members
from scripts.archive_milestone import ArchiveError
import tests.test_member_integration as member_integration

git = member_integration.git
ARCHIVE = member_integration.ARCHIVE
SUBJECT = member_integration.SUBJECT
TAG = member_integration.TAG
URL = "https://github.com/acme/web/pull/7"


class MemberPullRequestTests(unittest.TestCase):
    fixture = member_integration.MemberIntegrationTests.fixture

    def setUp(self) -> None:
        member_integration.MemberIntegrationTests.setUp(self)
        self.pulls, self.posts = [], []

    remote_ref = member_integration.MemberIntegrationTests.remote_ref

    pulls: list
    posts: list

    def gh(self, *arguments: str) -> subprocess.CompletedProcess:
        def reply(payload) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(arguments, 0, json.dumps(payload), "")
        if arguments[:2] == ("gh", "auth"):
            return subprocess.CompletedProcess(arguments, 0, "", "")
        if "graphql" in arguments:
            merged = [pull["merge_commit_sha"] for pull in self.pulls if pull["merged_at"]]
            nodes = [{"__typename": "MergedEvent", "actor": {"__typename": "User", "login": "owner"},
                      "commit": {"oid": merged[0]}}] if merged else []
            return reply({"data": {"repository": {"pullRequest": {
                "mergeQueue": {"nodes": []}, "autoMerge": {"nodes": []}, "mergeAction": {"nodes": nodes}}}}})
        if "POST" in arguments:
            self.posts.append(arguments)
            self.pulls.append({"number": 7, "state": "open", "html_url": URL, "merged_at": None,
                               "merge_commit_sha": None, "base": {"ref": "main"},
                               "head": {"ref": "gsd-path/demo-M001", "sha": self.member_tip,
                                        "repo": {"full_name": "acme/web"}}})
            return reply(self.pulls[-1])
        return reply([self.pulls])

    def integrate(self) -> dict:
        with mock.patch.object(integration, "github_repository", return_value="acme/web"), \
                mock.patch.object(integration, "run_command", side_effect=self.gh):
            return integration.integrate_member_pull_request(self.root, "web", ARCHIVE, self.member_tip)

    def github_merge(self, *extra: str) -> str:
        """Merge the pull request on the remote the way GitHub's merge button does."""
        clone = self.root.parent / "github"
        git(self.root.parent, "clone", "-q", str(self.remote), str(clone))
        git(clone, "config", "user.name", "t")
        git(clone, "config", "user.email", "t@t")
        git(clone, "merge", "-q", *extra, "-m", "Merge pull request #7 from acme/gsd-path/demo-M001",
            "origin/gsd-path/demo-M001")
        if "--squash" in extra:
            git(clone, "commit", "-q", "-m", "Squashed pull request #7")
        git(clone, "push", "-q", "origin", "main")
        merge = git(clone, "rev-parse", "HEAD")
        self.pulls[0].update(state="closed", merged_at="2026-09-28T00:00:00Z", merge_commit_sha=merge)
        return merge

    def test_opens_one_pull_request_and_waits(self) -> None:
        result = self.integrate()
        self.assertEqual((result["status"], result["pull_request"]), ("awaiting-merge", URL))
        again = self.integrate()
        self.assertEqual(again["status"], "awaiting-merge")
        self.assertEqual(len(self.posts), 1)
        post = self.posts[0]
        self.assertIn(f"title={SUBJECT}", post)
        self.assertIn("head=gsd-path/demo-M001", post)
        self.assertIn("base=main", post)
        body = next(argument for argument in post if argument.startswith("body="))
        self.assertTrue(body.endswith(f"\n\n---\n{integration.PR_CREDIT_LINE}"))
        self.assertEqual(self.remote_ref("refs/heads/gsd-path/demo-M001"), self.member_tip)
        self.assertEqual(self.remote_ref("refs/heads/main"), self.main)
        self.assertTrue(members.authorized(self.member, "demo", "push", "refs/heads/gsd-path/demo-M001",
                                           self.member_tip))

    def test_merged_pull_request_is_tagged_and_validated(self) -> None:
        self.integrate()
        merge = self.github_merge("--no-ff")
        result = self.integrate()
        self.assertEqual(result["merge"], merge)
        self.assertEqual(self.remote_ref(f"refs/tags/{TAG}^{{commit}}"), merge)
        message = git(self.remote, "for-each-ref", "--format=%(contents)", f"refs/tags/{TAG}")
        self.assertIn("Mode: pull-request", message)
        self.assertIn(f"Pull-Request: {URL}", message)
        self.assertIn(f"Reviewed-HEAD: {self.member_tip}", message)
        self.assertTrue(members.authorized(self.member, "demo", "push", f"refs/tags/{TAG}",
                                           self.remote_ref(f"refs/tags/{TAG}")))
        self.assertEqual(integration.validate_member_integrated(self.root, "web", ARCHIVE, self.member_tip),
                         result)
        with self.assertRaisesRegex(ArchiveError, "different reviewed HEAD"):
            integration.validate_member_integrated(self.root, "web", ARCHIVE, self.main)

    def test_squash_merge_is_refused(self) -> None:
        self.integrate()
        self.github_merge("--squash")
        with self.assertRaisesRegex(ArchiveError, "two-parent"):
            self.integrate()
        self.assertEqual(self.remote_ref(f"refs/tags/{TAG}"), "")

    def test_closed_pull_request_blocks(self) -> None:
        self.integrate()
        self.pulls[0]["state"] = "closed"
        with self.assertRaisesRegex(ArchiveError, "closed without merging"):
            self.integrate()


if __name__ == "__main__":
    unittest.main()
