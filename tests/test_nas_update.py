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

LOCAL_D = "sha256:1111000000000000000000000000000000000000000000000000000000000000"
REMOTE_D = "sha256:2222000000000000000000000000000000000000000000000000000000000000"
OTHER_D = "sha256:3333000000000000000000000000000000000000000000000000000000000000"

# Stub curl: a registry that answers a token request and a manifest HEAD.
#
# Keyed per tag through STUB_REMOTE_<tag> so a test can make :latest and
# sha-new resolve to different digests, which is the whole point of the
# target-mismatch case. An unset tag exits non-zero, i.e. the registry does not
# have it — the same shape as having no network, which is what the default
# fixture exercises.
CURL_STUB = r"""#!/bin/sh
printf '%s\n' "$*" >> "$CURL_LOG"
url=""
for a in "$@"; do case "$a" in https://*) url=$a ;; esac; done
case "$url" in
  *"/token?"*) printf '{"token":"stub-token"}\n'; exit 0 ;;
  */manifests/*)
    tag=${url##*/manifests/}
    var="STUB_REMOTE_$(printf '%s' "$tag" | tr -c 'A-Za-z0-9' '_')"
    eval "d=\${$var:-}"
    [ -n "$d" ] || exit 22
    printf 'HTTP/2 200\r\ndocker-content-digest: %s\r\n\r\n' "$d"
    exit 0
    ;;
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
      '{{range .RepoDigests}}'*)
        # Empty when the tag is not present locally at all, which is a real
        # state and a safe one — nothing cached means nothing stale.
        [ -z "${STUB_LOCAL_DIGEST:-}" ] || printf '%s@%s\n' "$STUB_IMAGE_REPO" "$STUB_LOCAL_DIGEST"
        ;;
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


#: A template container tracking the release pointer — production's real shape.
MOVING = dict(TEMPLATE, STUB_CURRENT_IMAGE=f"{IMAGE_REPO}:latest")


class TestImageFreshness:
    """The failure this exists for happened, on 2026-07-28, on the real box.

    Production tracks `:latest`, a *moving* tag. An unRAID template "Apply"
    recreates the container but does not pull, so it rebuilds on whatever copy
    of `:latest` is already in the local image store. The deploy looked
    successful — new container, healthy, logs clean — and was running the
    previous release: the 18th extension was absent and the sync reported
    `Command set unchanged`.

    Preflight cannot pull for you (it mutates nothing by design, and the update
    itself belongs to the UI on this path), but it can compare the local copy
    against the registry and say so.
    """

    def test_a_stale_local_moving_tag_is_reported(self, env):
        result, _ = run(
            env,
            "--preflight",
            "sha-new",
            **MOVING,
            STUB_LOCAL_DIGEST=LOCAL_D,
            STUB_REMOTE_latest=REMOTE_D,
            STUB_REMOTE_sha_new=REMOTE_D,
        )
        assert result.returncode == 0
        assert "STALE" in result.stdout, (
            "the local :latest differs from the registry's and the operator was "
            "not told; this is the 2026-07-28 deploy verbatim"
        )

    def test_the_pull_command_names_the_moving_tag_not_the_target(self, env):
        """The discriminating case, and the easy thing to get wrong.

        Pulling `:sha-new` fetches the right image but leaves the `:latest` tag
        pointing at the old one — and `:latest` is what the template
        references, so the recreate still comes up on the stale image. Only a
        pull of the moving tag itself moves that pointer.
        """
        result, _ = run(
            env,
            "--preflight",
            "sha-new",
            **MOVING,
            STUB_LOCAL_DIGEST=LOCAL_D,
            STUB_REMOTE_latest=REMOTE_D,
            STUB_REMOTE_sha_new=REMOTE_D,
        )
        assert f"docker pull {IMAGE_REPO}:latest" in result.stdout
        assert f"pull {IMAGE_REPO}:sha-new" not in result.stdout, (
            "pulling the sha tag does not move :latest, so it would not fix "
            "the very failure being reported"
        )

    def test_a_local_copy_matching_the_registry_is_not_called_stale(self, env):
        result, _ = run(
            env,
            "--preflight",
            "sha-new",
            **MOVING,
            STUB_LOCAL_DIGEST=REMOTE_D,
            STUB_REMOTE_latest=REMOTE_D,
            STUB_REMOTE_sha_new=REMOTE_D,
        )
        assert result.returncode == 0
        assert "STALE" not in result.stdout
        assert "up to date" in result.stdout

    def test_it_reports_when_the_moving_tag_is_not_the_target_commit(self, env):
        """A separate failure with the same ending.

        The local copy can be a perfect match for the registry's `:latest`
        while `:latest` has not yet been moved to the commit you asked for —
        release published, pointer not yet updated, or the target is a trunk
        build that will never be on `:latest`. Applying then deploys something
        other than the commit whose CI you just checked.
        """
        result, _ = run(
            env,
            "--preflight",
            "sha-new",
            **MOVING,
            STUB_LOCAL_DIGEST=REMOTE_D,
            STUB_REMOTE_latest=REMOTE_D,
            STUB_REMOTE_sha_new=OTHER_D,
        )
        assert result.returncode == 0
        assert "does NOT" in result.stdout, (
            "latest resolves to a different image than the requested commit "
            "and nothing said so"
        )

    def test_an_immutable_sha_pin_is_not_checked_for_drift(self, env):
        """`sha-` tags are immutable, so local and registry cannot disagree.

        Reporting a comparison here would be noise at best; claiming staleness
        would be wrong. The default fixture runs `:sha-old`, so this also
        covers the Compose path, which pins a sha on every deploy.
        """
        result, _ = run(
            env,
            "--preflight",
            "sha-new",
            **TEMPLATE,
            STUB_LOCAL_DIGEST=LOCAL_D,
            STUB_REMOTE_latest=REMOTE_D,
        )
        assert result.returncode == 0
        assert "STALE" not in result.stdout
        assert "immutable" in result.stdout

    def test_it_never_pulls(self, env):
        """Preflight's mutate-nothing contract is why it ships untested against
        the real box. A pull is not a recreate, but it does change what the next
        recreate runs, so it stays the operator's call."""
        _, calls = run(
            env,
            "--preflight",
            "sha-new",
            **MOVING,
            STUB_LOCAL_DIGEST=LOCAL_D,
            STUB_REMOTE_latest=REMOTE_D,
        )
        assert not [c for c in calls if c.startswith("pull ")]

    def test_no_registry_reachable_degrades_to_a_warning(self, env):
        """Same posture as the CI gate: unverified is reported, never fatal.

        With no STUB_REMOTE_* set the stub registry has nothing, which is what
        no network looks like from here.
        """
        result, _ = run(
            env, "--preflight", "sha-new", **MOVING, STUB_LOCAL_DIGEST=LOCAL_D
        )
        assert result.returncode == 0
        assert "UNVERIFIED" in result.stdout
        assert "STALE" not in result.stdout, (
            "a failed lookup must not be read as a mismatch"
        )

    def test_an_absent_local_copy_is_not_stale(self, env):
        """Nothing cached means the recreate must pull, so there is no hazard."""
        result, _ = run(
            env,
            "--preflight",
            "sha-new",
            **MOVING,
            STUB_LOCAL_DIGEST="",
            STUB_REMOTE_latest=REMOTE_D,
            STUB_REMOTE_sha_new=REMOTE_D,
        )
        assert result.returncode == 0
        assert "STALE" not in result.stdout
        assert "not present locally" in result.stdout

    def test_the_check_can_be_skipped(self, env):
        result, _ = run(
            env,
            "--preflight",
            "sha-new",
            **MOVING,
            GUDBUS_SKIP_FRESHNESS_CHECK="1",
            STUB_LOCAL_DIGEST=LOCAL_D,
            STUB_REMOTE_latest=REMOTE_D,
        )
        assert result.returncode == 0
        assert "Image freshness" not in result.stdout

    def test_a_stale_pointer_makes_the_apply_instructions_say_pull_first(self, env):
        """The report is only useful if it lands where the operator is looking.

        The closing instructions are what gets read and acted on, so a stale
        pointer has to change them, not just add a paragraph further up.
        """
        result, _ = run(
            env,
            "--preflight",
            "sha-new",
            **MOVING,
            STUB_LOCAL_DIGEST=LOCAL_D,
            STUB_REMOTE_latest=REMOTE_D,
            STUB_REMOTE_sha_new=REMOTE_D,
        )
        tail = result.stdout.split("Preflight complete")[-1]
        assert "pull" in tail, (
            "the apply instructions still read as though a bare Apply is enough"
        )


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
