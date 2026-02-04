"""

API to edit pyproject.toml files.

Originally from https://jcristharif.com/msgspec/examples/pyproject-toml.html

"""

from __future__ import annotations
from typing import Any

from pathlib import Path

import msgspec


class Base(
    msgspec.Struct,
    omit_defaults=True,
    forbid_unknown_fields=True,
    rename="kebab",
):
    """A base class holding some common settings.

    - We set ``omit_defaults = True`` to omit any fields containing only their
      default value from the output when encoding.
    - We set ``forbid_unknown_fields = True`` to error nicely if an unknown
      field is present in the input TOML. This helps catch typo errors early,
      and is also required per PEP 621.
    - We set ``rename = "kebab"`` to rename all fields to use kebab case when
      encoding/decoding, as this is the convention used in pyproject.toml. For
      example, this will rename ``requires_python`` to ``requires-python``.
    """

    pass


class BuildSystem(Base):
    requires: list[str] = []
    build_backend: str | None = None
    backend_path: list[str] = []


class Readme(Base):
    file: str | None = None
    text: str | None = None
    content_type: str | None = None


class License(Base):
    file: str | None = None
    text: str | None = None


class Contributor(Base):
    name: str | None = None
    email: str | None = None


class Project(Base):
    name: str | None = None
    version: str | None = None
    description: str | None = None
    readme: str | Readme | None = None
    license: str | License | None = None
    authors: list[Contributor] = []
    maintainers: list[Contributor] = []
    keywords: list[str] | None = None
    classifiers: list[str] = []
    urls: dict[str, str] = {}
    requires_python: str | None = None
    dependencies: list[str] = []
    optional_dependencies: dict[str, list[str]] = {}
    scripts: dict[str, str] = {}
    gui_scripts: dict[str, str] = {}
    entry_points: dict[str, dict[str, str]] = {}
    dynamic: list[str] = []


class ToolUVSource(Base):
    index: str | None = None
    workspace: bool | None = False
    path: str | None = None
    editable: bool | None = None


class ToolUVIndex(Base):
    name: str
    url: str
    explicit: bool | None = None


class ToolUVWorkspace(Base):
    members: list[str] = []


class ToolUV(Base):
    sources: dict[str, ToolUVSource] = {}
    index: list[ToolUVIndex] = []
    workspace: ToolUVWorkspace | None = None


class ToolHatchMetadata(Base):
    allow_custom_classifiers: bool | None = False


class ToolHatchVersion(Base):
    path: str | None = None
    source: str | None = None
    fallback_version: str | None = None


class ToolHatchBuildTarget(Base):
    artifacts: list[str] = []
    packages: list[str] = []
    hooks: dict[str, Any] = {}


class ToolHatchBuild(Base):
    artifacts: list[str] = []
    packages: list[str] = []
    hooks: dict[str, Any] = {}
    targets: dict[str, ToolHatchBuildTarget] = {}


class ToolHatch(Base):
    metadata: dict[str, str | bool] = {}
    envs: dict[str, Any] | None = None
    version: ToolHatchVersion | None = None
    build: ToolHatchBuild | None = None
    # publish: dict[str, str] | None = {}


class ToolCoverageRun(Base):
    source_pkgs: list[str] = msgspec.field(default=[], name="source_pkgs")
    branch: bool = True
    parallel: bool = True
    omit: list[str] = []


class ToolCoverage(Base):
    run: Any | None = None
    paths: dict[str, Any] = {}
    report: Any | None = None


class ToolSetuptoolsScme(Base):
    version_file: str | None = msgspec.field(default=None, name="version_file")


class ToolRuffLintISort(Base):
    force_sort_within_sections: bool = False


class ToolRuffLint(Base):
    isort: ToolRuffLintISort | None = None


class ToolRuff(Base):
    lint: ToolRuffLint | None = None


class ToolMypy(Base):
    check_untyped_defs: bool = False
    disallow_untyped_defs: bool = False
    disallow_untyped_calls: bool = False
    overrides: list[Any] = []


class Tools(Base):
    """
    We can't specify a Tool subclass depending on the Tool name,
    so this Tool struct needs to handle ALL the tools we need at
    once :/
    Sucks, but good enough for me :p
    """

    hatch: ToolHatch | None = None
    uv: ToolUV | None = None
    coverage: ToolCoverage | None = None
    setuptools_scm: ToolSetuptoolsScme | None = msgspec.field(
        default=None, name="setuptools_scm"
    )
    ruff: ToolRuff | None = None
    mypy: ToolMypy | None = None
    setuptools: Any | None = None


class PyProject(Base):

    build_system: BuildSystem | None = None
    project: Project | None = None
    dependency_groups: dict[str, list[str]] = {}
    tool: Tools | None = None

    def set_filepath(self, filepath: Path):
        self._filepath = filepath


def load_pyproject(filepath: Path | str):
    filepath = Path(filepath)
    with filepath.open() as fp:
        data = fp.read()
    pyproject = msgspec.toml.decode(data, type=PyProject)
    return pyproject


def save_pyproject(pyproject: PyProject, filepath: Path | str):
    filepath = Path(filepath)
    data = msgspec.toml.encode(pyproject)
    with filepath.open("wb") as fp:
        fp.write(data)


def test():
    import toml
    import json
    import rich
    import dictdiffer

    stats = dict(
        tested=0,
        failed=0,
    )

    def assert_roundtrip(path: str | Path):
        stats["tested"] += 1
        path = Path(path)
        try:
            pp = load_pyproject(path)
        except Exception as err:
            raise Exception(f"pyproject load failed for {path}: {err}")
        pp_dict = json.loads(msgspec.json.encode(pp))
        toml_dict = toml.load(path)
        try:
            assert pp_dict == toml_dict
        except AssertionError:
            stats["failed"] += 1
            if 0:
                print(10 * "##")
                rich.print(pp_dict)
                print(10 * "--")
                rich.print(toml_dict)

            print(f"Diff found for {str(path)}:")
            for diff in dictdiffer.diff(pp_dict, toml_dict):
                print(diff)

            print(f"Roundtrip failed for {str(path)}!")

    root_path = Path("/home/dee/DEV/_OPEN-TGZR_")
    for folder in root_path.iterdir():
        pyproject_filename = folder / "pyproject.toml"
        if pyproject_filename.exists():
            print("Testing", pyproject_filename)
            assert_roundtrip(pyproject_filename)

    print(f"Stats: {stats}")


if __name__ == "__main__":
    test()
