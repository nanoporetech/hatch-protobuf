from hatchling.plugin import hookimpl

from .plugin import ProtocHook


@hookimpl
def hatch_register_build_hook():
    return ProtocHook
