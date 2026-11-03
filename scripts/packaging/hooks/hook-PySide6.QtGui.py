"""Keep QtWidgets image/native input plugins; omit unused optional readers/UI."""
from PyInstaller.utils.hooks.qt import add_qt6_dependencies


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)

# Exclude before binary dependency expansion, rather than deleting Qt DLLs.
_unused_plugins = {"plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
                   "plugins/imageformats/qpdf.dll"}


def _plugin_path(item):
    source, destination = (str(value).replace("\\", "/") for value in item)
    return ("/" + destination.strip("/") + "/" + source.rsplit("/", 1)[-1]).casefold()


binaries = [item for item in binaries
            if not any(_plugin_path(item).endswith("/" + name) for name in _unused_plugins)]
