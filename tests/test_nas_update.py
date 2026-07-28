"""deploy/nas-update.sh, driven against a stubbed docker.

The script deletes images. It runs on a host with 60+ containers belonging to
other people, so the interesting assertions are not "did it prune" but "did it
refuse to touch anything that is not ours, and did it keep a rollback".

Until now this script had no test at all — the one recorded exercise against a
stubbed docker was ad hoc and never landed. Every deploy of the bot goes
through it.

The stub records each invocation verbatim, so the tests assert on the argv the
script actually produced rather than on its printed summary, which is the same
distinction the script itself draws about compose's exit code.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "nas-update.sh"
SHELL = shutil.which("sh") or shutil.which("bash")

pytestmark = pytest.mark.skipif(
    SHELL is None, reason="no POSIX shell available to run the deploy script"
)

IMAGE_REPO = "ghcr.io/example/gudbus"
RUNNING_IMG = "sha256:aaaa000000000000000000000000000000000000000000000000000000000000"
PREV_IMG = "sha256:bbbb111111111111111111111111111111111111111111111111111111111111"
OLD_IMG = "sha256:cccc222222222222222222222222222222222222222222222222222222222222"
OLDER_IMG = "sha256:dddd333333333333333333333333333333333333333333333333333333333333"

# Newest first, exactly as `docker images` orders them.
ALL_IMAGES = [RUNNING_IMG, PREV_IMG, OLD_IMG, OLDER_IMG]

STUB = r"""#!/bin/sh
# Stub docker. Logs argv one line per call, answers the queries the script makes.
printf '%s\n' "$*" >> "$DOCKER_LOG"

case "$1" in
  compose)
    case "$2" in
      version)  exit 0 ;;
      config)   printf 'gudbus\n'; exit 0 ;;
      # Model the recreate: from here on the container is a new one running the
      # new tag. Without this the script's own id-changed check correctly
      # refuses, and the prune is never reached.
      up)       : > "$DOCKER_LOG.recreated"; exit 0 ;;
    esac
    exit 0
    ;;
  inspect)
    if [ -f "$DOCKER_LOG.recreated" ]; then
      _id=id-after; _img="$STUB_IMAGE_REPO:$STUB_NEW_TAG"
    else
      _id=id-before; _img="$STUB_CURRENT_IMAGE"
    fi
    case "$3" in
      '{{.Config.Image}}')  printf '%s\n' "$_img" ;;
      '{{.Id}}')            printf '%s\n' "$_id" ;;
      '{{.Image}}')
        # Called two ways: for our container by name, and for every container
        # id at once when collecting in-use images.
        if [ "$4" = "$STUB_CONTAINER_NAME" ]; then
          printf '%s\n' "$STUB_RUNNING_IMAGE"
        else
          printf '%s\n' $STUB_IN_USE_IMAGES
        fi
        ;;
      '{{.State.Running}}') printf 'true\n' ;;
      *compose.project*)    printf '%s\n' "$STUB_COMPOSE_PROJECT" ;;
      *compose.service*)    printf '%s\n' "$STUB_COMPOSE_SERVICE" ;;
      *unraid*)             printf '%s\n' "$STUB_UNRAID_MANAGED" ;;
      *)                    printf '\n' ;;
    esac
    exit 0
    ;;
  images)
    # Only answer when scoped to the repo under test; an unscoped listing
    # would be the bug these tests exist to catch.
    case "$*" in
      *"reference=$STUB_IMAGE_REPO"*) printf '%s\n' $STUB_IMAGE_IDS; exit 0 ;;
      *) printf 'STUB-REFUSED-UNSCOPED-LISTING\n' >&2; exit 1 ;;
    esac
    ;;
  ps)   printf '%s\n' $STUB_ALL_CONTAINERS; exit 0 ;;
  rmi)  exit "${STUB_RMI_RC:-0}" ;;
  exec) exit 0 ;;
esac
exit 0
"""


@pytest.fixture
def env(tmp_path):
    """A fake host: stub docker on PATH plus a compose project directory."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(STUB, encoding="utf-8", newline="\n")
    docker.chmod(0o755)

    project = tmp_path / "GUDBUS"
    project.mkdir()
    (project / "docker-compose.yml").write_text(
        f"services:\n  gudbus:\n    image: {IMAGE_REPO}:sha-old\n",
        encoding="utf-8",
        newline="\n",
    )
    (project / "name").write_text("gudbus", encoding="utf-8", newline="\n")

    log = tmp_path / "docker.log"
    log.write_text("", encoding="utf-8")

    return {
        "PATH": f"{bin_dir}{';' if ';' in '' else ':'}",
        "tmp_path": tmp_path,
        "project": project,
        "log": log,
        "bin": bin_dir,
    }


def run(env, *args, **overrides):
    """Invoke the script with the stub on PATH; return (result, docker calls)."""
    import os

    e = dict(os.environ)
    e["PATH"] = str(env["bin"]) + os.pathsep + e["PATH"]
    e.update(
        {
            "DOCKER_LOG": str(env["log"]),
            "GUDBUS_PROJECT_DIR": str(env["project"]),
            "GUDBUS_CONTAINER": "gudbus",
            "GUDBUS_IMAGE_REPO": IMAGE_REPO,
            # No network in tests; the CI gate has its own coverage.
            "GUDBUS_SKIP_CI_CHECK": "1",
            "GUDBUS_SKIP_BACKUP": "1",
            "STUB_IMAGE_REPO": IMAGE_REPO,
            "STUB_IMAGE_IDS": " ".join(ALL_IMAGES),
            "STUB_CURRENT_IMAGE": f"{IMAGE_REPO}:sha-old",
            "STUB_RUNNING_IMAGE": RUNNING_IMG,
            "STUB_NEW_TAG": "sha-new",
            "STUB_CONTAINER_NAME": "gudbus",
            # Compose-managed by default; the template tests blank these.
            "STUB_COMPOSE_PROJECT": "gudbus",
            "STUB_COMPOSE_SERVICE": "gudbus",
            "STUB_UNRAID_MANAGED": "",
            # By default only our own container exists on the host.
            "STUB_ALL_CONTAINERS": "c-prod",
            "STUB_IN_USE_IMAGES": RUNNING_IMG,
        }
    )
    e.update(overrides)
    result = subprocess.run(
        [SHELL, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=e,
        cwd=str(env["tmp_path"]),
    )
    calls = [c for c in env["log"].read_text(encoding="utf-8").splitlines() if c]
    return result, calls


def _rmi_targets(calls):
    return [c.split()[1] for c in calls if c.startswith("rmi ")]


class TestPruneSafety:
    """What the prune must never do, on a host full of other people's images."""

    def test_only_ever_lists_our_own_repo(self, env):
        # The stub hard-fails an unscoped `docker images`, so a missing
        # reference filter shows up as a failure rather than as a silent
        # superset of someone else's images.
        result, calls = run(env, "--dry-run", "sha-new")
        assert "STUB-REFUSED-UNSCOPED-LISTING" not in result.stderr
        listings = [c for c in calls if c.startswith("images ")]
        assert listings, "never listed images at all"
        for c in listings:
            assert f"reference={IMAGE_REPO}" in c

    def test_never_removes_the_running_image(self, env):
        _, calls = run(env, "sha-new")
        assert RUNNING_IMG not in _rmi_targets(calls)

    def test_never_removes_the_running_image_when_it_is_not_the_newest(self, env):
        """The case that actually discriminates.

        With the running image newest, it survives whether or not the skip
        exists — the keep window covers it either way, so that test passes
        against a build with the skip deleted. Mutation testing caught it.
        Here the running image sits third, which is the real situation after a
        rollback, and only the explicit skip saves it.
        """
        order = " ".join([OLD_IMG, PREV_IMG, RUNNING_IMG, OLDER_IMG])
        _, calls = run(env, "sha-new", STUB_IMAGE_IDS=order)
        assert RUNNING_IMG not in _rmi_targets(calls)

    def test_keeps_one_previous_image_for_rollback(self, env):
        _, calls = run(env, "sha-new")
        assert PREV_IMG not in _rmi_targets(calls), (
            "pruned the rollback target; a bad deploy would then need the "
            "network to get back"
        )

    def test_removes_the_ones_past_the_keep_window(self, env):
        _, calls = run(env, "sha-new")
        assert set(_rmi_targets(calls)) == {OLD_IMG, OLDER_IMG}

    def test_never_forces_removal(self, env):
        # -f would tear an image out from under a container still using it.
        _, calls = run(env, "sha-new")
        assert not [c for c in calls if c.startswith("rmi ") and " -f" in c]

    def test_never_removes_an_image_another_container_is_using(self, env):
        """The dev instance runs :nightly from this same repo.

        Both instances' images show up in one `docker images` listing, so a
        production deploy would otherwise treat the dev container's image as a
        deletion candidate. `docker rmi` would refuse it, but that makes the
        protection an accident of an error path rather than a decision.
        """
        _, calls = run(
            env,
            "sha-new",
            STUB_ALL_CONTAINERS="c-prod c-dev",
            STUB_IN_USE_IMAGES=f"{RUNNING_IMG} {OLD_IMG}",
        )
        assert OLD_IMG not in _rmi_targets(calls)

    def test_an_in_use_image_does_not_consume_the_rollback_slot(self, env):
        """It is spoken for, not spare capacity.

        If it counted as the kept image, the genuine rollback target would be
        deleted instead — the failure would be invisible until a rollback.
        """
        _, calls = run(
            env,
            "sha-new",
            STUB_ALL_CONTAINERS="c-prod c-dev",
            STUB_IN_USE_IMAGES=f"{RUNNING_IMG} {PREV_IMG}",
        )
        assert PREV_IMG not in _rmi_targets(calls)
        assert OLD_IMG not in _rmi_targets(calls), (
            "the in-use image ate the keep slot, so the real rollback target "
            "was pruned"
        )
        assert OLDER_IMG in _rmi_targets(calls)

    def test_an_image_still_in_use_is_reported_not_fatal(self, env):
        result, _ = run(env, "sha-new", STUB_RMI_RC="1")
        assert result.returncode == 0, "a refused rmi must not fail the deploy"
        assert "in use, kept" in result.stdout


class TestPruneWindow:
    def test_keep_count_is_configurable(self, env):
        _, calls = run(env, "sha-new", GUDBUS_KEEP_IMAGES="2")
        assert set(_rmi_targets(calls)) == {OLDER_IMG}

    def test_keeping_everything_removes_nothing(self, env):
        _, calls = run(env, "sha-new", GUDBUS_KEEP_IMAGES="99")
        assert _rmi_targets(calls) == []

    def test_no_prune_flag_disables_it(self, env):
        result, calls = run(env, "--no-prune", "sha-new")
        assert _rmi_targets(calls) == []
        assert "Old images" not in result.stdout


class TestDryRun:
    def test_dry_run_removes_nothing(self, env):
        result, calls = run(env, "--dry-run", "sha-new")
        assert result.returncode == 0
        assert _rmi_targets(calls) == []
        assert "Nothing was modified" in result.stdout

    def test_dry_run_names_what_it_would_remove(self, env):
        result, _ = run(env, "--dry-run", "sha-new")
        # Short ids, as printed
        assert OLD_IMG[7:19] in result.stdout
        assert OLDER_IMG[7:19] in result.stdout
        assert "would rm" in result.stdout

    def test_dry_run_still_marks_the_rollback_and_running_images(self, env):
        result, _ = run(env, "--dry-run", "sha-new")
        assert "running" in result.stdout
        assert "rollback" in result.stdout

    def test_flags_compose_in_either_order(self, env):
        a, _ = run(env, "--dry-run", "--no-prune", "sha-new")
        b, _ = run(env, "--no-prune", "--dry-run", "sha-new")
        assert a.returncode == 0 and b.returncode == 0
        assert "Old images" not in a.stdout and "Old images" not in b.stdout


TEMPLATE = {
    "STUB_COMPOSE_PROJECT": "",
    "STUB_COMPOSE_SERVICE": "",
    "STUB_UNRAID_MANAGED": "dockerman",
}


class TestTemplateManagedContainer:
    """Production moved to an unRAID Docker template on 2026-07-28.

    Such a container has no `com.docker.compose.*` labels and no compose file,
    so the recreate path cannot drive it — and must not pretend to. What was
    actually lost was the checking around the update, not the update, so
    `--preflight` restores the checks and stops.
    """

    def test_it_refuses_to_recreate_a_label_less_container(self, env):
        result, calls = run(env, "sha-new", **TEMPLATE)
        assert result.returncode != 0
        assert "compose up" not in " ".join(calls)
        assert "--preflight" in result.stdout + result.stderr, (
            "refusing is right, but it should name the mode that does work"
        )

    def test_preflight_accepts_it_and_reports_how_it_is_managed(self, env):
        result, _ = run(env, "--preflight", "sha-new", **TEMPLATE)
        assert result.returncode == 0
        assert "unRAID Docker template" in result.stdout

    def test_preflight_still_reports_compose_when_that_is_the_truth(self, env):
        result, _ = run(env, "--preflight", "sha-new")
        assert result.returncode == 0
        assert "Compose" in result.stdout

    def test_preflight_modifies_nothing(self, env):
        """The whole basis for shipping this untested against the real box."""
        result, calls = run(env, "--preflight", "sha-new", **TEMPLATE)
        assert result.returncode == 0
        for forbidden in ("compose up", "rmi ", "compose down", "stop ", "rm "):
            assert not [c for c in calls if c.startswith(forbidden)], (
                f"preflight ran a mutating command: {forbidden}"
            )

    def test_preflight_does_not_error_when_already_on_the_target(self, env):
        """Run after updating, to confirm the box is where you think it is."""
        result, _ = run(
            env, "--preflight", "sha-old", **TEMPLATE
        )  # stub's current image is :sha-old
        assert result.returncode == 0
        assert "Already running" in result.stdout

    def test_preflight_tells_you_how_to_verify_afterwards(self, env):
        result, _ = run(env, "--preflight", "sha-new", **TEMPLATE)
        assert "image.revision" in result.stdout, (
            "should point at the running artifact, not the template form"
        )


class TestOrdering:
    def test_prune_happens_after_the_recreate(self, env):
        """A prune before verification could delete the rollback target."""
        _, calls = run(env, "sha-new")
        up = next(i for i, c in enumerate(calls) if c.startswith("compose up"))
        first_rmi = next(i for i, c in enumerate(calls) if c.startswith("rmi "))
        assert up < first_rmi
