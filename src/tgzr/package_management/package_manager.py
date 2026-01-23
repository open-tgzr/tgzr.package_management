from __future__ import annotations

import os
import platform
from pathlib import Path

from .venv import Venv


class PackageManager:
    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def get_venv_path(self, venv_name: str, group: str) -> Path:
        return self.root / group / venv_name

    def get_venv(self, venv_name: str, group: str) -> Venv:
        return Venv(self.get_venv_path(venv_name, group))

    def _create_bat_shortcut(self, exe_path: Path | str, shortcut_path: Path | str):
        exe_path = Path(exe_path)
        if not exe_path.is_absolute() and not str(exe_path).startswith("./"):
            exe_path = f".\\{exe_path}"

        shortcut_path = Path(shortcut_path)
        if shortcut_path.suffix != ".bat":
            shortcut_path = f"{shortcut_path}.bat"

        content = [
            "@echo off",
            f"REM Shortcut to {exe_path}",
            "",
            f"{exe_path} %*",
        ]
        with open(shortcut_path, "w") as fp:
            fp.write("\n".join(content))

    def create_shortcut(
        self, exe_path: Path | str, shortcut_path: Path | str, relative: bool = True
    ):
        """
        Create a shortcut to exe_path at shortcut_path.

        If `relative` is True, `exe_path` will be modified to be relative
        to `shortcut_path`.

        The shortcut will be a symlink to the exe, unless the OS does not
        allow it in which case a .bat file is created.
        """
        if relative:
            exe_path = Path(exe_path).relative_to(Path(shortcut_path).parent)

        if platform.system() == "Linux":
            os.symlink(exe_path, shortcut_path, target_is_directory=False)
        else:
            self._create_bat_shortcut(exe_path, shortcut_path)

    def create_venv(
        self,
        venv_name: str,
        group: str,
        exist_ok: bool = False,
        prompt: str | None = None,
    ) -> Venv:
        venv = self.get_venv(venv_name, group)
        if venv.exists() and not exist_ok:
            raise ValueError(f"Virtual Env {venv.path} already exists!")

        venv.create(prompt, clear_existing=exist_ok)
        venv.install_uv()
        return venv
