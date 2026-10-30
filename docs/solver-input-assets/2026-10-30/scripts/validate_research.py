"""Validate research records and retained bytes; never import or run asset code.

Only explicit local-file fields are resolved. Upstream repository ``path(s)``,
archive members, URLs, prose and rejected candidates are not guessed as files.
Run from any directory: python /path/to/scripts/validate_research.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_SOLVERS = {"abaqus", "aster", "calculix", "dyna", "nastran", "optistruct", "radioss"}
QUESTIONS = {f"Q{i:02}" for i in range(1, 13)}
SINGLE_LOCAL_FIELDS = {"local_file", "analysis_file", "analysis_local_file", "internal_file"}
LIST_LOCAL_FIELDS = {"local_files", "analysis_local_files", "companion_files"}
FALSE_FLAGS = {"runtime_verified", "solver_executed", "executed"}
LOCAL_PREFIXES = ("tmp/", "examples/", "assets/", "catalogues/", "notes/", "scripts/")


class Validator:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.errors: list[dict] = []
        self.counts = Counter()
        self.source_ids: set[str] = set()
        self.rule_ids: set[str] = set()
        self.example_ids: set[str] = set()
        self.hashes: dict[Path, str] = {}
        self.checked_files: set[Path] = set()
        self.docs: dict[str, dict] = {}
        self.catalogue_counts: dict[str, int] = {}
        self.solver_results: dict[str, dict] = {}
        self.inputs: list[dict] = []

    def error(self, document: str, pointer: str, check: str, message: str):
        self.errors.append(dict(document=document, pointer=pointer, check=check, message=message))

    def digest(self, path: Path) -> str:
        if path not in self.hashes:
            h = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(block)
            self.hashes[path] = h.hexdigest()
        return self.hashes[path]

    def resolve(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path.resolve()
        # Both research-root-relative and workspace-prefixed acquisition records exist.
        if value.startswith(self.root.name + "/"):
            return (self.root.parent / path).resolve()
        return (self.root / path).resolve()

    def check_file(self, value, document, pointer, metadata=None):
        if value is None or value == "":
            return
        if not isinstance(value, str):
            self.error(document, pointer, "local-file-type", "Expected a path string or null")
            return
        if "://" in value:
            self.error(document, pointer, "local-file-type", "URL supplied in a local file field")
            return
        path = self.resolve(value)
        self.counts["local_file_references"] += 1
        if not path.is_file():
            self.error(document, pointer, "local-file-exists", f"File missing or not a regular file: {value}")
            return
        self.checked_files.add(path)
        if not metadata:
            return
        declared_size = metadata.get("size_bytes")
        if declared_size is not None and declared_size != "":
            self.counts["size_assertions"] += 1
            try:
                valid_size = int(declared_size) == path.stat().st_size
            except (TypeError, ValueError):
                valid_size = False
            if not valid_size:
                self.error(document, pointer, "local-file-size", f"Declared {declared_size!r}; observed {path.stat().st_size}: {value}")
        expected = metadata.get("sha256")
        if expected:
            self.counts["sha256_assertions"] += 1
            if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
                self.error(document, pointer, "sha256-format", f"Not a SHA256 hex digest: {expected!r}")
            elif self.digest(path) != expected.lower():
                self.error(document, pointer, "local-file-sha256", f"Declared {expected}; observed {self.digest(path)}: {value}")

    def check_false(self, value, document, pointer, csv_row=False):
        self.counts["false_execution_flag_assertions"] += 1
        okay = value == "false" or value == "False" if csv_row else value is False
        if not okay:
            self.error(document, pointer, "execution-flag-false", f"Expected false, observed {value!r}")

    def refs(self, value, allowed, document, pointer, kind):
        values = value if isinstance(value, list) else [value]
        for index, identifier in enumerate(values):
            self.counts[f"{kind}_reference_assertions"] += 1
            if not isinstance(identifier, str) or identifier not in allowed:
                self.error(document, pointer + (f"[{index}]" if isinstance(value, list) else ""), f"{kind}-reference", f"Unknown ID: {identifier!r}")

    def walk(self, node, document, pointer="$", csv_row=False):
        if isinstance(node, list):
            for index, item in enumerate(node):
                self.walk(item, document, f"{pointer}[{index}]", csv_row)
            return
        if not isinstance(node, dict):
            return
        for field in FALSE_FLAGS & node.keys():
            self.check_false(node[field], document, f"{pointer}.{field}", csv_row)
        for field in ("source_id", "source_ids"):
            if field in node:
                self.refs(node[field], self.source_ids, document, f"{pointer}.{field}", "source")
        if "rule_ids" in node:
            self.refs(node["rule_ids"], self.rule_ids, document, f"{pointer}.rule_ids", "rule")
        for field in SINGLE_LOCAL_FIELDS & node.keys():
            self.check_file(node[field], document, f"{pointer}.{field}", node)
        # Generic `file` can also mean an upstream rejected candidate. Resolve only
        # explicit local roots/absolute paths and never that rejection category.
        value = node.get("file")
        local_file = isinstance(value, str) and (value.startswith(LOCAL_PREFIXES) or Path(value).is_absolute() or value.startswith(self.root.name + "/"))
        if local_file and ".rejected_candidates" not in pointer:
            self.check_file(value, document, f"{pointer}.file", node)
        list_paths = []
        for field in LIST_LOCAL_FIELDS & node.keys():
            if not isinstance(node[field], list):
                self.error(document, f"{pointer}.{field}", "local-files-type", "Expected an explicit list of retained files")
                continue
            for index, item in enumerate(node[field]):
                list_paths.append(item)
                self.check_file(item, document, f"{pointer}.{field}[{index}]")
        if isinstance(node.get("file_hashes"), dict):
            for basename, digest in node["file_hashes"].items():
                matches = [x for x in list_paths if isinstance(x, str) and Path(x).name == basename]
                if len(matches) != 1:
                    self.error(document, f"{pointer}.file_hashes.{basename}", "file-hash-target", "Expected exactly one explicit retained-file match")
                else:
                    self.check_file(matches[0], document, f"{pointer}.file_hashes.{basename}", {"sha256": digest})
        # Legacy single-example records place primary input first in an explicit
        # analysis_local_files list; a single SHA applies only to that first file.
        elif node.get("sha256") and not any(node.get(k) for k in SINGLE_LOCAL_FIELDS | {"file"}):
            explicit = node.get("analysis_local_files")
            if isinstance(explicit, list) and explicit:
                self.check_file(explicit[0], document, f"{pointer}.analysis_local_files[0] (primary SHA)", {"sha256": node["sha256"]})
        for field, child in node.items():
            self.walk(child, document, f"{pointer}.{field}", csv_row)

    def load_json(self, path):
        relative = path.relative_to(self.root).as_posix()
        try:
            data = json.loads(path.read_text())
        except (ValueError, OSError) as exc:
            self.error(relative, "$", "json-parse", str(exc))
            return None
        self.inputs.append(dict(file=relative, size_bytes=path.stat().st_size, sha256=self.digest(path)))
        return data

    def canonical_records(self):
        files = sorted((self.root / "solvers").glob("*.json"))
        names = {p.stem for p in files}
        if names != EXPECTED_SOLVERS:
            self.error("solvers/", "$", "seven-solver-set", f"Expected {sorted(EXPECTED_SOLVERS)}, observed {sorted(names)}")
        all_ids = {"sources": self.source_ids, "rules": self.rule_ids, "examples": self.example_ids}
        for path in files:
            data = self.load_json(path)
            if not isinstance(data, dict):
                continue
            document = path.relative_to(self.root).as_posix()
            self.docs[document] = data
            if data.get("key") != path.stem:
                self.error(document, "$.key", "solver-key", "Filename and solver key differ")
            for category, identifiers in all_ids.items():
                for index, row in enumerate(data.get(category, [])):
                    identifier = row.get("id")
                    if not isinstance(identifier, str) or not identifier:
                        self.error(document, f"$.{category}[{index}].id", "record-id", "Missing ID")
                    elif identifier in identifiers:
                        self.error(document, f"$.{category}[{index}].id", "global-id-unique", f"Duplicate {category} ID: {identifier}")
                    else:
                        identifiers.add(identifier)
        for document, data in self.docs.items():
            start = len(self.errors)
            coverage = data.get("coverage", [])
            questions = [x.get("question_id") for x in coverage]
            if len(questions) != 12 or set(questions) != QUESTIONS:
                self.error(document, "$.coverage", "q01-q12", f"Expected each Q01–Q12 once, observed {questions}")
            if data.get("runtime_verified") is not False:
                self.error(document, "$.runtime_verified", "execution-flag-false", "Top-level runtime_verified must be false")
            scoped_rules = {x["id"] for x in data.get("rules", []) if "id" in x}
            for index, row in enumerate(coverage):
                for identifier in row.get("rule_ids", []):
                    if identifier not in scoped_rules:
                        self.error(document, f"$.coverage[{index}].rule_ids", "scoped-rule-reference", f"Rule is outside this solver: {identifier}")
            for index, row in enumerate(data.get("rules", [])):
                self.refs(row.get("question_ids", []), QUESTIONS, document, f"$.rules[{index}].question_ids", "question")
                self.refs(row.get("examples", []), self.example_ids, document, f"$.rules[{index}].examples", "example")
            for index, row in enumerate(data.get("examples", [])):
                if row.get("solver_executed") is not False:
                    self.error(document, f"$.examples[{index}].solver_executed", "execution-flag-false", "Every canonical example must explicitly have false")
            for index, row in enumerate(data.get("code_assets", [])):
                if row.get("executed") is not False:
                    self.error(document, f"$.code_assets[{index}].executed", "execution-flag-false", "Every code asset must explicitly have false")
            self.walk(data, document)
            catalogue = data.get("catalogue", {})
            for index, value in enumerate(catalogue.get("files", [])):
                self.check_file(value, document, f"$.catalogue.files[{index}]")
            self.solver_results[data["key"]] = dict(sources=len(data.get("sources", [])), rules=len(data.get("rules", [])), examples=len(data.get("examples", [])), code_assets=len(data.get("code_assets", [])), coverage_questions=questions, expected_primary_catalogue_rows=catalogue.get("entry_count"), canonical_errors=len(self.errors)-start)

    def catalogues(self):
        for path in sorted((self.root / "catalogues").iterdir()):
            document = path.relative_to(self.root).as_posix()
            if path.suffix == ".json":
                data = self.load_json(path)
                if data is not None:
                    self.walk(data, document)
            elif path.suffix in {".csv", ".jsonl"}:
                self.inputs.append(dict(file=document, size_bytes=path.stat().st_size, sha256=self.digest(path)))
                try:
                    if path.suffix == ".csv":
                        with path.open(newline="") as stream:
                            records = list(csv.DictReader(stream))
                    else:
                        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
                    self.catalogue_counts[document] = len(records)
                    for index, row in enumerate(records):
                        self.walk(row, document, f"$[{index}]", csv_row=path.suffix == ".csv")
                except (OSError, ValueError, csv.Error) as exc:
                    self.error(document, "$", "catalogue-parse", str(exc))
        for solver, result in self.solver_results.items():
            name = f"catalogues/{solver}.csv"
            actual = self.catalogue_counts.get(name)
            result["primary_catalogue_rows"] = actual
            if actual != result["expected_primary_catalogue_rows"]:
                self.error(name, "$", "primary-catalogue-count", f"Declared {result['expected_primary_catalogue_rows']}, observed {actual}")
            alternate = f"catalogues/{solver}.jsonl"
            if alternate in self.catalogue_counts and actual != self.catalogue_counts[alternate]:
                self.error(alternate, "$", "catalogue-mirror-count", f"CSV has {actual}, JSONL has {self.catalogue_counts[alternate]}")

    def run(self):
        self.canonical_records()
        self.catalogues()
        return dict(validation_kind="research-metadata-and-retained-file-integrity", checked_at=datetime.now(timezone.utc).isoformat(), root=str(self.root), passed=not self.errors, solver_count=len(self.solver_results), global_unique_source_ids=len(self.source_ids), global_unique_rule_ids=len(self.rule_ids), global_unique_example_ids=len(self.example_ids), solvers=self.solver_results, catalogue_row_counts=self.catalogue_counts, checks=dict(self.counts), unique_local_files_checked=len(self.checked_files), unique_files_sha256_read=len(self.hashes), errors=self.errors, input_documents=self.inputs, execution=dict(product_code_executed=False, solver_executed=False, code_assets_executed=False, validator_only=True), policy=dict(explicit_local_fields=sorted(SINGLE_LOCAL_FIELDS), explicit_local_lists=sorted(LIST_LOCAL_FIELDS), ignored_nonlocal_fields=["paths", "path", "source_path", "upstream_path", "archive_member", "url", "prose", "rejected_candidates.file"], generic_file="Only explicit research local roots/absolute path, excluding rejected candidates", primary_list_hash="Single SHA on analysis_local_files-only example applies to first primary input; named file_hashes maps by basename", catalogue="Every CSV/JSONL parses and source references resolve; primary <solver>.csv count equals declared entry_count; available CSV/JSONL mirror counts equal"), limits=["This validator checks declared metadata and retained file bytes only; it does not validate complete keyword field schemas or solver syntax/numerical behavior.", "Archive-member-only inventories without explicit retained local paths are not guessed as extracted files; their archive acquisition is verified through declared sources.", "No upstream code was imported, solver installed, generated deck written, or product executed."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="Defaults to <root>/validation.json")
    args = parser.parse_args()
    report = Validator(args.root).run()
    output = args.output or args.root / "validation.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ["passed", "solver_count", "global_unique_source_ids", "unique_local_files_checked"]}, ensure_ascii=False))
    print(f"errors={len(report['errors'])}; report={output}")
    for error in report["errors"][:30]:
        print(f"{error['document']} {error['pointer']}: {error['check']}: {error['message']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
