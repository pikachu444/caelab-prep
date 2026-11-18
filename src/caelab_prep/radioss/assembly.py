"""Explicit native-ID remapping for a closed, inspectable assembly profile.

Independent inputs never share a native namespace implicitly. This codec
creates new include payloads; it does not mutate the source deck or weaken
DeckResource's source-header safeguards. Unsupported reference-bearing cards
are rejected before any document mutation.
"""
from ..cae_core import PrepError
from .includes import include_lookup, resolve_includes
from .modeling import ELEMENT_ALIASES, native_identity
from .relations import element_group_members


ELEMENTS = {"BEAM": 3, "TRUSS": 2, "SHELL": 4, "QUAD": 4, "SH3N": 3, "TETRA4": 4, "BRICK": 8}
ELEMENT_NAMESPACE = {"BEAM": "BEAM", "TRUSS": "TRUSS", "SHELL": "SHELL", "QUAD": "QUAD",
                     "SH3N": "SH3N", "TETRA4": "SOLID", "BRICK": "SOLID"}
ELEMENTS.update({alias: ELEMENTS[family] for alias, family in ELEMENT_ALIASES.items()})
ELEMENT_NAMESPACE.update({alias: ELEMENT_NAMESPACE[family] for alias, family in ELEMENT_ALIASES.items()})
GROUPS = {"GRNOD/NODE": "NODE", "GRBEAM/BEAM": "E:BEAM", "GRTRUS/TRUS": "E:TRUSS",
          "GRSHEL/SHEL": "E:SHELL", "GRQUAD/QUAD": "E:QUAD", "GRSH3N/SH3N": "E:SH3N", "GRBRIC/BRIC": "E:SOLID", "SURF/PART": "PART"}
REFERENCE_FREE_PAIRS = {"MAT/LAW1", "MAT/ELAST", "PROP/BEAM", "PROP/TYPE3", "PROP/TRUSS", "PROP/TYPE2",
                        "PROP/SHELL", "PROP/TYPE1", "PROP/SOLID", "PROP/TYPE14", "SKEW/FIX"}
PAIRS = REFERENCE_FREE_PAIRS | {"INIVEL/TRA", "INTER/TYPE7"} | set(GROUPS)


def identity(keyword):
    words = keyword.strip().upper().split("/")
    if len(words) >= 4 and words[1] in ("SKEW", "FRAME", "GRBEAM", "GRTRUS") and words[3].isdigit():
        return ("SKEW" if words[1] in ("SKEW", "FRAME") else words[1]), int(words[3])
    return native_identity(keyword)


def _int(text, *, zero=False):
    try:
        value = int(text.strip() or "0")
        if value < (0 if zero else 1): raise ValueError()
        return value
    except ValueError:
        raise PrepError("unsupported_source_profile", "Expected a positive fixed-width native ID.", {"field": text}) from None


def element_node_references(family, line):
    """Include BEAM's optional direction node as a native reference."""
    fields = []
    for index in range(1, ELEMENTS[family] + 1):
        value = _int(line[index * 10:(index + 1) * 10], zero=family == "BEAM" and index == 3)
        if value: fields.append((index * 10, value))
    return tuple(fields)


def element_part_reference(keyword):
    words = keyword.strip("/").split("/")
    if len(words) != 2:
        raise PrepError("unsupported_source_units", "Element unit overrides are not supported.")
    return _int(words[1])


def _inspect(resources):
    """Collect definitions and fixed-width references, retaining file ownership."""
    definitions, refs, edits, omitted = {}, [], {}, {}
    def define(ns, value, rid, line, start=None):
        key = (ns, value)
        if key in definitions:
            raise PrepError("ambiguous_source_id", "IDs must be unique within the source native namespace.", {"namespace": ns, "id": value})
        definitions[key] = (rid, line)
        if start is not None: edits.setdefault(rid, []).append((line, start, ns, value))
    def reference(ns, value, rid, line, start, zero=False):
        if zero and value == 0: return
        refs.append((ns, value)); edits.setdefault(rid, []).append((line, start, ns, value))
    for resource in resources:
        rid, lines = resource.id, resource.render().decode("latin1").splitlines(keepends=True)
        omitted[rid] = set()
        for card in resource.cards:
            words = card.keyword.upper().strip("/").split("/"); root = words[0]; pair = "/".join(words[:2])
            if root not in {"BEGIN", "END", "NODE", "PART", "FUNCT", "BCS", "CLOAD", *ELEMENTS} and pair not in PAIRS:
                raise PrepError("unsupported_source_profile", "This card's complete reference mapping is not supported.", {"keyword": card.keyword})
            header_id = identity(card.keyword)
            if root == "NODE" and len(words) != 1:
                raise PrepError("unsupported_source_units", "NODE unit overrides are not supported by this mapping profile.")
            expected_segments = 2 if root in ("PART", "FUNCT", "BCS", "CLOAD") else 3
            if header_id and len(words) != expected_segments and not (root=="PART" and len(words)==3 and words[-1]=="0"):
                raise PrepError("unsupported_source_units", "Per-card unit overrides are not remapped by this profile.", {"keyword": card.keyword})
            if root in ("BEGIN", "END"):
                omitted[rid].update((card.start, *card.data)); continue
            if header_id: define(*header_id, rid, card.start)
            if root == "NODE":
                for row in card.data: define("NODE", _int(lines[row][:10]), rid, row, 0)
            elif root in ELEMENTS:
                reference("PART", element_part_reference(card.keyword), rid, card.start, -1)
                for row in card.data:
                    define("E:" + ELEMENT_NAMESPACE[root], _int(lines[row][:10]), rid, row, 0)
                    for start, identifier in element_node_references(root, lines[row]):
                        reference("NODE", identifier, rid, row, start)
            elif root == "PART":
                if len(card.data) != 2: raise PrepError("unsupported_source_profile", "PART requires the standard title and assignment row.")
                row = card.data[1]
                reference("PROP", _int(lines[row][:10]), rid, row, 0)
                reference("MAT", _int(lines[row][10:20]), rid, row, 10)
                if _int(lines[row][20:30], zero=True):
                    raise PrepError("unsupported_source_profile", "SUBSET references require a separate mapping profile.")
            elif pair in GROUPS:
                namespace = GROUPS[pair]
                entries = []
                for row in card.data[1:]:
                    for start in range(0, len(lines[row].rstrip("\r\n")), 10):
                        token = lines[row][start:start + 10].strip()
                        if token:
                            value = -_int(token[1:]) if namespace.startswith("E:") and token.startswith("-") else _int(token)
                            entries.append((row, start, value))
                effective = set(element_group_members([value for _, _, value in entries]))
                for row, start, value in entries:
                    if value in effective:
                        reference(namespace, value, rid, row, start)
                    else:
                        edits.setdefault(rid, []).append((row, start, namespace, value))
            elif root == "BCS":
                row = card.data[1]
                reference("SKEW", _int(lines[row][10:20], zero=True), rid, row, 10, True)
                reference("GRNOD", _int(lines[row][20:30]), rid, row, 20)
            elif root == "CLOAD":
                row = card.data[1]
                for ns, start, zero in (("FUNCT", 0, False), ("SKEW", 20, True), ("GRNOD", 40, False)):
                    reference(ns, _int(lines[row][start:start + 10], zero=zero), rid, row, start, zero)
                if _int(lines[row][30:40], zero=True): raise PrepError("unsupported_source_profile", "CLOAD sensor activation is outside this profile.")
            elif pair == "INIVEL/TRA":
                row = card.data[1]
                reference("GRNOD", _int(lines[row][60:70]), rid, row, 60)
                reference("SKEW", _int(lines[row][70:80], zero=True), rid, row, 70, True)
            elif pair == "INTER/TYPE7":
                row = card.data[1]
                # Curvature, sensor and temperature-function options are not
                # silently remapped; the initial profile is the explicit writer.
                if len(card.data) != 7 or any(_int(lines[row][s:s + 10], zero=True) for s in (60, 80, 90)):
                    raise PrepError("unsupported_source_profile", "TYPE7 import supports the explicit non-curved, no-sensor profile.")
                reference("GRNOD", _int(lines[row][:10]), rid, row, 0)
                reference("SURF", _int(lines[row][10:20]), rid, row, 10)
                last = lines[card.data[6]]
                # Row 6: Ifric, Ifiltr, Xfreq(20), Iform, sens_ID,
                # fct_ID_F, Ascale_F(20), fric_ID. The scale is real data,
                # never an ID; all unimplemented function/friction refs block.
                if any(_int(last[s:s + 10], zero=True) for s in (0, 10, 50, 60, 90)):
                    raise PrepError("unsupported_source_profile", "TYPE7 function/sensor options require their own mapping profile.")
    missing = sorted(set(refs) - set(definitions))
    if missing:
        raise PrepError("dangling_source_reference", "The source contains unresolved native references.", {"references": missing})
    return definitions, edits, omitted


def inspect(resources):
    try:
        return _inspect(resources)
    except (IndexError, ValueError, TypeError) as exc:
        raise PrepError("unsupported_source_profile", "A supported source card has malformed fixed-width data.", {"reason": str(exc)}) from exc


def source_include_graph(resources, paths):
    by_path = {resource.name: resource for resource in resources}
    root = next(resource.name for resource in resources if not resource.is_include)
    return resolve_includes(root, include_lookup(paths), by_path.__getitem__, archive_inventory=set(paths))


def remap(resources, mappings, paths, *, two_line="quoted", legacy_direct_inline: bool = False):
    definitions, edits, omitted = inspect(resources)
    reached, bindings, problems = source_include_graph(resources, paths)
    if problems or (not legacy_direct_inline and reached != set(paths)):
        raise PrepError("include_missing", "The imported INCLUDE graph could not be resolved.")
    result = {}
    for resource in resources:
        lines = resource.render().decode("latin1").splitlines(keepends=True)
        for card in resource.cards:
            original = identity(card.keyword)
            if original:
                words = card.keyword.split("/"); index = 2 if words[1].upper() in ("PART", "FUNCT", "BCS", "CLOAD") else 3
                words[index] = str(mappings[original]); ending = lines[card.start][len(lines[card.start].rstrip("\r\n")):]
                lines[card.start] = "/".join(words) + ending
        for line, start, namespace, value in edits.get(resource.id, []):
            mapped = mappings.get((namespace, abs(value)))
            if value < 0 and mapped is not None:
                mapped = -mapped
            if start == -1:
                ending = lines[line][len(lines[line].rstrip("\r\n")):]
                words = lines[line].strip().split("/"); words[2] = str(mapped); lines[line] = "/".join(words) + ending
            else:
                body = lines[line].rstrip("\r\n"); ending = lines[line][len(body):]
                field = f"{mapped:10d}" if mapped is not None else " " * 10
                lines[line] = body.ljust(start + 10)[:start] + field + body[start + 10:] + ending
        for directive in resource.include_directives:
            multiline = directive.filename_row != directive.header_row
            if multiline and two_line == "unchanged":
                continue
            original = bindings.get((resource.name, directive.header_row))
            if legacy_direct_inline and not multiline:
                direct = directive.path.replace("\\", "/")
                if direct in paths:
                    original = direct
            if original is None:
                raise PrepError("include_missing", "The imported INCLUDE directive could not be resolved.")
            directive.replace_path(lines, paths[original], preserve_quotes=multiline and two_line == "quoted")
        # Explicitly shared nodes live in the destination resource only.
        shared = {line for (namespace, identifier), (rid, line) in definitions.items()
                  if rid == resource.id and namespace == "NODE" and (namespace, identifier) in mappings.shared}
        result[resource.id] = "".join(line for index, line in enumerate(lines) if index not in omitted[resource.id] | shared).encode("latin1")
    return result


class NativeMap(dict):
    def __init__(self, values=(), *, shared=()):
        super().__init__(values); self.shared = frozenset(shared)
