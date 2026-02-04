from __future__ import annotations
from typing import Literal, Any

import os
from pathlib import Path
import subprocess
import subprocess
import logging

from packaging.requirements import Requirement
import uv

from . import pyproject
from .pyproject import (
    PyProject,
    Project,
    Tools,
    ToolUV,
    ToolUVIndex,
    ToolUVSource,
    ToolUVWorkspace,
)
from .venv import Venv

logger = logging.getLogger(__name__)


class Workspace:
    """
    A uv workspace
    """

    def __init__(
        self,
        path: Path | str,
    ) -> None:
        self._path = Path(path)
        self._pyproject_filename = self._path / "pyproject.toml"
        self._pyproject: PyProject | None = None

    @property
    def path(self) -> Path:
        """The Path of the workspace."""
        return self._path

    @property
    def name(self) -> str:
        """The name of the workspace folder."""
        return self._path.name

    @property
    def group(self) -> str:
        """The name of the parent folder (sometime representing a group of workspaces)."""
        return self._path.parent.name

    def exists(self) -> bool:
        """
        Returns True if the folder exists and contains a pyproject.toml
        NB: It could be True for non-workspace folders, we assume you don't mess up your project paths.
        """
        return self._path.exists() and self._pyproject_filename.exists()

    def venv(self) -> Venv:
        venv_name = ".venv"
        return Venv(self.path / venv_name)

    def create(
        self,
        description: str | None = None,
        python_version: str | None = None,
        vcs: Literal["git", "none"] | None = None,
    ) -> None:
        description = (
            description
            or "A UV workspace, managed by tgzr.package_management.workspcace."
        )
        descr_args = []
        if description is not None:
            descr_args = ["--description", description]

        py_args = []
        if python_version is not None:
            py_args = ["-p", python_version]

        uv_exe = uv.find_uv_bin()
        cmd = [
            uv_exe,
            "init",
            "--no-package",
            "--vcs",
            vcs,
            *py_args,
            "--no-workspace",
            *descr_args,
            "--author-from",
            "auto",
            str(self.path),
        ]
        print(f"Creating workspace {self.path}: {cmd}")
        subprocess.check_call(cmd)

    @property
    def pyproject(self) -> PyProject:
        if self._pyproject is None:
            self._pyproject = pyproject.load_pyproject(self._pyproject_filename)
            if self.pyproject.tool is None:
                self.pyproject.tool = Tools(uv=ToolUV())
            if self.pyproject.tool.uv is None:
                self.pyproject.tool.uv = ToolUV()

        return self._pyproject

    @property
    def tool_uv(self) -> ToolUV:
        """The PyProject.tool.uv configuration."""
        return self.pyproject.tool.uv  # type: ignore self.pyproject ensure it's not None!

    def save_pyproject(self) -> None:
        pyproject.save_pyproject(self.pyproject, self._pyproject_filename)

    def get_index(self, name: str) -> ToolUVIndex | None:
        for index in self.tool_uv.index:
            if index.name == name:
                return index

    def ensure_index(self, name: str, url: str, explicit: bool | None = None) -> None:
        """
        Will create or update the index with name `name`.
        """
        index_to_set = ToolUVIndex(name=name, url=url, explicit=explicit)
        found = False
        for index in self.tool_uv.index:
            if index == index_to_set:
                # it is already set exactly as requested
                return

            if index.name == index_to_set.name:
                found = True
                index.url = index_to_set.url
                index.explicit = index_to_set.explicit
                break
        if not found:
            self.tool_uv.index.append(index_to_set)
        self.save_pyproject()

    def set_source(
        self,
        source_name: str,
        index_name: str | None = None,
        workspace: bool | None = None,
        path: Path | str | None = None,
        editable: bool | None = None,
    ) -> None:
        """
        Beware: not all combinations of index/workspace/path/editable are valid!

        When index_name is given, an index with that name must already
        have been defined. You can use `self.ensure_index()` if needed.
        """
        source = self.tool_uv.sources.get(source_name)
        if source is None:
            source = ToolUVSource()
            self.tool_uv.sources[source_name] = source

        if index_name is not None:
            source.index = index_name

        if workspace is not None:
            source.workspace = workspace

        if path is not None:
            source.path = str(path)

        if editable is not None:
            source.editable = editable

        self.save_pyproject()

    def add_dependencies(self, group: str = "", *new_requirements):
        if self.pyproject.project is None:
            self.pyproject.project = Project()

        if group is None:
            deps = self.pyproject.project.dependencies
        else:
            try:
                deps = self.pyproject.dependency_groups[group]
            except KeyError:
                deps = []
                self.pyproject.dependency_groups[group] = deps

        to_remove = []
        for new in new_requirements:
            new_req = Requirement(new)
            for old in deps:
                if Requirement(old).name == new_req.name:
                    to_remove.append(old)
                    break
            deps.append(new)

        for obsolet in to_remove:
            deps.remove(obsolet)

        self.save_pyproject()

    def add_member(self, member: str):
        if self.tool_uv.workspace is None:
            self.tool_uv.workspace = ToolUVWorkspace()
        self.tool_uv.workspace.members.append(member)
        self.save_pyproject()

    def run(self, console_script_name: str, *args, **extra_env: str):
        uv_exe = uv.find_uv_bin()
        cmd = [
            uv_exe,
            "run",
            # "--python",
            # str(python),
            "--directory",
            str(self.path),
            console_script_name,
            *args,
        ]
        env = None
        if extra_env:
            env = os.environ.copy()
            env.update(extra_env)

        print(f"Workspace run: {self.path}: {cmd}")
        subprocess.check_call(cmd)

    def run_python_command(self, command: str) -> None:
        uv_exe = uv.find_uv_bin()
        cmd = [
            uv_exe,
            "run",
            # "--python",
            # str(python),
            "--directory",
            str(self.path),
            "python",
            "-c",
            command,
        ]
        print(f"Workspace run python cmd: {self.path}: {cmd}")
        subprocess.check_call(cmd)

    def sync(
        self, allow_upgrade: bool = True, allow_custom_classifiers: bool = False
    ) -> None:
        env = None
        if allow_custom_classifiers:
            env = os.environ.copy()
            # This is needed to build the packages with custom classifiers:
            env["HATCH_METADATA_CLASSIFIERS_NO_VERIFY"] = "1"

        more_options = []
        if allow_upgrade:
            more_options.append("--upgrade")

        uv_exe = uv.find_uv_bin()
        cmd = [uv_exe, "--project", self.path, "sync", *more_options]
        print(f"Sync workspace {self.path}: {cmd}")
        subprocess.check_call(cmd, env=env)
