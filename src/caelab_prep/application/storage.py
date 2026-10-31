"""Shared atomic container writing and bounded reading; codecs own semantics."""
import json
import os
from pathlib import Path
import tempfile
import zipfile


def write_container(target: Path, manifest: dict, members: dict[str, bytes]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".caeprep-", dir=target.parent)
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False))
            for name, payload in members.items():
                archive.writestr(name, payload)
        with open(temporary, "r+b") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_container(source: Path) -> tuple[dict, dict[str, bytes]]:
    with zipfile.ZipFile(source) as archive:
        inventory = archive.infolist()
        if len(inventory) > 10000 or sum(item.file_size for item in inventory) > 2 * 1024**3:
            raise ValueError("container size limit exceeded")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate ZIP member")
        manifest = json.loads(archive.read("manifest.json"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        return manifest, {name: archive.read(name) for name in names if name != "manifest.json"}
