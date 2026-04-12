"""Tests for the extractor framework: schema, registry, CLI."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from spikuit_cli.extractors import check_availability, list_extractors, resolve
from spikuit_cli.extractors.manifest import ManifestError, load_manifest
from spikuit_cli.extractors.registry import (
    brain_extractors_dir,
    system_extractors_dir,
)
from spikuit_cli.main import app

runner = CliRunner()


# -- helpers ----------------------------------------------------------------


def _write_extractor(root: Path, name: str, *, file_patterns: list[str] | None = None,
                     commands: list[str] | None = None, description: str = "test fixture") -> Path:
    """Create a minimal valid extractor under ``root/<name>/``."""
    ext = root / name
    ext.mkdir(parents=True)
    fp = file_patterns or []
    cmds = commands or []
    fp_toml = "[" + ", ".join(f'"{p}"' for p in fp) + "]"
    cmds_toml = "[" + ", ".join(f'"{c}"' for c in cmds) + "]"
    (ext / "manifest.toml").write_text(
        f'[extractor]\n'
        f'name = "{name}"\n'
        f'version = "0.1.0"\n'
        f'description = "{description}"\n'
        f'\n'
        f'[match]\n'
        f'file_patterns = {fp_toml}\n'
        f'\n'
        f'[requires]\n'
        f'commands = {cmds_toml}\n',
        encoding="utf-8",
    )
    (ext / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return ext


@pytest.fixture
def brain(tmp_path, monkeypatch):
    """Empty brain rooted at tmp_path (no git, no DB needed for these tests)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".spikuit").mkdir()
    return tmp_path


# -- manifest ---------------------------------------------------------------


def test_load_manifest_parses_all_fields(tmp_path):
    p = tmp_path / "manifest.toml"
    p.write_text(
        '[extractor]\n'
        'name = "demo"\n'
        'version = "1.2.3"\n'
        'description = "d"\n'
        'author = "a"\n'
        '[match]\n'
        'file_patterns = ["*.py"]\n'
        'url_patterns = ["github.com/"]\n'
        'content_keywords = ["import"]\n'
        '[requires]\n'
        'commands = ["python3"]\n'
        'python_packages = ["msgspec"]\n',
        encoding="utf-8",
    )
    m = load_manifest(p)
    assert m.name == "demo"
    assert m.version == "1.2.3"
    assert m.match.file_patterns == ["*.py"]
    assert m.match.url_patterns == ["github.com/"]
    assert m.match.content_keywords == ["import"]
    assert m.requires.commands == ["python3"]
    assert m.requires.python_packages == ["msgspec"]


def test_load_manifest_requires_name(tmp_path):
    p = tmp_path / "manifest.toml"
    p.write_text('[extractor]\nversion = "0.0.1"\n', encoding="utf-8")
    with pytest.raises(ManifestError, match="name is required"):
        load_manifest(p)


# -- registry ---------------------------------------------------------------


def test_resolve_includes_bundled_default():
    extractors = resolve(brain_root=None)
    assert "default" in extractors
    assert extractors["default"].tier == "system"


def test_resolve_includes_reference_extractors():
    """python-code, pdf-paper, github-repo ship with v0.6.1."""
    extractors = resolve(brain_root=None)
    for name in ("python-code", "pdf-paper", "github-repo"):
        assert name in extractors, f"{name} not found in system tier"
        assert extractors[name].tier == "system"
        assert extractors[name].skill_md.is_file()


def test_reference_extractors_have_match_rules():
    """Reference extractors must declare at least one match pattern."""
    extractors = resolve(brain_root=None)
    for name in ("python-code", "pdf-paper", "github-repo"):
        m = extractors[name].manifest.match
        assert m.file_patterns or m.url_patterns or m.content_keywords, \
            f"{name} has no match rules"


def test_pdf_paper_declares_pymupdf_requirement():
    extractors = resolve(brain_root=None)
    assert "pymupdf" in extractors["pdf-paper"].manifest.requires.python_packages


def test_github_repo_declares_gh_command():
    extractors = resolve(brain_root=None)
    assert "gh" in extractors["github-repo"].manifest.requires.commands


def test_brain_tier_shadows_system(brain):
    bdir = brain_extractors_dir(brain)
    bdir.mkdir(parents=True)
    _write_extractor(bdir, "default", description="my custom default")

    extractors = resolve(brain_root=brain)
    assert extractors["default"].tier == "brain"
    assert extractors["default"].manifest.description == "my custom default"


def test_underscore_dirs_are_skipped(brain):
    """`_template` and `_registry.toml` should not appear as extractors."""
    extractors = resolve(brain_root=None)
    assert "_template" not in extractors


def test_list_extractors_sorted(brain):
    bdir = brain_extractors_dir(brain)
    bdir.mkdir(parents=True)
    _write_extractor(bdir, "zeta")
    _write_extractor(bdir, "alpha")
    names = [e.name for e in list_extractors(brain_root=brain)]
    # alpha and zeta both present, sorted alphabetically alongside default
    assert names == sorted(names)
    assert "alpha" in names and "zeta" in names and "default" in names


# -- availability -----------------------------------------------------------


def test_availability_default_is_runnable():
    extractors = resolve(brain_root=None)
    report = check_availability(extractors["default"])
    assert report.available is True
    assert report.missing_commands == []
    assert report.missing_python_packages == []


def test_availability_reports_missing_command(brain):
    bdir = brain_extractors_dir(brain)
    bdir.mkdir(parents=True)
    _write_extractor(bdir, "needs-magic", commands=["definitely-not-a-real-binary-xyz"])
    extractors = resolve(brain_root=brain)
    report = check_availability(extractors["needs-magic"])
    assert report.available is False
    assert "definitely-not-a-real-binary-xyz" in report.missing_commands


# -- CLI --------------------------------------------------------------------


def test_cli_list_json_includes_default(brain):
    result = runner.invoke(app, ["skills", "extractor", "list", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    names = [e["name"] for e in data]
    assert "default" in names


def test_cli_status_json_marks_default_available(brain):
    result = runner.invoke(app, ["skills", "extractor", "status", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    default = next(e for e in data if e["name"] == "default")
    assert default["available"] is True


def test_cli_show_default(brain):
    result = runner.invoke(app, ["skills", "extractor", "show", "default", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["name"] == "default"
    assert data["tier"] == "system"
    assert "skill_md" in data and "Default Extractor" in data["skill_md"]


def test_cli_fork_default_into_brain(brain):
    result = runner.invoke(
        app, ["skills", "extractor", "fork", "default", "my-default"]
    )
    assert result.exit_code == 0, result.output
    forked = brain_extractors_dir(brain) / "my-default"
    assert (forked / "manifest.toml").is_file()
    assert (forked / "SKILL.md").is_file()
    # name was rewritten
    m = load_manifest(forked / "manifest.toml")
    assert m.name == "my-default"
    # Registry was written
    assert (brain_extractors_dir(brain) / "_registry.toml").is_file()


def test_cli_fork_same_name_shadows_system(brain):
    result = runner.invoke(app, ["skills", "extractor", "fork", "default"])
    assert result.exit_code == 0, result.output
    extractors = resolve(brain_root=brain)
    assert extractors["default"].tier == "brain"


def test_cli_add_external_dir(brain, tmp_path):
    src = tmp_path / "external"
    _write_extractor(src.parent, "external")
    # Move into actual external dir
    ext_src = tmp_path / "external"
    result = runner.invoke(app, ["skills", "extractor", "add", str(ext_src)])
    assert result.exit_code == 0, result.output
    assert (brain_extractors_dir(brain) / "external" / "manifest.toml").is_file()


def test_cli_remove_brain_extractor(brain):
    runner.invoke(app, ["skills", "extractor", "fork", "default", "tmp-ext"])
    result = runner.invoke(
        app, ["skills", "extractor", "remove", "tmp-ext", "-y"]
    )
    assert result.exit_code == 0, result.output
    assert not (brain_extractors_dir(brain) / "tmp-ext").exists()


def test_cli_remove_nonexistent_fails(brain):
    result = runner.invoke(
        app, ["skills", "extractor", "remove", "not-installed", "-y"]
    )
    assert result.exit_code != 0


def test_cli_refresh_writes_registry(brain):
    bdir = brain_extractors_dir(brain)
    bdir.mkdir(parents=True)
    _write_extractor(bdir, "alpha", file_patterns=["*.txt"])
    result = runner.invoke(app, ["skills", "extractor", "refresh"])
    assert result.exit_code == 0, result.output
    registry = bdir / "_registry.toml"
    assert registry.is_file()
    text = registry.read_text(encoding="utf-8")
    assert 'name = "alpha"' in text
    assert '"*.txt"' in text
