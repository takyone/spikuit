"""Tests for spkt branch / history / undo (git-backed Brain versioning)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest
from typer.testing import CliRunner

from spikuit_cli.main import app

runner = CliRunner()


# -- Fixtures ---------------------------------------------------------------


@pytest.fixture
def brain(tmp_path, monkeypatch):
    """A fresh git-backed brain in tmp_path. Returns the brain root."""
    if shutil.which("git") is None:
        pytest.skip("git not on PATH")

    monkeypatch.chdir(tmp_path)
    # Make sure git commits work in CI / minimal environments
    monkeypatch.setenv("GIT_AUTHOR_NAME", "test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")

    result = runner.invoke(app, ["init", "-p", "none", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["git"] is True
    return tmp_path


def _git(brain_root, *args):
    return subprocess.run(
        ["git", "-C", str(brain_root), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _add_commit(brain_root, filename, message):
    (brain_root / filename).write_text("x")
    _git(brain_root, "add", filename)
    _git(brain_root, "commit", "-q", "-m", message)


# -- init --git -------------------------------------------------------------


def test_init_creates_git_repo_with_initial_commit(brain):
    assert (brain / ".git").is_dir()
    assert (brain / ".gitignore").is_file()
    log = _git(brain, "log", "--pretty=%s")
    assert "manual: init brain" in log.stdout


def test_init_no_git_skips_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "-p", "none", "--no-git", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["git"] is False
    assert not (tmp_path / ".git").exists()


# -- branch start/finish/abandon --------------------------------------------


def test_branch_start_creates_ingest_branch(brain):
    result = runner.invoke(app, ["branch", "start", "papers-2026-04", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["branch"] == "ingest/papers-2026-04"
    current = _git(brain, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert current == "ingest/papers-2026-04"


def test_branch_finish_ff_merges_into_main(brain):
    runner.invoke(app, ["branch", "start", "test", "--json"])
    _add_commit(brain, "a.txt", "ingest(test): 1 sample")

    result = runner.invoke(app, ["branch", "finish", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["merged"] == "ingest/test"
    assert payload["into"] == "main"

    current = _git(brain, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert current == "main"
    branches = _git(brain, "branch", "--list", "ingest/test").stdout.strip()
    assert branches == ""  # branch deleted
    log = _git(brain, "log", "--pretty=%s").stdout
    assert "ingest(test): 1 sample" in log


def test_branch_abandon_discards_branch(brain):
    runner.invoke(app, ["branch", "start", "junk", "--json"])
    _add_commit(brain, "junk.txt", "ingest(junk): bad data")

    result = runner.invoke(app, ["branch", "abandon", "--json"])
    assert result.exit_code == 0, result.output

    current = _git(brain, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert current == "main"
    branches = _git(brain, "branch", "--list", "ingest/junk").stdout.strip()
    assert branches == ""
    log = _git(brain, "log", "--pretty=%s").stdout
    assert "ingest(junk)" not in log


def test_branch_finish_refuses_main(brain):
    result = runner.invoke(app, ["branch", "finish", "--json"])
    assert result.exit_code != 0
    assert "not an ingest" in result.output or "not an ingest" in str(result.stderr)


# -- history ----------------------------------------------------------------


def test_history_lists_commits(brain):
    _add_commit(brain, "a.txt", "ingest(test): one")
    _add_commit(brain, "b.txt", "manual: hand edit")

    result = runner.invoke(app, ["history", "--json"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    messages = [r["message"] for r in rows]
    assert "ingest(test): one" in messages
    assert "manual: hand edit" in messages


def test_history_grep_filters(brain):
    _add_commit(brain, "a.txt", "ingest(papers): one")
    _add_commit(brain, "b.txt", "manual: unrelated")

    result = runner.invoke(app, ["history", "--grep", "ingest", "--json"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    messages = [r["message"] for r in rows]
    assert "ingest(papers): one" in messages
    assert "manual: unrelated" not in messages


# -- undo -------------------------------------------------------------------


def test_undo_reverts_head(brain):
    _add_commit(brain, "a.txt", "ingest(test): one")
    head_before = _git(brain, "rev-parse", "HEAD").stdout.strip()

    result = runner.invoke(app, ["undo", "-y", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["count"] == 1
    assert head_before in payload["reverted"]

    log = _git(brain, "log", "-1", "--pretty=%s").stdout.strip()
    assert log.startswith('Revert "ingest(test): one"')
    # File should be gone after revert
    assert not (brain / "a.txt").exists()


def test_undo_to_sha_reverts_range(brain):
    base = _git(brain, "rev-parse", "HEAD").stdout.strip()
    _add_commit(brain, "a.txt", "ingest(test): one")
    _add_commit(brain, "b.txt", "ingest(test): two")

    result = runner.invoke(app, ["undo", "--to", base, "-y", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["count"] == 2

    assert not (brain / "a.txt").exists()
    assert not (brain / "b.txt").exists()


def test_undo_ingest_tag_filter(brain):
    _add_commit(brain, "a.txt", "ingest(papers): one")
    _add_commit(brain, "b.txt", "manual: unrelated")
    _add_commit(brain, "c.txt", "ingest(papers): two")

    result = runner.invoke(app, ["undo", "--ingest-tag", "papers", "-y", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["count"] == 2

    # The unrelated manual commit's file is still there
    assert (brain / "b.txt").exists()
    # Reverted ingest files are gone
    assert not (brain / "a.txt").exists()
    assert not (brain / "c.txt").exists()
