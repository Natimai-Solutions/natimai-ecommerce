"""``scripts/release/deploy.sh`` run for real, with fake ``docker``, ``curl``
and ``sleep``: the order of the steps, the dump before migrating, the
rollback when the new version does not start or is not ready.

Review of 17/11/2026: the deploy script was covered by no test."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "release" / "deploy.sh"

FAKE_DOCKER = r"""#!/usr/bin/env bash
# Logs every call (with the IMAGE_TAG it ran with) and fakes the answers.
echo "IMAGE_TAG=${IMAGE_TAG} $*" >> "$FAKE_LOG"
args="$*"
case "$args" in
  *" ps --status running --services"*)
    [[ "${FAKE_DB_RUNNING:-1}" == 1 ]] && echo postgres
    exit 0 ;;
  *" exec -T postgres "*)
    printf 'PGDMP-fake-dump'
    exit 0 ;;
  *" up -d "*)
    if [[ "${FAKE_UP_FAIL:-0}" == 1 && "$IMAGE_TAG" != "${FAKE_PREVIOUS:-}" ]]; then
      exit 1
    fi
    exit 0 ;;
esac
exit 0
"""

FAKE_CURL = r"""#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_LOG"
[[ "${FAKE_READY:-1}" == 1 ]]
"""

FAKE_SLEEP = "#!/usr/bin/env bash\nexit 0\n"


def _executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def shop(tmp_path: Path) -> Path:
    """A copy of the repository layout the script needs, and fake tools."""
    if shutil.which("bash") is None or not SCRIPT.exists():  # pragma: no cover
        pytest.skip("bash or the repository scripts are not available here")
    root = tmp_path / "shop"
    (root / "scripts" / "release").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "release" / "deploy.sh")
    (root / ".env").write_text("POSTGRES_USER=postgres\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _executable(bin_dir / "docker", FAKE_DOCKER)
    _executable(bin_dir / "curl", FAKE_CURL)
    _executable(bin_dir / "sleep", FAKE_SLEEP)
    return root


def _deploy(shop: Path, **env: str) -> tuple[int, str, list[str]]:
    log = shop.parent / "calls.log"
    log.write_text("")
    run_env = {
        **os.environ,
        "PATH": f"{shop.parent / 'bin'}:{os.environ['PATH']}",
        "FAKE_LOG": str(log),
        "IMAGE_PREFIX": "ghcr.io/org/shop",
        "IMAGE_TAG": "newsha1234567890",
        **env,
    }
    run_env.pop("GHCR_USER", None)
    done = subprocess.run(
        ["bash", str(shop / "scripts" / "release" / "deploy.sh")],
        env=run_env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return done.returncode, done.stdout + done.stderr, log.read_text().splitlines()


def _index(calls: list[str], needle: str) -> int:
    return next(i for i, call in enumerate(calls) if needle in call)


def test_a_deploy_dumps_then_migrates_then_starts(shop: Path) -> None:
    (shop / ".deployed_tag").write_text("oldsha")

    code, out, calls = _deploy(shop, API_URL="https://api.shop.test")

    assert code == 0, out
    assert (shop / ".deployed_tag").read_text().strip() == "newsha1234567890"
    dumps = list((shop / "backups").glob("pre_deploy_newsha123456_*.dump"))
    assert len(dumps) == 1 and dumps[0].read_text().startswith("PGDMP")
    # The dump, then the migrations, then the new code.
    assert _index(calls, "exec -T postgres") < _index(
        calls, "run --rm --no-build migrate"
    )
    assert _index(calls, "run --rm --no-build migrate") < _index(calls, " up -d ")
    assert any("healthz/ready" in call for call in calls)


def test_a_version_that_does_not_start_is_rolled_back(shop: Path) -> None:
    (shop / ".deployed_tag").write_text("oldsha")

    code, out, calls = _deploy(shop, FAKE_UP_FAIL="1", FAKE_PREVIOUS="oldsha")

    assert code == 1
    assert "Retour à la version précédente oldsha" in out
    assert any(c.startswith("IMAGE_TAG=oldsha ") and " up -d " in c for c in calls)
    # Still the previous version on record.
    assert (shop / ".deployed_tag").read_text().strip() == "oldsha"


def test_a_version_never_ready_is_rolled_back(shop: Path) -> None:
    (shop / ".deployed_tag").write_text("oldsha")

    code, out, calls = _deploy(shop, API_URL="https://api.shop.test", FAKE_READY="0")

    assert code == 1
    assert "ne répond pas « ready »" in out
    assert sum(1 for c in calls if "healthz/ready" in c) == 30
    assert any(c.startswith("IMAGE_TAG=oldsha ") and " up -d " in c for c in calls)
    assert (shop / ".deployed_tag").read_text().strip() == "oldsha"


def test_no_migration_without_a_dump_when_a_version_runs(shop: Path) -> None:
    (shop / ".deployed_tag").write_text("oldsha")

    code, out, calls = _deploy(shop, FAKE_DB_RUNNING="0")

    assert code == 1
    assert "pas de sauvegarde possible" in out
    assert not any("migrate" in c for c in calls)


def test_a_first_deploy_needs_no_dump(shop: Path) -> None:
    code, out, calls = _deploy(shop, FAKE_DB_RUNNING="0")

    assert code == 0, out
    assert "premier déploiement" in out
    assert not list((shop / "backups").glob("*.dump"))
    assert any("migrate" in c for c in calls)
    assert (shop / ".deployed_tag").read_text().strip() == "newsha1234567890"


def test_the_env_file_is_required(shop: Path) -> None:
    (shop / ".env").unlink()

    code, out, calls = _deploy(shop)

    assert code == 1 and ".env absent" in out
    assert calls == []
