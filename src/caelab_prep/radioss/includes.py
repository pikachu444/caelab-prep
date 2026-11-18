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


def disk_include_lookup(base):
    @cache
    def lookup(path):
        candidate = base / path
        if candidate.is_file():
            return candidate.resolve().relative_to(base).as_posix()
        matches = [base]
        for part in PurePosixPath(path).parts:
            matches = [child for parent in matches if parent.is_dir() for child in parent.iterdir()
                       if child.name.casefold() == part.casefold()]
            if not matches:
                break
        files = [candidate for candidate in matches if candidate.is_file()]
        if len(files) == 1:
            return files[0].resolve().relative_to(base).as_posix()
        return None

    return lookup


def resolve_includes(root, lookup, load, *, scope=""):
    """Return reachable files, directive bindings, and unresolved references."""
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
        for directive in directives:
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
                if not (root_file or sibling):
                    raise PrepError("include_missing", "INCLUDE 파일이 없습니다.", {"path": logical})
                if len(relative.parts) == 1 and root_file and sibling and root_file != sibling:
                    if (root_file in chain) != (sibling in chain):
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
    # Resolve all direct and qualified claims before ambiguous bare names,
    # regardless of their order in the Starter or intermediate includes.
    while pending:
        owner, directive, root_file, sibling, chain = pending.popleft()
        target = sibling if root_file in reached and sibling not in explicit else root_file
        follow(owner, directive, target, chain)
    return reached, bindings, problems
