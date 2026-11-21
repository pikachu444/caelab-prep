"""Resolve Starter INCLUDE graphs against disk or a portable file inventory."""
from collections import Counter, defaultdict, deque
from functools import cache
from pathlib import PurePosixPath

from ..cae_core import PrepError


_MAX_8E85_STALLED_WALKS = 64


class _DiskOrderMismatch(Exception):
    """A partial deduction cannot produce the recorded first-visit order."""


def include_relative(value: str) -> PurePosixPath:
    if not isinstance(value, str):
        raise PrepError("invalid_project", "INCLUDE 경로는 문자열이어야 합니다.")
    portable = value.replace("\\", "/")
    path = PurePosixPath(portable)
    if not value or path.is_absolute() or ":" in portable or ".." in path.parts:
        raise PrepError("include_path_unsupported", "이 INCLUDE 경로는 독립 문서로 묶을 수 없습니다.", {"path": value})
    return path


def include_lookup(paths):
    exact = set(paths)
    folded = defaultdict(list)
    for path in exact:
        folded[path.casefold()].append(path)

    def lookup(path):
        if path in exact:
            return path
        matches = folded.get(path.casefold(), ())
        return matches[0] if len(matches) == 1 else None

    return lookup


def disk_include_lookup(base, *, canonical=True):
    def relative_path(candidate):
        return (candidate.resolve() if canonical else candidate).relative_to(base).as_posix()

    @cache
    def lookup(path):
        candidate = base / path
        if candidate.is_file():
            return relative_path(candidate)
        matches = [base]
        for part in PurePosixPath(path).parts:
            matches = [child for parent in matches if parent.is_dir() for child in parent.iterdir()
                       if child.name.casefold() == part.casefold()]
            if not matches:
                break
        files = [candidate for candidate in matches if candidate.is_file()]
        if len(files) == 1:
            return relative_path(files[0])
        return None

    return lookup


def resolve_includes(root, lookup, load, *, scope="", archive_inventory=None, selected=None, recovered=None,
                     historical=None, archived_order=None, load_order=None):
    """Resolve live paths or replay validated bindings against an archive inventory."""
    selected, recovered = selected or {}, recovered or {}
    if historical in ("ac0", "bde", "8e85") and archive_inventory is not None:
        load = cache(load)
        disk_policy = None if historical == "8e85" else historical
        order = []
        result = _walk_includes(root, lookup, load, scope, selected, recovered, disk_policy, load_order=order)
        sequential = historical == "8e85" and not result[2] and result[0] != archive_inventory
        if sequential:
            # The writer used sequential replay to remap the archived bytes after disk collection.
            result = _walk_includes(root, lookup, load, scope, selected, recovered, historical)
        if (not result[2] and result[0] == archive_inventory
                and (sequential or (archived_order is not None and order != archived_order))
                and not _can_collect_from_disk(root, lookup, load, scope, archive_inventory, disk_policy,
                                              archived_order=archived_order, load_order=order)):
            directive = next(iter(load(root).include_directives), None)
            result[2].append((root, directive, PrepError(
                "invalid_project", "The writer's disk traversal could not verify the archived INCLUDE inventory and order.")))
        if load_order is not None:
            load_order[:] = order
        return result
    result = _walk_includes(root, lookup, load, scope, selected, recovered, historical, load_order=load_order)
    if historical is None and archive_inventory is not None and not result[2] and archive_inventory - result[0]:
        # ac0a255d let an earlier ambiguous directive claim the root for the
        # next directive. Use that policy only if it explains the entire ZIP.
        legacy_order = [] if load_order is not None else None
        legacy = _walk_includes(root, lookup, load, scope, selected, recovered, "ac0", load_order=legacy_order)
        if not legacy[2] and legacy[0] == archive_inventory:
            if load_order is not None:
                load_order[:] = legacy_order
            return legacy
    return result


def _include_paths(directory, operand, scope):
    relative = include_relative(operand)
    logical = relative.as_posix()
    scoped = scope and not logical.casefold().startswith(scope.casefold() + "/")
    return relative, f"{scope}/{logical}" if scoped else logical, (directory / relative).as_posix()


def _can_collect_from_disk(root, lookup, load, scope, archive_inventory, historical, *,
                           archived_order=None, load_order=None):
    """Deduce missing sibling paths from disk order and verify a fixed layout."""
    lookup = cache(lookup)
    expected = list(archived_order) if archived_order is not None else None
    archived_files = {path.casefold() for path in archive_inventory}
    archived_dirs = {parent.as_posix().casefold() for path in archive_inventory
                     for parent in PurePosixPath(path).parents if parent != PurePosixPath(".")}
    references = Counter()
    lookups = Counter()
    children = defaultdict(set)
    for owner in archive_inventory:
        directory = PurePosixPath(owner).parent
        for directive in load(owner).include_directives:
            _, root_path, sibling_path = _include_paths(directory, directive.path, scope)
            lookups.update({root_path.casefold(), sibling_path.casefold()})
            targets = {lookup(root_path), lookup(sibling_path)} - {None}
            references.update(targets)
            children[owner].update(targets)

    def isolated_prefix(root_file, matched):
        todo, visited = [root_file], set()
        while todo:
            path = todo.pop()
            if path in visited:
                continue
            if path not in matched or references[path] != 1:
                return False
            visited.add(path)
            todo.extend(children.get(path, ()))
        return True

    @cache
    def is_legal_phantom(path):
        return (path not in archived_files and path not in archived_dirs
                and not any(parent.as_posix() in archived_files for parent in PurePosixPath(path).parents))

    def load_archived(path):
        if path not in archive_inventory:
            raise PrepError("include_missing", "Disk traversal would collect an unarchived INCLUDE.")
        return load(path)

    pending = [iter((frozenset(),))]
    seen = set()
    best_prefix = -1
    stalled = 0
    while pending:
        alternatives = next(pending[-1], None)
        if alternatives is None:
            pending.pop()
            continue
        if alternatives in seen:
            continue
        seen.add(alternatives)
        phantoms = set(alternatives)
        fallback = {}
        deduced_order = []

        def disk_lookup(path):
            archived = lookup(path)
            if archived is None and path.casefold() in phantoms:
                return path.casefold()
            return archived

        def next_expected():
            return expected[len(deduced_order)] if len(deduced_order) < len(expected) else None

        def load_in_order(path):
            if expected is not None and path != next_expected():
                raise _DiskOrderMismatch()
            return load_archived(path)

        def deduce_sibling(sibling_path, root_file):
            if root_file not in archive_inventory:
                return None
            path = sibling_path.casefold()
            if expected is None or root_file == next_expected():
                # An isolated leaf cannot change any later wave decision.
                affects_wave = references[root_file] > 1 or load(root_file).include_directives or lookups[path] > 1
                if affects_wave and is_legal_phantom(path):
                    fallback.setdefault(path, root_file)
                return None
            if not is_legal_phantom(path):
                raise _DiskOrderMismatch()
            phantoms.add(path)
            return path

        try:
            _walk_includes(root, disk_lookup, load_in_order, scope, {}, {}, historical,
                           load_order=deduced_order, deduce_sibling=deduce_sibling)
        except _DiskOrderMismatch:
            pass

        # Verify from the Starter with every deduced file present from the start.
        verified_order = []
        if not any(parent.as_posix() in phantoms for path in phantoms for parent in PurePosixPath(path).parents):
            reached, _, problems = _walk_includes(root, disk_lookup, load_archived, scope, {}, {}, historical,
                                                  load_order=verified_order)
            if (not problems and reached == archive_inventory
                    and (expected is None or verified_order == expected)):
                if load_order is not None:
                    load_order[:] = verified_order
                return True
        prefix = len(verified_order)
        if expected is not None:
            prefix = next((i for i, (actual, wanted) in enumerate(zip(verified_order, expected))
                           if actual != wanted), prefix)
        if prefix > best_prefix:
            best_prefix, stalled = prefix, 0
        else:
            stalled += 1
            if stalled >= _MAX_8E85_STALLED_WALKS:
                return False
        # Delaying an entire private subtree already consumed in order cannot
        # change later bindings. Keep alternatives that cross the mismatch or
        # affect a path shared with another branch.
        matched = set(verified_order[:prefix])
        candidates = ((path,) for path, target in reversed(fallback.items())
                      if lookups[path] > 1 or not isolated_prefix(target, matched))
        pending.append(map(alternatives.union, candidates))
    return False


def _walk_includes(root, lookup, load, scope, selected, recovered, historical, *, load_order=None, deduce_sibling=None):
    reached, explicit = set(), set()
    bindings, problems = {}, []
    outgoing = defaultdict(set)
    pending = deque()

    def leads_to(start, owner):
        todo, visited = [start], set()
        while todo:
            path = todo.pop()
            if path == owner:
                return True
            if path not in visited:
                visited.add(path)
                todo.extend(outgoing.get(path, ()))
        return False

    def follow(owner, directive, target, chain):
        try:
            if target in chain or (target in reached and leads_to(target, owner)):
                raise PrepError("include_cycle", "순환 INCLUDE를 발견했습니다.", {"path": target})
            visit(target, chain)
            bindings[owner, directive.header_row] = target
            outgoing[owner].add(target)
        except (PrepError, ValueError, OSError) as exc:
            problems.append((owner, directive, exc))

    def visit(owner, ancestors):
        if owner in reached:
            return
        directives = load(owner).include_directives
        reached.add(owner)
        if load_order is not None:
            load_order.append(owner)
        chain = (*ancestors, owner)
        directory = PurePosixPath(owner).parent
        for ordinal, directive in enumerate(directives):
            try:
                # Archived imports have their own original root. A converted
                # path that already names that namespace stays project-relative.
                relative, root_path, sibling_path = _include_paths(directory, directive.path, scope)
                logical = relative.as_posix()
                root_file = lookup(root_path)
                # The 24137d60 reader resolved every operand from the Starter root.
                sibling = lookup(sibling_path) if historical != "241" and sibling_path != root_path else root_file
                key = owner, ordinal
                if key in recovered:
                    follow(owner, directive, recovered[key], chain)
                    continue
                if key in selected and selected[key] not in (root_file, sibling):
                    raise PrepError("invalid_project", "A recorded INCLUDE binding does not match its native directive.",
                                    {"path": logical, "target": selected[key]})
                if not (root_file or sibling):
                    raise PrepError("include_missing", "INCLUDE 파일이 없습니다.", {"path": logical})
                if (deduce_sibling is not None and owner != root and sibling_path != root_path
                        and root_file is not None and root_file not in reached and sibling is None):
                    sibling = deduce_sibling(sibling_path, root_file)
                if root_file and sibling and root_file != sibling:
                    if key in selected:
                        follow(owner, directive, selected[key], chain)
                    elif historical == "8fe":
                        follow(owner, directive, sibling, chain)
                    elif historical == "987":
                        follow(owner, directive, root_file, chain)
                    elif historical == "ac0" and len(relative.parts) > 1:
                        explicit.add(root_file)
                        follow(owner, directive, root_file, chain)
                    elif (root_file in chain) != (sibling in chain):
                        follow(owner, directive, sibling if root_file in chain else root_file, chain)
                    else:
                        pending.append((owner, directive, root_file, sibling, chain))
                else:
                    target = root_file or sibling
                    if len(relative.parts) > 1:
                        explicit.add(target)
                    follow(owner, directive, target, chain)
            except (PrepError, ValueError, OSError) as exc:
                problems.append((owner, directive, exc))

    visit(root, ())
    # Freeze the unambiguous claims so one ambiguous binding cannot change
    # the choice made for another directive.
    snapshot_reached, snapshot_explicit = reached.copy(), explicit.copy()
    sequential = historical in ("ac0", "8e85")
    while pending:
        if sequential:
            unambiguous_reached, unambiguous_explicit = reached, explicit
        elif historical == "bde":
            unambiguous_reached, unambiguous_explicit = snapshot_reached, snapshot_explicit
        else:
            unambiguous_reached, unambiguous_explicit = reached.copy(), explicit.copy()
        batch = [pending.popleft() for _ in range(1 if sequential else len(pending))]
        for owner, directive, root_file, sibling, chain in batch:
            target = sibling if root_file in unambiguous_reached and sibling not in unambiguous_explicit else root_file
            follow(owner, directive, target, chain)
    return reached, bindings, problems
