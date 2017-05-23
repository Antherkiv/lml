"""
    lml.plugin
    ~~~~~~~~~~~~~~~~~~~

    Plugin management system

    :class:`~lml.plugin.PluginManager` should be inherited to form new
    plugin manager class. If you have more than one plugins in your
    architcture, it is advisable to have one class per plugin type.

    :class:`~lml.plugin.PluginInfoChain` helps the plugin module to
    declare the avialable plugins in the module.

    :class:`~lml.plugin.PluginInfo` can be subclassed to describe
    your plugin. Its method :meth:`~lml.plugin.PluginInfo.tags`
    can be overridden to help its matching :class:`~lml.plugin.PluginManager`
    to look itself up.

    :copyright: (c) 2017 by Onni Software Ltd.
    :license: New BSD License, see LICENSE for more details
"""
import logging
from collections import defaultdict

from lml.utils import do_import_class
from lml.utils import json_dumps


PLUG_IN_MANAGERS = {}
CACHED_PLUGIN_INFO = defaultdict(list)

log = logging.getLogger(__name__)


class PluginInfo(object):
    """
    Information about the plugin

    Parameters
    -------------
    name:
       plugin name

    absolute_import_path:
       absolute import path from your plugin name space for your plugin class

    tags:
       a list of keywords help the plugin manager to retrieve your plugin
    """
    def __init__(self, plugin_type,
                 abs_class_path=None,
                 tags=None, **keywords):
        self.plugin_type = plugin_type
        self.absolute_import_path = abs_class_path
        self.cls = None
        self.properties = keywords
        self.__tags = tags

    def __getattr__(self, name):
        if name == 'module_name':
            if self.absolute_import_path:
                module_name = self.absolute_import_path.split('.')[0]
            else:
                module_name = self.cls.__module__
            return module_name
        return self.properties.get(name)

    def tags(self):
        """
        A list of tags for identifying the plugin class

        The plugin class is described at the absolute_import_path
        """
        if self.__tags is None:
            yield self.plugin_type
        else:
            for tag in self.__tags:
                yield tag

    def __repr__(self):
        rep = {"plugin_type": self.plugin_type,
               "path": self.absolute_import_path}
        rep.update(self.properties)
        return json_dumps(rep)

    def __call__(self, cls):
        self.cls = cls
        _register_a_plugin(self, cls)
        return cls


class PluginInfoChain(object):
    """
    Pandas style, chained list declaration

    It is used in the plugin packages to list all plugin classes
    """
    def __init__(self, path):
        self.module_name = path

    def add_a_plugin(self, plugin_type, submodule=None,
                     **keywords):
        """
        Add a plain plugin

        Parameters
        -------------

        plugin_type:
          plugin manager name

        submodule:
          the relative import path to your plugin class
        """
        a_plugin_info = PluginInfo(
            plugin_type,
            self._get_abs_path(submodule),
            **keywords)

        self.add_a_plugin_instance(a_plugin_info)
        return self

    def add_a_plugin_instance(self, plugin_info_instance):
        """
        Add a plain plugin

        Parameters
        -------------

        plugin_info_instance:
          an instance of PluginInfo

        The developer has to specify the absolute import path
        """
        log.debug(plugin_info_instance)
        _load_me_later(plugin_info_instance)
        return self

    def _get_abs_path(self, submodule):
        return "%s.%s" % (self.module_name, submodule)


class PluginManager(object):
    """
    Load plugin info into in-memory dictionary for later import
    """
    def __init__(self, plugin_type):
        self.plugin_name = plugin_type
        self.registry = defaultdict(list)
        self._logger = logging.getLogger(
            self.__class__.__module__ + '.' + self.__class__.__name__)
        _register_class(self)

    def get_a_plugin(self, key, **keywords):
        """ Get a plugin """
        self._logger.debug("get a plugin")
        plugin = self.load_me_now(key)
        return plugin()

    def raise_exception(self, key):
        """Raise plugin not found exception

        Override this method to raise custom exception
        """
        self._logger.debug(self.registry.keys())
        raise Exception(
            "No %s is found for %s" % (self.plugin_name, key))

    def load_me_later(self, plugin_info):
        """
        Register a plugin info for later loading
        """
        self._logger.debug('load me later: ' + plugin_info.module_name)
        self._logger.debug(plugin_info)
        for key in plugin_info.tags():
            self.registry[key.lower()].append(plugin_info)

    def load_me_now(self, key, library=None, **keywords):
        """
        Import a plugin from plugin registry
        """
        self._logger.debug("load me now:" + key)
        if keywords:
            self._logger.debug(keywords)
        __key = key.lower()
        if __key in self.registry:
            for plugin_info in self.registry[__key]:
                cls = self.dynamic_load_library(plugin_info)
                module_name = _get_me_pypi_package_name(cls.__module__)
                if library and module_name != library:
                    continue
                else:
                    break
            else:
                # only library condition coud raise an exception
                raise Exception("%s is not installed" % library)
            return cls
        else:
            self.raise_exception(key)

    def dynamic_load_library(self, a_plugin_info):
        """Dynamically load the plugin info if not loaded"""
        if a_plugin_info.cls is None:
            self._logger.debug("import " + a_plugin_info.absolute_import_path)
            cls = do_import_class(a_plugin_info.absolute_import_path)
            a_plugin_info.cls = cls
        return a_plugin_info.cls

    def register_a_plugin(self, plugin_cls, plugin_info):
        """ for dynamically loaded plugin during runtime"""
        self._logger.debug("register " + plugin_cls.__name__)
        for key in plugin_info.tags():
            plugin_info.cls = plugin_cls
            self.registry[key.lower()].append(plugin_info)


def _register_class(cls):
    """Reigister a newly created plugin manager"""
    log.debug("register " + cls.plugin_name)
    PLUG_IN_MANAGERS[cls.plugin_name] = cls
    if cls.plugin_name in CACHED_PLUGIN_INFO:
        # check if there is early registrations or not
        for plugin_info in CACHED_PLUGIN_INFO[cls.plugin_name]:
            if plugin_info.absolute_import_path:
                log.debug("load cached plugin info: %s",
                          plugin_info.absolute_import_path)
            else:
                log.debug("load cached plugin info: %s",
                          plugin_info.cls.__name__)
            cls.load_me_later(plugin_info)

        del CACHED_PLUGIN_INFO[cls.plugin_name]


def _register_a_plugin(plugin_info, plugin_cls):
    """module level function to register a plugin"""
    manager = PLUG_IN_MANAGERS.get(plugin_info.plugin_type)
    if manager:
        manager.register_a_plugin(plugin_cls, plugin_info)
    else:
        # let's cache it and wait the manager to be registered
        log.debug("caching %s", plugin_cls.__name__)
        CACHED_PLUGIN_INFO[plugin_info.plugin_type].append(plugin_info)


def _load_me_later(plugin_info):
    """ module level function to load a plugin later"""
    log.debug("load me later")
    log.debug(plugin_info)
    manager = PLUG_IN_MANAGERS.get(plugin_info.plugin_type)
    if manager:
        manager.load_me_later(plugin_info)
    else:
        # let's cache it and wait the manager to be registered
        log.debug("caching " + plugin_info.absolute_import_path)
        CACHED_PLUGIN_INFO[plugin_info.plugin_type].append(plugin_info)


def _get_me_pypi_package_name(module_name):
    root_module_name = module_name.split('.')[0]
    return root_module_name.replace('_', '-')
