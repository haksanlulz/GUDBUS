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

CLEAN_CHECKRUNS = '{"total_count":2,"check_runs":[{"name":"pytest (3.10)","status":"completed","conclusion":"success"},{"name":"pytest (3.12)","status":"completed","conclusion":"success"}]}'
RED_CHECKRUNS = '{"total_count":2,"check_runs":[{"name":"pytest (3.10)","status":"completed","conclusion":"failure"},{"name":"pytest (3.12)","status":"completed","conclusion":"success"}]}'
RUNNING_CHECKRUNS = '{"total_count":1,"check_runs":[{"name":"pytest (3.10)","status":"in_progress","conclusion":null}]}'
QUEUED_CHECKRUNS = '{"total_count":1,"check_runs":[{"name":"pytest (3.10)","status":"queued","conclusion":null}]}'

#: `behind`/`identical` mean the commit is an ancestor of main, i.e. a release.
COMPARE_RELEASE = '{"status":"behind","ahead_by":0,"behind_by":3,"files":[]}'

#: A trunk build. The files[] entries each carry their OWN "status" key, which is
#: exactly what defeated the first version of the channel parse: a greedy match
#: took the LAST one and read a nightly as a release. Kept verbose on purpose.
COMPARE_NIGHTLY = (
    '{"status":"ahead","ahead_by":2,"behind_by":0,"files":['
    '{"filename":"a.py","status":"modified"},'
    '{"filename":"b.py","status":"added"},'
    '{"filename":"c.py","status":"renamed"}]}'
)

# Stub curl: the two GitHub API reads the CI gate makes.
#
# Bodies come from the environment so a test can hand the script a red commit,
# an in-flight one, or a comparison whose files[] array carries its own "status"
# key — that last one is the shape that broke the channel parse once and is the
# reason this stub returns raw JSON rather than a tidy summary.
#
# GUDBUS_CURL points at this file. It is NOT shadowed on PATH: Git Bash on
# Windows prepends its own bin dir ahead of the caller's, so a stub placed on
# PATH was ignored and the suite made real requests to api.github.com.
CURL_STUB = r"""#!/bin/sh
printf '%s
' "$*" >> "$CURL_LOG"
[ "${STUB_CURL_FAIL:-0}" = "1" ] && exit 22
url=""
for a in "$@"; do case "$a" in https://*) url=$a ;; esac; done
case "$url" in
  */check-runs) printf '%s
' "$STUB_CHECKRUNS"; exit 0 ;;
  */compare/*)  printf '%s
' "$STUB_COMPARE";   exit 0 ;;
esac
exit 22
"""

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
      '{{.Config.Image}}')
        # Fail for a name that is not the container that exists — this is the
        # first inspect the script makes, and it is where a wrong name (or wrong
        # case) has to surface. Without this the stub answered for any name and
        # a case-mismatch test could not fail.
        [ "$4" = "$STUB_CONTAINER_NAME" ] || exit 1
        printf '%s\n' "$_img"
        ;;
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
  ps)
    # Names when asked for names, ids otherwise: the error path lists names to
    # suggest a near-miss, while the prune collects ids.
    case "$*" in
      *'{{.Names}}'*) printf '%s\n' ${STUB_CONTAINER_NAMES:-$STUB_CONTAINER_NAME} ;;
      *)              printf '%s\n' $STUB_ALL_CONTAINERS ;;
    esac
    exit 0
    ;;
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

    curl = bin_dir / "curl"
    curl.write_text(CURL_STUB, encoding="utf-8", newline="\n")
    curl.chmod(0o755)

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
    curl_log = tmp_path / "curl.log"
    curl_log.write_text("", encoding="utf-8")

    return {
        "PATH": f"{bin_dir}{';' if ';' in '' else ':'}",
        "tmp_path": tmp_path,
        "project": project,
        "log": log,
        "curl_log": curl_log,
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
            "CURL_LOG": str(env["curl_log"]),
            # Named explicitly rather than shadowed on PATH. Git Bash on Windows
            # prepends its own bin dir ahead of whatever the caller prepended,
            # so the stub was ignored there and the suite made real requests to
            # ghcr.io — and three of these tests then passed for the wrong
            # reason, on a real curl failing rather than the stub declining.
            "GUDBUS_CURL": str(env["bin"] / "curl"),
            "GUDBUS_PROJECT_DIR": str(env["project"]),
            "GUDBUS_CONTAINER": "gudbus",
            "GUDBUS_IMAGE_REPO": IMAGE_REPO,
            # Off by default so the 30-odd prune/template tests stay focused;
            # TestCiGate turns it back on. Before 2026-07-29 nothing turned it
            # on at all, so the gate that refuses a red build was untested.
            "GUDBUS_SKIP_CI_CHECK": "1",
            "STUB_CHECKRUNS": CLEAN_CHECKRUNS,
            "STUB_COMPARE": COMPARE_RELEASE,
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
        # Decoded explicitly. `text=True` uses the locale encoding, which is
        # cp1252 under PowerShell here and UTF-8 under a POSIX shell, so the
        # script's non-ASCII warning markers came back mangled in one and not
        # the other — an assertion that holds or fails by which terminal
        # launched pytest is not an assertion.
        encoding="utf-8",
        errors="replace",
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


CI_ON = {"GUDBUS_SKIP_CI_CHECK": "0"}


class TestCiGate:
    """The script's actual safety feature, and until now the untested one.

    Every other test in this file sets GUDBUS_SKIP_CI_CHECK=1, so nothing
    exercised the check that refuses to deploy a commit whose tests are red —
    which is the whole reason the script reads the GitHub API at all. It exists
    as a belt to the publish workflow's braces: images published before that
    workflow was gated are still pullable, and a workflow edit could remove the
    gate without anything here noticing.
    """

    def test_it_refuses_a_commit_with_a_failing_check_run(self, env):
        result, calls = run(
            env, "sha-new", **CI_ON, STUB_CHECKRUNS=RED_CHECKRUNS
        )
        assert result.returncode != 0
        assert "FAILING" in result.stderr
        assert "compose up" not in " ".join(calls), "deployed a red build anyway"

    def test_it_refuses_while_ci_is_still_running(self, env):
        """Absent conclusions are not passes — that is the fail-open shape."""
        result, calls = run(
            env, "sha-new", **CI_ON, STUB_CHECKRUNS=RUNNING_CHECKRUNS
        )
        assert result.returncode != 0
        assert "still running" in result.stderr
        assert "compose up" not in " ".join(calls)

    def test_it_refuses_while_ci_is_merely_queued(self, env):
        result, _ = run(env, "sha-new", **CI_ON, STUB_CHECKRUNS=QUEUED_CHECKRUNS)
        assert result.returncode != 0

    def test_a_green_commit_passes_the_gate(self, env):
        """The other half: a gate that refuses everything is also broken."""
        result, calls = run(env, "sha-new", **CI_ON)
        assert result.returncode == 0, result.stderr
        assert "no failing check runs" in result.stdout
        assert "compose up" in " ".join(calls)

    def test_an_unreachable_api_warns_rather_than_refusing(self, env):
        """Deliberate: the box may have no egress, and a deploy blocked by a
        network hiccup is worse than one that says the status is unverified."""
        result, _ = run(env, "sha-new", **CI_ON, STUB_CURL_FAIL="1")
        assert result.returncode == 0
        assert "UNVERIFIED" in result.stdout

    def test_the_skip_flag_bypasses_it(self, env):
        result, _ = run(env, "sha-new", STUB_CHECKRUNS=RED_CHECKRUNS)
        assert result.returncode == 0, "SKIP_CI_CHECK=1 should deploy anyway"

    def test_it_reads_the_commit_out_of_the_tag(self, env):
        """`sha-` prefix stripped, or every lookup 404s and reads as unverified."""
        _, _ = run(env, "sha-abc1234", **CI_ON)
        calls = env["curl_log"].read_text(encoding="utf-8")
        assert "/commits/abc1234/check-runs" in calls
        assert "sha-abc1234/check-runs" not in calls


class TestReleaseChannel:
    """Which branch a `sha-` tag came from. Reports, never refuses.

    Both `main` and `dev` publish `sha-` tags, so the tag alone does not say
    whether you are about to put a release or a trunk build on the box.
    """

    def test_an_ancestor_of_main_reads_as_a_release(self, env):
        result, _ = run(env, "sha-new", **CI_ON, STUB_COMPARE=COMPARE_RELEASE)
        assert "RELEASE" in result.stdout

    def test_a_trunk_build_reads_as_a_nightly(self, env):
        """The regression guard for the greedy-parse bug.

        The comparison's files[] entries each carry their own "status", so a
        greedy match takes the LAST one — `"modified"` — and falls through to
        the warning branch or, worse, matches nothing and reads as a release.
        The parse is anchored on the adjacent "ahead_by" key for this reason.
        It looked correct on every release tag it was tried against, because a
        release comparison has an empty files[].
        """
        result, _ = run(env, "sha-new", **CI_ON, STUB_COMPARE=COMPARE_NIGHTLY)
        assert "NIGHTLY" in result.stdout, (
            "read a trunk build as a release; the files[] status keys won"
        )
        assert "RELEASE" not in result.stdout

    def test_an_unreadable_comparison_says_so(self, env):
        result, _ = run(env, "sha-new", **CI_ON, STUB_COMPARE='{"unexpected":true}')
        assert result.returncode == 0
        assert "could not read the channel" in result.stdout


class TestContainerName:
    """The default has to match the container that actually exists.

    Production moved from Compose (`gudbus`) to the unRAID template (`GUDBUS`)
    on 2026-07-28 and the default was not updated, so `--preflight` would have
    died on "container not found" the first time it ran. Docker names are
    case-sensitive and this one deployment spells itself five ways, so a
    near-miss has to be named rather than left in a 60-line listing.
    """

    def test_the_default_matches_the_template_container(self, env):
        import re

        source = SCRIPT.read_text(encoding="utf-8")
        m = re.search(r"CONTAINER=\$\{GUDBUS_CONTAINER:-(\S+?)\}", source)
        assert m, "could not find the container default"
        assert m.group(1) == "GUDBUS", (
            "verified on the box 2026-07-29: the template container is GUDBUS"
        )

    def test_a_case_mismatch_is_named_not_just_listed(self, env):
        """The failure that cost a round trip: right container, wrong case."""
        result, _ = run(
            env,
            "--preflight",
            "sha-new",
            **TEMPLATE,
            GUDBUS_CONTAINER="gudbus",  # what the caller asked for
            STUB_CONTAINER_NAME="GUDBUS",  # what actually exists on the box
        )
        out = result.stdout + result.stderr
        assert "case-sensitive" in out, (
            "a case-only mismatch must say so; the bare listing did not make "
            "GUDBUS vs gudbus visible"
        )


class TestOrdering:
    def test_prune_happens_after_the_recreate(self, env):
        """A prune before verification could delete the rollback target."""
        _, calls = run(env, "sha-new")
        up = next(i for i, c in enumerate(calls) if c.startswith("compose up"))
        first_rmi = next(i for i, c in enumerate(calls) if c.startswith("rmi "))
        assert up < first_rmi
