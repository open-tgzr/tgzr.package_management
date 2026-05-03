from __future__ import annotations

from pathlib import Path
import importlib_metadata
import platform
import json
import os
import subprocess

import pydantic

import uv


class InstallOptions(pydantic.BaseModel):
    python_version: str | None = pydantic.Field(
        default=None,
        description="The python to use (for operaty where you can force it).",
    )
    update: bool = pydantic.Field(
        default=True, description="The default python to use when creating venvs"
    )
    default_index: str | None = pydantic.Field(
        default=None, description="The default index to use when installing packages"
    )
    find_links: str | None = pydantic.Field(
        default=None,
        description="The default --find-links option when installing packages",
    )
    allow_prerelease: bool = pydantic.Field(
        default=False,
        description="The default --allow-prerelease option when installing packages",
    )
    no_cache: bool = pydantic.Field(
        default=False,
        description="The default --no-cache option when installing packages",
    )

    def to_pip_options(self) -> list[str]:
        # not sure it's actually the same as uv but I
        # dont think we'll use it anyway...
        #
        # Actually, '--no-cache' from uv is more '--no-cache-dir' for pip
        # but not exactly the same thing.
        # Should we support it?
        return self.to_uv_options()

    def to_uv_options(self) -> list[str]:
        options = []

        if self.update:
            options.append("-U")

        if self.default_index is not None:
            # options.append(f"--default-index {self.default_index}")
            options.append(
                f"--default-index {self.default_index} --index https://pypi.org/simple --index-strategy unsafe-best-match"
            )

        if self.find_links:
            options.append(f"--find-links {self.find_links}")

        if self.allow_prerelease:
            options.append("--prerelease=allow")

        if self.no_cache:
            options.append("--no-cache")

        return options


class Venv:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        if platform.system() == "Windows":
            self._bin_path = self._path / "Scripts"
        else:
            self._bin_path = self._path / "bin"
        self._site_packages_path: Path | None = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def site_packages_path(self) -> Path | None:
        if self._site_packages_path is None:
            # Note:
            # On Windows: venv/Lib/site-packages
            # On POSIX:   venv/lib/pythonX.Y/site-packages
            site_packages_path = self._path / "Lib" / "site-packages"
            if site_packages_path.exists():
                self._site_packages_path = site_packages_path
            else:
                lib = self._path / "lib"
                for p in lib.glob("python*"):
                    site_packages_path = p / "site-packages"
                    if site_packages_path.is_dir():
                        self._site_packages_path = site_packages_path
                        break
        return self._site_packages_path

    def exists(self) -> bool:
        return (
            self.path.exists()
            and self._bin_path.exists()
            and self.site_packages_path is not None
        )

    def create(
        self,
        prompt: str | None = None,
        clear_existing: bool = False,
        python_version: str | None = None,
    ):
        uv_exe = uv.find_uv_bin()

        prompt_option = ""
        if prompt:
            prompt_option = f'--prompt "{prompt}"'

        clear_option = ""
        if clear_existing:
            clear_option = f"--clear"

        python_option = ""
        if python_version is not None:
            python_option = f"--python {python_version}"

        cmd = f"{uv_exe} venv --seed {clear_option} {prompt_option} {python_option} {self.path}"
        print(f"Creating venv {self.path}: {cmd}")
        ret = os.system(cmd)
        if ret:
            raise Exception(f"Error creating venv (cmd was: {cmd}).")

    def get_exe(self, name: str):
        exe = self._bin_path / name
        if platform.system() == "Windows":
            # the '.exe' suffix is not needed to execute
            # but the caller may want to use `exe.exists()``
            # so we need to add the extension if on windows :/
            exe_suffix = exe.with_suffix(".exe")
            if exe_suffix.exists():
                # special case for .bat files
                exe = exe_suffix
        return exe

    def install_uv(self):
        return self.install_packages("uv", use_uv=False)

    def install_packages(
        self,
        requirements: str,
        install_options: InstallOptions | None = None,
        # update: bool = True,
        use_uv: bool = True,
        # default_index: str | None = None,
        # find_links: str | None = None,
        # allow_prerelease: bool = False,
    ) -> bool:
        """
        Returns True if the package has been successfully installed.

        if `index` is given, it will be passed to pip:
            - as -f/--find-links it it is a path (Note: relative path are discouraged).
            - as -i/--index-url otherwise
        """
        if use_uv:
            # NB: we're using python -m uv instead of uv directly so that uv pip installs in the same env
            # see "If uv is installed in a Python environment" in https://docs.astral.sh/uv/pip/environments/#using-arbitrary-python-environments
            exe = f'{self.get_exe("python")} -m uv pip'
        else:
            exe = f'{self.get_exe("python")} -m pip'

        options = []
        if install_options is not None:
            if use_uv:
                options = install_options.to_uv_options()
            else:
                options = install_options.to_pip_options()

        # index_options = ""
        # if default_index is not None:
        #     index_options = f"--default-index {default_index}"

        # find_links_options = ""
        # if find_links:
        #     find_links_options = f"--find-links {find_links}"

        # prerelease_options = ""
        # if allow_prerelease:
        #     prerelease_options = "--prerelease=allow"

        # update_flag = ""
        # if update:
        #     update_flag = "-U"

        cmd = f"{exe} install {' '.join(options)} {requirements}"
        print(f"Installing package(s) {requirements}: {cmd}")
        ret = os.system(cmd)
        if ret:
            raise Exception(
                f"Error installing packages {requirements!r} in venv (cmd was: {cmd})"
            )
        return not ret

    def execute_cmd(self, cmd: str) -> bool:
        """
        Returns True if the command was been successfully executed.
        """
        print("Executing venv cmd:", cmd)
        ret = os.system(cmd)
        return not ret

    def get_cmd_output(self, cmd_name: str, cmd_args: list[str]) -> tuple[str, str]:
        """
        Returns the stdout and stderr of a the command.
        """
        # TODO: thread this.
        exe = str(self.get_exe(cmd_name))
        # subprocess.Popen(text=True)
        result = subprocess.run(
            [exe] + cmd_args, capture_output=True, check=True, text=True
        )
        print("CMD", " ".join([exe] + cmd_args), "->", result.returncode)
        return result.stdout, result.stderr

    def run_cmd(self, cmd_name: str, cmd_args: list[str]) -> bool:
        """
        Returns True if the command was been successfully executed.
        """
        # TODO: thread this.
        exe = self.get_exe(cmd_name)
        cmd = str(exe) + " " + " ".join(cmd_args)
        return self.execute_cmd(cmd)

    def get_cmd_names(self) -> list[str]:
        raise NotImplementedError()

    def get_package(
        self, package_name: str, raises: bool = True
    ) -> importlib_metadata.Distribution | None:
        if self.site_packages_path is None:
            return None

        distributions = list(
            importlib_metadata.distributions(
                name=package_name, path=[str(self.site_packages_path)]
            )
        )
        if not distributions:
            if raises:
                raise ValueError(f"No {package_name} distribution found!")
            return None

        distribution = distributions.pop(0)

        if distributions:
            if raises:
                raise ValueError(
                    f"More than one distribution found for package {package_name} !!!"
                )
            return None

        return distribution

    def get_packages(
        self, name_filters: list[str] | None = None
    ) -> list[importlib_metadata.Distribution]:
        if self.site_packages_path is None:
            return []
        distributions = importlib_metadata.distributions(
            path=[str(self.site_packages_path)]
        )
        ret = []
        for dist in distributions:
            skip = False
            if name_filters:
                for name_filter in name_filters:
                    if name_filter not in dist.name:
                        skip = True
                        break
            if skip:
                continue
            ret.append(dist)
        return ret

    def get_plugins(
        self, group_filter: str | None
    ) -> list[tuple[importlib_metadata.EntryPoint, importlib_metadata.Distribution]]:
        if self.site_packages_path is None:
            return []
        distributions = importlib_metadata.distributions(
            path=[str(self.site_packages_path)]
        )
        plugins = []
        for dist in distributions:
            for ep in dist.entry_points:
                if group_filter is None or group_filter in ep.group:
                    plugins.append([ep, dist])
        return plugins

    def hatch_version_bump(self, package_path: Path, bump_type: str):
        hatch_exe = self.get_exe("hatch")
        subprocess.call(
            [hatch_exe, "version", bump_type],
            cwd=package_path,
        )

    def hatch_build(
        self,
        package_path: str | Path,
        dist_path: str | Path,
        allow_custom_classifiers=True,
    ):
        env = None
        if allow_custom_classifiers:
            env = os.environ.copy()
            # This is needed to build a package with custom classifiers:
            env["HATCH_METADATA_CLASSIFIERS_NO_VERIFY"] = "1"

        hatch_exe = self.get_exe("hatch")
        subprocess.call(
            [hatch_exe, "build", "-t", "sdist", dist_path],
            cwd=package_path,
            env=env,
        )

    def hatch_publish(
        self, package_path: str | Path, dist_path: Path, repo_url: str, **options: str
    ):
        hatch_options = sum([["-o", f"{k}={v}"] for k, v in options.items()], [])
        hatch_exe = self.get_exe("hatch")
        cmd = [
            hatch_exe,
            "publish",
            # "--publisher",
            # "tgzr-pipeline-asset",
            "--repo",
            repo_url,
            *hatch_options,
            *dist_path.iterdir(),
        ]
        # print("--->", cmd)
        subprocess.call(
            cmd,
            cwd=package_path,
        )
