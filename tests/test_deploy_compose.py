"""The nightly instance must not collide with production.

`deploy/nightly-compose.yml` stands up a second copy of the bot on the same
host, from the same image repository. Everything that makes that safe is a
naming decision: its own container, its own volume, its own env file, its own
Discord token. Those are easy to break by copying a line across from the
production compose and easy not to notice, because the failure is a dev build
running migrations against the real database.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
PROD = ROOT / "docker-compose.yml"
NIGHTLY = ROOT / "deploy" / "nightly-compose.yml"


def _load(path):
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def prod():
    return _load(PROD)


@pytest.fixture(scope="module")
def nightly():
    return _load(NIGHTLY)


def _only_service(compose):
    (svc,) = compose["services"].values()
    return svc


class TestNoCollisionWithProduction:
    def test_container_names_differ(self, prod, nightly):
        assert _only_service(prod)["container_name"] != _only_service(nightly)[
            "container_name"
        ]

    def test_service_keys_differ(self, prod, nightly):
        # Compose targets services by name; identical keys in two projects on
        # one host is a trap even when the projects are separate.
        assert set(prod["services"]) & set(nightly["services"]) == set()

    def test_volumes_are_disjoint(self, prod, nightly):
        shared = set(prod.get("volumes") or {}) & set(nightly.get("volumes") or {})
        assert not shared, (
            f"nightly shares volume(s) {sorted(shared)} with production — a "
            "trunk build would migrate the real database"
        )

    def test_nightly_mounts_none_of_productions_volumes(self, prod, nightly):
        prod_vols = {m.split(":")[0] for m in _only_service(prod)["volumes"]}
        night_vols = {m.split(":")[0] for m in _only_service(nightly)["volumes"]}
        assert not (prod_vols & night_vols)

    def test_env_files_differ(self, prod, nightly):
        assert _only_service(prod)["env_file"] != _only_service(nightly)["env_file"]


class TestNightlyTracksTrunk:
    def test_image_is_the_nightly_tag(self, nightly):
        image = _only_service(nightly)["image"]
        assert image.endswith(":nightly"), (
            f"nightly instance points at {image}; it is supposed to track the "
            "trunk channel, otherwise it is a second production instance"
        )

    def test_it_does_not_build_locally(self, nightly):
        # The whole point is exercising the artifact CI published.
        assert "build" not in _only_service(nightly)


class TestHardeningMatchesProduction:
    """A dev instance with more privilege than production is not testing it."""

    @pytest.mark.parametrize("key", ["read_only", "cap_drop", "security_opt"])
    def test_same_hardening(self, prod, nightly, key):
        assert _only_service(nightly)[key] == _only_service(prod)[key], (
            f"{key} differs from production"
        )

    def test_tmpfs_is_present(self, nightly):
        # read_only rootfs with nowhere to scratch fails at runtime, not here.
        assert "/tmp" in _only_service(nightly)["tmpfs"]
