"""Resolve Starter INCLUDE graphs against disk or a portable file inventory."""
from collections import defaultdict, deque
from functools import cache
from pathlib import PurePosixPath

from ..cae_core import PrepError


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


def resolve_includes(root, lookup, load, *, scope="", archive_inventory=None, selected=None, recovered=None):
    """Resolve live paths or replay validated bindings against an archive inventory."""
    selected, recovered = selected or {}, recovered or {}
    result = _walk_includes(root, lookup, load, scope, selected, recovered, legacy_pending=False)
    if archive_inventory is not None and not result[2] and archive_inventory - result[0]:
        # ac0a255d let an earlier ambiguous directive claim the root for the
        # next directive. Use that policy only if it explains the entire ZIP.
        historical = _walk_includes(root, lookup, load, scope, selected, recovered, legacy_pending=True)
        if not historical[2] and historical[0] == archive_inventory:
            return historical
    return result


def _walk_includes(root, lookup, load, scope, selected, recovered, *, legacy_pending):
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
        chain = (*ancestors, owner)
        directory = PurePosixPath(owner).parent
        for ordinal, directive in enumerate(directives):
            try:
                relative = include_relative(directive.path)
                logical = relative.as_posix()
                # Archived imports have their own original root. A converted
                # path that already names that namespace stays project-relative.
                scoped = scope and not logical.casefold().startswith(scope.casefold() + "/")
                root_path = f"{scope}/{logical}" if scoped else logical
                sibling_path = (directory / relative).as_posix()
                root_file = lookup(root_path)
                sibling = lookup(sibling_path) if sibling_path != root_path else root_file
                key = owner, ordinal
                if key in recovered:
                    follow(owner, directive, recovered[key], chain)
                    continue
                if key in selected and selected[key] not in (root_file, sibling):
                    raise PrepError("invalid_project", "A recorded INCLUDE binding does not match its native directive.",
                                    {"path": logical, "target": selected[key]})
                if not (root_file or sibling):
                    raise PrepError("include_missing", "INCLUDE 파일이 없습니다.", {"path": logical})
                if root_file and sibling and root_file != sibling:
                    if key in selected:
                        follow(owner, directive, selected[key], chain)
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
    while pending:
        unambiguous_reached = reached if legacy_pending else reached.copy()
        unambiguous_explicit = explicit if legacy_pending else explicit.copy()
        batch = [pending.popleft() for _ in range(1 if legacy_pending else len(pending))]
        for owner, directive, root_file, sibling, chain in batch:
            target = sibling if root_file in unambiguous_reached and sibling not in unambiguous_explicit else root_file
            follow(owner, directive, target, chain)
    return reached, bindings, problems
