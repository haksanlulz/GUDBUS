"""Structural assertions on the GitHub Actions workflows.

On 2026-07-27 a commit with a red test matrix published a pullable image and
was nearly deployed, because `docker-publish.yml` and `tests.yml` fired
independently on the same push. The fix was one `needs:` line. Nothing in the
repo would have noticed it being removed again — `deploy/nas-update.sh` says
as much in its own comment, and keeps a second CI check for that reason.

These read the workflows as YAML rather than grepping them, so a re-indent or
a reordered key does not quietly stop asserting anything.

The gate itself was proven to refuse by dispatching the publish workflow at a
branch carrying a planted failure: both matrix legs failed, `build-and-push`
was skipped, and no `sha-` tag appeared in the registry for that commit. These
tests are what keep that true.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"

# Branches that both run tests and publish an image. `main` is the release
# channel and the only branch `:latest` follows; `dev` is trunk, and publishes
# the nightly channel. Adding a branch here is a deliberate act.
PUBLISHING_BRANCHES = {"main", "dev"}

# What DEPLOY.md tells people they can deploy on. Kept here so the promise and
# the build are asserted against one another rather than drifting apart, which
# is how the published index spent months carrying amd64 alone under a
# "multi-arch" heading.
DOCUMENTED_ARCHITECTURES = {"linux/amd64", "linux/arm64"}


def _load(name):
    with (WORKFLOWS / name).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def publish():
    return _load("docker-publish.yml")


@pytest.fixture(scope="module")
def tests_wf():
    return _load("tests.yml")


def _triggers(workflow):
    # `on` is truthy YAML 1.1: an unquoted `on:` key parses as the boolean True.
    return workflow.get("on", workflow.get(True))


class TestPublishGate:
    """The publish job must not be able to run without the suite passing."""

    def test_build_job_needs_the_test_job(self, publish):
        needs = publish["jobs"]["build-and-push"]["needs"]
        needs = [needs] if isinstance(needs, str) else needs
        assert "test" in needs, (
            "build-and-push must declare `needs: test`. Without it both "
            "workflows fire independently and a red commit still publishes."
        )

    def test_the_gating_job_runs_the_real_suite(self, publish):
        # A gate that calls something other than the Tests workflow is a gate
        # against a different question than the one anyone is asking.
        assert publish["jobs"]["test"]["uses"] == "./.github/workflows/tests.yml"

    def test_tests_workflow_is_callable(self, tests_wf):
        # If tests.yml stops accepting workflow_call, the gate job cannot run
        # at all — which fails closed, but loudly and confusingly.
        assert "workflow_call" in _triggers(tests_wf)

    def test_no_other_job_pushes_without_the_gate(self, publish):
        # Guards the shape rather than today's job list: any future job holding
        # registry credentials has to sit behind the same gate.
        for name, job in publish["jobs"].items():
            if name == "test":
                continue
            packages = (job.get("permissions") or {}).get("packages")
            if packages == "write":
                needs = job.get("needs") or []
                needs = [needs] if isinstance(needs, str) else needs
                assert "test" in needs, (
                    f"job {name!r} can push to the registry but does not "
                    "depend on the test gate"
                )


class TestChannels:
    """`:latest` is the release pointer. Trunk must not be able to move it."""

    def test_latest_is_gated_on_the_default_branch(self, publish):
        tags = publish["jobs"]["build-and-push"]["steps"]
        meta = next(s for s in tags if s.get("id") == "meta")
        raw_latest = [
            line
            for line in meta["with"]["tags"].splitlines()
            if "value=latest" in line
        ]
        assert raw_latest, "no `latest` tag rule found"
        assert all(
            "is_default_branch" in line for line in raw_latest
        ), "`latest` must be gated on is_default_branch, or a dev push moves it"

    def test_dev_publishes_a_nightly_pointer(self, publish):
        meta = next(
            s
            for s in publish["jobs"]["build-and-push"]["steps"]
            if s.get("id") == "meta"
        )
        assert "value=nightly" in meta["with"]["tags"], (
            "dev should publish a stable `nightly` tag; without one the only "
            "way to pull trunk is to look up a sha by hand"
        )

    @pytest.mark.parametrize("workflow", ["tests.yml", "docker-publish.yml"])
    def test_both_branches_are_wired(self, workflow):
        branches = set(_triggers(_load(workflow))["push"]["branches"])
        assert branches == PUBLISHING_BRANCHES, (
            f"{workflow} pushes on {sorted(branches)}; expected "
            f"{sorted(PUBLISHING_BRANCHES)}. dev is trunk — if it does not "
            "run tests, the split hides breakage instead of isolating it."
        )


class TestArchitectures:
    """DEPLOY.md offers ARM hosts. The workflow has to actually build for them.

    For months it did not: no `platforms:` meant the runner's architecture and
    nothing else, so the published index was amd64-only while the docs
    recommended Oracle A1 and Raspberry Pi. Nothing connected the promise to
    the build, so nothing noticed. This is that connection.
    """

    def _platforms(self, publish):
        step = next(
            s
            for s in publish["jobs"]["build-and-push"]["steps"]
            if str(s.get("uses", "")).startswith("docker/build-push-action")
        )
        return " ".join(step["with"]["platforms"].split())

    def test_releases_publish_every_documented_architecture(self, publish):
        # The value is a ref-conditional expression, so this asserts the arches
        # it can select rather than a flat list. Both documented platforms have
        # to appear together in the release branch of that expression.
        expr = self._platforms(publish)
        release_arm = "'linux/amd64,linux/arm64'"
        assert release_arm in expr, (
            f"release build does not select {sorted(DOCUMENTED_ARCHITECTURES)}; "
            f"platforms reads: {expr}"
        )
        for platform in DOCUMENTED_ARCHITECTURES:
            assert platform in expr, f"{platform} is never built"

    def test_the_multi_arch_leg_is_gated_on_release_refs(self, publish):
        """Trunk must not pay for an architecture nobody pulls from it."""
        expr = self._platforms(publish)
        assert "refs/heads/main" in expr and "refs/tags/v" in expr, (
            "the multi-arch leg should be selected by release refs (main and "
            f"version tags); platforms reads: {expr}"
        )
        assert "'linux/amd64'" in expr, "no single-arch fallback for trunk"

    def test_deploy_doc_names_the_same_architectures(self):
        # Reads the doc, not a copy of it — a table edited to drop arm64 fails
        # here rather than silently disagreeing with the workflow.
        doc = (WORKFLOWS.parent.parent / "DEPLOY.md").read_text(encoding="utf-8")
        for platform in DOCUMENTED_ARCHITECTURES:
            arch = platform.split("/")[1]
            assert arch in doc, f"DEPLOY.md never mentions {arch}"

    def test_cross_build_emulation_is_set_up(self, publish):
        # arm64 on an amd64 runner needs QEMU registered before buildx runs.
        # Without it the arm64 leg fails; the failure is loud, but the job
        # ordering is the thing that is easy to break in a reshuffle.
        names = [
            str(s.get("uses", "")) for s in publish["jobs"]["build-and-push"]["steps"]
        ]
        qemu = next(i for i, u in enumerate(names) if "setup-qemu-action" in u)
        buildx = next(i for i, u in enumerate(names) if "setup-buildx-action" in u)
        assert qemu < buildx, "QEMU must be set up before buildx"
