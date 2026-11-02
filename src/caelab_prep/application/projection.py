"""Read-only geometry payloads and an explicit mutable/JSON boundary.

Geometry is cached by the session's document epoch and projection revision.
Only the small view stamps are renewed after scalar commands. Consumers must
request ``mesh_view(mutable=True)`` when they need editable lists or JSON data.
"""
from collections.abc import Mapping
from types import MappingProxyType


def readonly(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: readonly(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(readonly(item) for item in value)
    return value


def mutable(value):
    """Materialize a detached JSON-compatible tree; never used for rendering."""
    if isinstance(value, Mapping):
        return {key: mutable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [mutable(item) for item in value]
    return value
