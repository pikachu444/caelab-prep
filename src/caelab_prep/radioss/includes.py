"""Resolve Starter INCLUDE graphs against disk or a portable file inventory."""
from collections import defaultdict, deque
from functools import cache
from heapq import heappop, heappush
from itertools import count
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
                     historical=None, archived_order=None, load_order=None, uncollected_siblings=None, sibling_aliases=None):
    """Resolve live paths or replay validated bindings against an archive inventory."""
    selected, recovered = selected or {}, recovered or {}
    if selected and archived_order is not None and archive_inventory is not None:
        load = cache(load)
        expected_bindings = {(owner, load(owner).include_directives[ordinal].header_row): target
                             for (owner, ordinal), target in selected.items()}
        has_sibling_evidence = uncollected_siblings is not None or sibling_aliases is not None
        if has_sibling_evidence:
            lookup = _include_lookup_with_siblings(archive_inventory, load, lookup, uncollected_siblings or set(),
                                                   sibling_aliases or {}, scope)
        order = []

        def load_collected(path):
            if path not in archive_inventory:
                raise PrepError("invalid_project", "The INCLUDE traversal selected an unarchived file.")
            return load(path)

        result = _walk_includes(root, lookup, load_collected, scope, selected, recovered, historical, load_order=order,
                                verify_disk=True)
        if result != (archive_inventory, expected_bindings, []) or order != archived_order:
            # The archive may omit an alternate that delayed a native wave.
            # Validate the recorded order and bindings against one disk replay.
            replay = None
            if not has_sibling_evidence:
                replay = _can_collect_from_disk(root, lookup, load, scope, archive_inventory, historical,
                                                archived_order=archived_order, load_order=order,
                                                expected_bindings=expected_bindings)
            if replay:
                result = replay
            else:
                directive = next(iter(load(root).include_directives), None)
                result[2].append((root, directive, PrepError(
                    "invalid_project", "The recorded INCLUDE bindings and order could not be verified.")))
        if load_order is not None:
            load_order[:] = order
        return result
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


def _archived_path_types(inventory, *, exact=False):
    files = set(inventory)
    directories = {parent.as_posix() for path in inventory
                   for parent in PurePosixPath(path).parents if parent != PurePosixPath(".")}
    if exact:
        return files, directories
    return {path.casefold() for path in files}, {path.casefold() for path in directories}


def _legal_phantom(path, files, directories):
    return (path not in files and path not in directories
            and not any(parent.as_posix() in files for parent in PurePosixPath(path).parents))


def _sibling_evidence(inventory, load, lookup, scope="", *, path_name=None):
    """Find alternate disk paths absent from the collected inventory."""
    files, directories = _archived_path_types(inventory, exact=True)
    siblings, aliases = set(), {}
    for owner in inventory:
        directory = PurePosixPath(owner).parent
        for directive in load(owner).include_directives:
            _, root_path, sibling_path = _include_paths(directory, directive.path, scope)
            candidate = sibling_path if path_name is None else path_name(sibling_path)
            if root_path != sibling_path and candidate is not None and _legal_phantom(candidate, files, directories):
                target = lookup(sibling_path)
                root_target = lookup(root_path)
                if target is not None and root_target in inventory and target != root_target:
                    if target in inventory:
                        aliases[candidate] = target
                    else:
                        siblings.add(candidate)
    return siblings, aliases


def source_disk_siblings(base, resources):
    """Capture uncollected files and aliases to collected files before saving."""
    by_path = {resource.name: resource for resource in resources}
    siblings, aliases = _sibling_evidence(by_path.keys(), by_path.__getitem__, disk_include_lookup(base))
    return sorted(siblings), dict(sorted(aliases.items()))


def _include_lookup_with_siblings(inventory, load, lookup, siblings, aliases, scope):
    """Check that the archived disk evidence could coexist with the inventory."""
    alternate_paths = siblings | aliases.keys()
    path_name = include_lookup(inventory | alternate_paths)

    def disk_lookup(path):
        name = path_name(path)
        if name in inventory:
            return lookup(name)
        return aliases.get(name, name)

    files, directories = _archived_path_types(inventory, exact=True)
    if (siblings & aliases.keys() or any(target not in inventory for target in aliases.values())
            or any(not _legal_phantom(path, files, directories)
                   or any(parent.as_posix() in alternate_paths for parent in PurePosixPath(path).parents)
                   for path in alternate_paths)
            or _sibling_evidence(inventory, load, disk_lookup, scope, path_name=path_name) != (siblings, aliases)):
        raise PrepError("invalid_project", "Invalid INCLUDE sibling evidence.")
    return disk_lookup


def _can_collect_from_disk(root, lookup, load, scope, archive_inventory, historical, *,
                           archived_order=None, load_order=None, expected_bindings=None):
    """Deduce missing sibling paths from disk order and verify a fixed layout."""
    lookup = cache(lookup)
    expected = list(archived_order) if archived_order is not None else None
    archived_files, archived_dirs = _archived_path_types(archive_inventory)
    callers = defaultdict(set)
    lookup_sites = defaultdict(set)
    children = defaultdict(set)
    for owner in archive_inventory:
        directory = PurePosixPath(owner).parent
        for ordinal, directive in enumerate(load(owner).include_directives):
            relative, root_path, sibling_path = _include_paths(directory, directive.path, scope)
            root_target = lookup(root_path)
            qualified_root = historical == "ac0" and len(relative.parts) > 1 and root_target is not None
            operands = {root_path} if qualified_root else {root_path, sibling_path}
            # Repeat operands in a frozen wave make the same selection. The
            # sequential reader can make two decisions even within one file.
            site = (owner, root_path.casefold(), sibling_path.casefold(), ordinal if historical == "ac0" else None)
            for path in operands:
                lookup_sites[path.casefold()].add(site)
            targets = {lookup(path) for path in operands} - {None}
            for target in targets:
                callers[target].add(owner)
            children[owner].update(targets)

    def isolated_prefix(root_file, matched, wave_targets):
        todo, visited = [root_file], set()
        while todo:
            path = todo.pop()
            if path in visited:
                continue
            if path not in matched or path in wave_targets or not callers[path].issubset(matched):
                return False
            visited.add(path)
            todo.extend(children.get(path, ()))
        return True

    @cache
    def frontier_ancestors(target):
        todo, ancestors = [target], set()
        while todo:
            path = todo.pop()
            if path not in ancestors:
                ancestors.add(path)
                todo.extend(callers.get(path, ()))
        return ancestors

    @cache
    def is_legal_phantom(path):
        return _legal_phantom(path, archived_files, archived_dirs)

    def load_archived(path):
        if path not in archive_inventory:
            raise PrepError("include_missing", "Disk traversal would collect an unarchived INCLUDE.")
        return load(path)

    initial = frozenset()
    pending = [(0, 0, 0, (0, 0, 0), 0, initial)]
    seen = {initial}
    sequence = count(1)
    best_prefix = -1
    stalled = 0
    while pending:
        _, _, _, _, _, alternatives = heappop(pending)
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
                affects_wave = (len(callers[root_file]) > 1 or children.get(root_file)
                                or len(lookup_sites[path]) > 1)
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
        wave_pairs = set()
        if not any(parent.as_posix() in phantoms for path in phantoms for parent in PurePosixPath(path).parents):
            reached, bindings, problems = _walk_includes(root, disk_lookup, load_archived, scope, {}, {}, historical,
                                                         load_order=verified_order, wave_pairs=wave_pairs)
            if (not problems and reached == archive_inventory
                    and (expected is None or verified_order == expected)
                    and (expected_bindings is None or bindings == expected_bindings)):
                if load_order is not None:
                    load_order[:] = verified_order
                return reached, bindings, problems
        prefix = len(verified_order)
        if expected is not None:
            prefix = next((i for i, (actual, wanted) in enumerate(zip(verified_order, expected))
                           if actual != wanted), prefix)
        if prefix > best_prefix:
            best_prefix, stalled = prefix, 0
        else:
            stalled += 1
            if stalled >= _MAX_8E85_STALLED_WALKS:
                return None
        # A shared target entirely within the matched prefix is harmless when
        # neither its callers nor any pending choice need it after that prefix.
        matched = set(verified_order[:prefix])
        relevant = frontier_ancestors(expected[prefix]) if expected is not None and prefix < len(expected) else set()
        positions = {path: index for index, path in enumerate(verified_order)}
        wave_targets = {target for pair in wave_pairs
                        if expected_bindings is not None
                        or any(path not in matched or load(path).include_directives for path in pair)
                        for target in pair}
        for fallback_order, (path, target) in enumerate(fallback.items()):
            if (all(site[0] in matched for site in lookup_sites[path])
                    and isolated_prefix(target, matched, wave_targets)):
                continue
            candidate = alternatives | {path}
            if candidate not in seen:
                seen.add(candidate)
                # Downstream directives can change wave order. Interleave both
                # ends of discovery order within each tier.
                priority = (not bool(load(target).include_directives),
                            min(fallback_order, len(fallback) - 1 - fallback_order), fallback_order)
                # Explore alternatives that can reach the first missing file
                # before unrelated branches, using the latest visited target.
                predicted_prefix = prefix + (target in relevant)
                position = -positions.get(target, 0) if target in relevant else 0
                heappush(pending, (-predicted_prefix, len(candidate), position, priority, next(sequence), candidate))
    return None


def _walk_includes(root, lookup, load, scope, selected, recovered, historical, *, load_order=None, deduce_sibling=None,
                   wave_pairs=None, verify_disk=False):
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
                        and root_file is not None and root_file not in reached and sibling is None
                        and not (historical == "ac0" and len(relative.parts) > 1)):
                    sibling = deduce_sibling(sibling_path, root_file)
                if root_file and sibling and root_file != sibling:
                    if key in selected and not verify_disk:
                        target = selected[key]
                        if historical in ("8fe", "987", "241") or (root_file in chain) != (sibling in chain):
                            follow(owner, directive, target, chain)
                        else:
                            pending.append((owner, directive, root_file, sibling, chain, target))
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
                        pending.append((owner, directive, root_file, sibling, chain, None))
                        if wave_pairs is not None:
                            wave_pairs.add((root_file, sibling))
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
        for owner, directive, root_file, sibling, chain, recorded_target in batch:
            target = recorded_target or (sibling if root_file in unambiguous_reached
                                         and sibling not in unambiguous_explicit else root_file)
            follow(owner, directive, target, chain)
    return reached, bindings, problems
