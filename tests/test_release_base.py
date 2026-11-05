# SPDX-License-Identifier: Apache-2.0
"""The guard of release.yml that decides on which branch a tag may stand (RELEASING.md)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

# The script runs on the Linux runner of release.yml, where this test runs too. On Windows,
# `bash` is often WSL's, which doesn't understand the paths. Only the platform decides, so that
# the test can never be skipped in CI.
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="needs a POSIX bash and git")

SCRIPT = Path(__file__).parent.parent / ".github" / "scripts" / "release-base.sh"
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.org",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.org",
}


@pytest.fixture(scope="module")
def repository(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    """root ── on_main, root ── on_release_01, root ── on_release_02, root ── elsewhere"""
    directory = tmp_path_factory.mktemp("release-base")

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=directory, env=GIT_ENV, check=True, capture_output=True, text=True
        )
        return done.stdout.strip()

    git("init", "-q")
    tree = git("hash-object", "-t", "tree", "-w", "/dev/null")
    root = git("commit-tree", tree, "-m", "root")
    commits = {"root": root}
    for name, branch in (
        ("on_main", "main"),
        ("on_release_01", "release/0.1"),
        ("on_release_02", "release/0.2"),
        ("elsewhere", "fix/other"),
    ):
        commits[name] = git("commit-tree", tree, "-p", root, "-m", name)
        git("update-ref", f"refs/remotes/origin/{branch}", commits[name])
    return directory, commits


@pytest.mark.parametrize(
    ("tag", "commit", "want"),
    [
        # A minor version comes from main only.
        ("v0.2.0", "on_main", "main"),
        ("v0.2.0-rc.1", "on_main", "main"),
        ("v0.2.0-alpha.1", "on_main", "main"),
        ("v0.1.0", "on_release_01", None),
        ("v0.1.0-rc.2", "on_release_01", None),
        # A patch comes from its own release branch only.
        ("v0.1.1", "on_release_01", "release/0.1"),
        ("v0.1.1-rc.1", "on_release_01", "release/0.1"),
        ("v0.1.10", "on_release_01", "release/0.1"),
        ("v0.2.3", "on_release_02", "release/0.2"),
        ("v0.1.1", "on_main", None),
        ("v0.1.1-rc.1", "on_main", None),
        # History the branches share.
        ("v0.2.0", "root", "main"),
        ("v0.1.1", "root", "release/0.1"),
        # Another release branch, one that does not exist, anywhere else.
        ("v0.1.2", "on_release_02", None),
        ("v0.2.1", "on_release_01", None),
        ("v0.3.1", "on_main", None),
        ("v0.1.1", "elsewhere", None),
        ("v0.2.0", "elsewhere", None),
        # Not a version.
        ("v0.1", "on_main", None),
        ("v0.2.0-beta.1", "on_main", None),
        ("0.2.0", "on_main", None),
        ("v0.2.0-rc.1;x", "on_main", None),
        ("v0.2.0\nv0.2.1", "on_main", None),
    ],
)
def test_release_base(
    repository: tuple[Path, dict[str, str]], tag: str, commit: str, want: str | None
) -> None:
    directory, commits = repository

    run = subprocess.run(
        ["bash", str(SCRIPT), tag, commits[commit]],
        cwd=directory,
        check=False,
        capture_output=True,
        text=True,
    )

    if want is None:
        assert run.returncode != 0
        assert run.stdout == ""
        assert "::error::" in run.stderr
    else:
        assert run.returncode == 0, run.stderr
        assert run.stdout.strip() == want
