from __future__ import annotations
from typing import (
    TYPE_CHECKING,
    get_args,
    Type,
    TypeVar,
    Callable,
    Any,
    Iterable,
    Generic,
)

import importlib_metadata
import inspect
import logging


T = TypeVar("T", bound="Plugin")

logger = logging.getLogger(__name__)


class Plugin:
    """
    Subclass to create your plugin type.

    NOTE: subclass should not change __init__ signature and always
    pass *args and **kwargs to super().__init__

    """

    @classmethod
    def plugin_type_name(cls) -> str:
        raise NotImplementedError()

    @classmethod
    def plugin_name(cls) -> str:
        return f"{cls.__module__}.{cls.__name__}"

    @classmethod
    def plugin_id(cls) -> str:
        return f"{cls.plugin_type_name()}@{cls.plugin_name()}"

    def __init__(self, ep: importlib_metadata.EntryPoint):
        super().__init__()
        self._entry_point = ep

    def plugin_info(self) -> dict[str, Any]:
        return dict(
            plugin_type_name=self.plugin_type_name(),
            plugin_name=self.plugin_name(),
            plugin_id=self.plugin_id(),
            entry_point=self._entry_point,
        )


PluginType = TypeVar("PluginType", bound=Plugin)


class PluginManagerRegistry:
    """
    A Registry containing all the PluginManager instances.
    This is used for documenting/inspecting plugins usage.
    """

    _PLUGIN_MANAGERS: set[PluginManager] = set()

    @classmethod
    def register(cls, plugin_manager: PluginManager):
        cls._PLUGIN_MANAGERS.add(plugin_manager)

    @classmethod
    def get_plugin_managers(cls) -> set[PluginManager]:
        return cls._PLUGIN_MANAGERS.copy()


class PluginManager(Generic[PluginType]):
    EP_GROUP = "your_plugin_entry_point_group"

    @classmethod
    def managed_plugin_type(cls) -> Type[PluginType]:
        return get_args(cls.__orig_bases__[0])[0]  # type: ignore __orig_bases__ trust me bro.

    def __init__(self):
        PluginManagerRegistry.register(self)

        self._broken: list[tuple[importlib_metadata.EntryPoint, Exception]] = []
        self._loaded: list[PluginType] = []
        self._needs_loading: bool = True

    def _instantiate_plugin_type(
        self, PluginType: Type[PluginType], entry_point: importlib_metadata.EntryPoint
    ) -> PluginType:
        """
        Subclasses will want to override this if the managed plugin type needs
        init args / kwargs.
        """
        return PluginType(entry_point)

    def _resolve_plugins(
        self,
        loaded: (
            PluginType
            | Type[PluginType]
            | Callable[[], PluginType | list[PluginType]]
            | Iterable[PluginType]
        ),
        entry_point: importlib_metadata.EntryPoint,
    ) -> list[PluginType]:
        # print("Resolving shell app plugins:", loaded)
        ManagedPluginType = self.__class__.managed_plugin_type()

        if isinstance(loaded, ManagedPluginType):
            # print("  is app")
            return [loaded]

        elif inspect.isclass(loaded) and issubclass(loaded, ManagedPluginType):
            # print("  is a plugin type")
            return [self._instantiate_plugin_type(loaded, entry_point)]

        elif callable(loaded):
            # print("  is callable (but not a plugin type)")
            try:
                plugin_or_list_of_plugins = loaded()  # type: ignore
            except Exception as err:
                raise ValueError(
                    f"Error while executing callable entry point value (ep={entry_point}): {err}"
                )
            return self._resolve_plugins(
                loaded=plugin_or_list_of_plugins, entry_point=entry_point
            )

        elif isinstance(loaded, (tuple, list, set)):
            # print("  is iterable")
            return [plugin for plugin in loaded]

        # print("  is unsupported")
        raise ValueError(
            f'Invalid value for "{self.EP_GROUP}" entry point. '
            f"Must be a {ManagedPluginType}, a list/tuple/set of {ManagedPluginType}, or a callable returning one of these"
        )

    def _load_plugins(self):
        all_entry_points = importlib_metadata.entry_points(group=self.EP_GROUP)

        self._broken.clear()
        self._loaded.clear()

        for ep in all_entry_points:
            logger.info(f"Loading {self.EP_GROUP} plugin:", ep.name)
            try:
                loaded = ep.load()
            except Exception as err:
                raise  # TMP DEE
                self._broken.append((ep, err))
            else:
                try:
                    plugins = self._resolve_plugins(loaded, ep)
                except Exception as err:
                    raise  # TMP DEE
                    self._broken.append((ep, err))
                else:
                    for plugin in plugins:
                        self._loaded.append(plugin)

        self._needs_loading = False

    def get_broken_plugins(
        self, force_reload: bool = False
    ) -> list[tuple[importlib_metadata.EntryPoint, Exception]]:
        if force_reload or self._needs_loading:
            self._load_plugins()
        return self._broken

    def get_plugins(self, force_reload: bool = False) -> list[PluginType]:
        if force_reload or self._needs_loading:
            self._load_plugins()
        return self._loaded

    def get_plugin(self, plugin_name: str) -> PluginType:
        for plugin in self.get_plugins():
            if plugin.plugin_name() == plugin_name:
                return plugin
        raise ValueError(
            f"Not {self.managed_plugin_type().plugin_type_name()} plugin found with name {plugin_name!r}. "
            f"(got plugins:{[p.plugin_name() for p in self.get_plugins()]} and errors: {self._broken})"
        )

    def find_plugins(
        self, PluginType: Type[T], raise_not_found: bool = True
    ) -> list[T]:
        found = []
        for plugin in self.get_plugins():
            if isinstance(plugin, PluginType):
                found.append(plugin)
        if not found:
            raise ValueError(
                f"No plugin with type {PluginType} found!."
                f"(got plugins:{[p.plugin_name() for p in self.get_plugins()]} and errors: {self._broken})"
            )
        return found


def usage_example():

    # In the plugin package ("my_package"):
    #
    # add this to your pyproject.toml:
    #   [project.entry-points.my_plugin_entry_point_group]
    #   my_plugin_name = "my_package.my_submodule:MyPlugin"
    #
    # Then is "my_package/my_submodule.py":
    class MyPlugin(Plugin):
        pass

    # In the host package:
    class MyPluginManager(PluginManager[MyPlugin]):
        EP_GROUP = "my_plugin_entry_point_group"

    pm = MyPluginManager()
    plugins = pm.get_plugins()


if __name__ == "__main__":
    usage_example()
