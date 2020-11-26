# --------------------------------------------------------------------------------------
# Copyright 2020 by Glaze Authors, see git history for more details.
#
# Distributed under the terms of the BSD license.
#
# The full license is in the file LICENCE, distributed with this software.
# --------------------------------------------------------------------------------------
"""Preferences plugin definition.

"""
import os
from collections import OrderedDict
from functools import partial
from typing import Any, Dict, Optional

import toml
from atom.api import Str, Typed
from enaml.workbench.api import Plugin

from glaze.utils.plugin_tools import ExtensionsCollector

from .preferences import Preferences

PREFS_POINT = "glaze.preferences.plugin"


class PrefPlugin(Plugin):
    """Plugin responsible for managing the application preferences."""

    #: Folder used by the application to store informations such as preferences
    #: log files, ...
    app_directory = Str()

    #: Path of the last location visited using a dialog.
    last_directory = Str()

    def start(self) -> None:
        """Start the plugin, locate app folder and load default preferences."""
        # Look for the app specific storage under the user to locate the application
        # folder that may be stored somewhere else.
        storage_path = os.path.join(os.path.expanduser("~"), self.location_file)
        if os.path.isfile(storage_path):
            self.app_directory = app_path = toml.load(storage_path)["app_path"]
        else:
            raise RuntimeError(
                "The location file does not exist. This should "
                "never happen since it is created during the app startup, "
                "ensure that the preference plugin startup sequence runs before "
                "starting teh plugin."
            )
        self.app_directory = app_path
        self._prefs = OrderedDict()

        pref_path = os.path.join(app_path, "preferences")
        if not os.path.isdir(pref_path):
            os.mkdir(pref_path)

        default_pref_path = os.path.join(pref_path, "default.ini")
        if os.path.isfile(default_pref_path):
            self._prefs = toml.load(default_pref_path, OrderedDict)

        self._pref_decls = ExtensionsCollector(
            workbench=self.workbench, point=PREFS_POINT, ext_class=Preferences
        )
        self._pref_decls.start()

    def stop(self) -> None:
        """Stop the plugin."""
        self._pref_decls.stop()
        del self._prefs

    def save_preferences(self, path: Optional[str] = None) -> None:
        """Collect and save preferences for all registered plugins.

        Parameters
        ----------
        path : str, optional
            Path of the file in which save the preferences. In its absence
            the default file is used.

        """
        if path is None:
            path = os.path.join(self.app_directory, "preferences", "default.toml")

        prefs = OrderedDict()
        for plugin_id in self._pref_decls.contributions:
            plugin = self.workbench.get_plugin(plugin_id)
            decl = self._pref_decls.contributions[plugin_id]
            save_method = getattr(plugin, decl.saving_method)
            prefs[plugin_id] = save_method()

        with open(path, "w") as f:
            toml.dump(prefs, f)

    def load_preferences(self, path: Optional[str] = None) -> None:
        """Load preferences and update all registered plugin.

        Parameters
        ----------
        path : str, optional
            Path to the file storing the preferences. In its absence default
            preferences are loaded.

        """
        if path is None:
            path = os.path.join(self.app_directory, "preferences", "default.toml")

        if not os.path.isfile(path):
            return

        prefs = toml.load(path, OrderedDict)
        self._prefs.merge(prefs)
        for plugin_id in prefs:
            if plugin_id in self._pref_decls.contributions:
                plugin = self.workbench.get_plugin(plugin_id, force_create=False)
                if plugin:
                    decl = self._pref_decls.contributions[plugin_id]
                    load_method = getattr(plugin, decl.loading_method)
                    load_method(prefs[plugin_id])

    def plugin_init_complete(self, plugin_id: str) -> None:
        """Notify the preference plugin that a plugin has started properly.

        The associated command should be called by a plugin once it has started
        and loaded its preferences. This call is necessary to avoid overriding
        values for auto-save members by default values.

        Parameters
        ----------
        plugin_id : str
            Id of the plugin which has started.

        """
        plugin = self.workbench.get_plugin(plugin_id)
        pref_decl = self._pref_decls.contributions[plugin_id]
        for member in pref_decl.auto_save:
            # Custom observer which does not rely on the fact that the object
            # in the change dictionnary is a plugin
            observer = partial(self._auto_save_update, plugin_id)
            plugin.observe(member, observer)

    def get_plugin_preferences(self, plugin_id: str) -> Dict[str, Any]:
        """Access to the preferences values stored for a plugin.

        Parameters
        ----------
        plugin_id : unicode
            Id of the plugin whose preferences values should be returned.

        Returns
        -------
        prefs : dict(str, str)
            Preferences for the plugin as a dict.

        """
        if plugin_id not in self._pref_decls.contributions:
            msg = "Plugin %s is not registered in the preferences system"
            raise KeyError(msg % plugin_id)

        if plugin_id in self._prefs:
            return self._prefs[plugin_id]

        return {}

    def open_editor(self):
        """"""
        pass
        # TODO here must build all editors from declaration, open dialog
        # and manage the update if the user validate.

    # =========================================================================
    # ---- Private API --------------------------------------------------------
    # =========================================================================

    #: Ordered dict in which the preferences are stored
    _prefs = Typed(OrderedDict)

    #: Mapping between plugin_id and the declared preferences.
    _pref_decls = Typed(ExtensionsCollector)

    def _auto_save_update(self, plugin_id: str, change: Dict[str, Any]) -> None:
        """Observer for the auto-save members

        Parameters
        ----------
        plugin_id : str
            Id of the plugin owner of the member being observed

        change : dict
            Change dictionnary given by Atom

        """
        name = change["name"]
        value = change["value"]
        if plugin_id in self._prefs:
            self._prefs[plugin_id][name] = value
        else:
            self._prefs[plugin_id] = {name: value}

        self._prefs.write()
