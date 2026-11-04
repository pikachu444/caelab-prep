"""Verify and archive an existing portable candidate without rebuilding it."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile


LOCAL_RECORDS = {"build-manifest.json", "analysis-inputs.json"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def archive_candidate(candidate, output):
    candidate = Path(candidate).resolve(strict=True)
    output = Path(output).resolve()
    if output.exists() or output.is_relative_to(candidate):
        raise ValueError("Output must be new and outside the existing candidate")
    manifest_path = candidate / "build-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest["stage"] != "built" or manifest["build_exit_code"] != 0:
        raise ValueError("Only a successfully built candidate can be archived")
    for field in ("source_commit", "packaging_commit"):
        if not isinstance(manifest[field], str) or not re.fullmatch(r"[0-9a-f]{40}", manifest[field]):
            raise ValueError(f"Invalid {field}")

    records = []
    names = set()
    for item in manifest["files"]:
        name = item["path"]
        if (not isinstance(name, str) or not name or "\\" in name or ":" in name
                or any(part in ("", ".", "..") for part in name.split("/"))
                or PurePosixPath(name).is_absolute() or name.casefold() in names
                or name.casefold() == "build-manifest.json"):
            raise ValueError(f"Unsafe or duplicate candidate path: {name!r}")
        names.add(name.casefold())
        path = candidate / name
        if (not path.resolve().is_relative_to(candidate) or not path.is_file()
                or path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]):
            raise ValueError(f"Candidate file is missing or changed: {name}")
        records.append({key: item[key] for key in ("path", "bytes", "sha256")})

    actual = set()
    for path in candidate.rglob("*"):
        if path.is_symlink():
            raise ValueError("Candidate must not contain symbolic links")
        if path.is_file():
            actual.add(path.relative_to(candidate).as_posix())
    expected = {item["path"] for item in records}
    if actual != expected | {"build-manifest.json"}:
        raise ValueError("Candidate contains files outside its recorded inventory")
    if (manifest["file_count"] != len(records)
            or manifest["total_bytes"] != sum(item["bytes"] for item in records)):
        raise ValueError("Candidate inventory totals disagree")
    if not {"caelab-prep.exe", "analysis-inputs.json"}.issubset(expected):
        raise ValueError("Candidate executable and analysis record are required")
    if digest(candidate / "analysis-inputs.json") != manifest["analysis_inputs_sha256"]:
        raise ValueError("Candidate analysis record has changed")

    payload = sorted((item for item in records if item["path"] not in LOCAL_RECORDS),
                     key=lambda item: item["path"])
    public = {
        "source_commit": manifest["source_commit"],
        "packaging_commit": manifest["packaging_commit"],
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "analysis_inputs_sha256": manifest["analysis_inputs_sha256"],
        "omitted_local_records": sorted(LOCAL_RECORDS),
        "files": payload,
        "scope": "Filtered handoff record; payload integrity only, not Windows or redistribution acceptance",
        "redistribution_accepted": False,
        "notice_gaps": len(manifest["notices"]["no_installed_notice_found"]),
        "unresolved_redistribution_conditions": len(manifest["notices"]["unresolved"]),
    }
    public_bytes = (json.dumps(public, indent=2) + "\n").encode("utf-8")
    archive_name = (f"CAELab-Prep-{manifest['source_commit'][:12]}-"
                    f"{manifest['packaging_commit'][:12]}.zip")
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix=".archive-", dir=output) as temporary:
        staged = Path(temporary) / archive_name
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in payload:
                archive.write(candidate / item["path"], "CAELab-Prep/" + item["path"])
            archive.writestr("CAELab-Prep/build-manifest.json", public_bytes)
        with zipfile.ZipFile(staged) as archive:
            expected_members = {"CAELab-Prep/" + item["path"] for item in payload}
            expected_members.add("CAELab-Prep/build-manifest.json")
            if set(archive.namelist()) != expected_members or archive.testzip() is not None:
                raise ValueError("Archive inventory or CRC verification failed")
            for item in payload:
                with archive.open("CAELab-Prep/" + item["path"]) as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                        raise ValueError(f"Candidate changed while archiving: {item['path']}")
            if archive.read("CAELab-Prep/build-manifest.json") != public_bytes:
                raise ValueError("Archive handoff record verification failed")
        checksum = digest(staged)
        checksum_file = output / (archive_name + ".sha256")
        archive_path = output / archive_name
        try:
            checksum_file.write_text(f"{checksum}  {archive_name}\n", encoding="ascii")
            staged.replace(archive_path)
        except BaseException:
            # This invocation exclusively created the output directory.
            checksum_file.unlink(missing_ok=True)
            archive_path.unlink(missing_ok=True)
            raise
    return output / archive_name


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path, help="Existing built CAELab-Prep directory")
    parser.add_argument("--output", required=True, type=Path, help="New directory for ZIP and SHA256")
    args = parser.parse_args(argv)
    try:
        path = archive_candidate(args.candidate, args.output)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        parser.error(str(error))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
