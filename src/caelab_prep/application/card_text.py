"""Native field text drafts; providers still own validation and publication."""
from copy import copy
from dataclasses import dataclass, field, replace

from ..cae_core import PrepError
from ..radioss.modeling import native_identity
from .contracts import ObjectRef


def _lines(text):
    return [(line.rstrip("\r\n"), line[len(line.rstrip("\r\n")):])
            for line in text.splitlines(keepends=True)]


def _logical_values(target, values, specs):
    keyword = target.native_scope.upper()
    if keyword.startswith("/PART/"):
        result = {}
        for native, logical, namespace in (("property_id", "property", "PROP"),
                                           ("material_id", "material", "MAT")):
            if native not in values or logical not in specs:
                raise PrepError("unsupported_card_text", "The PART assignment fields are incomplete.")
            matches = [ref for ref in specs[logical].choices if isinstance(ref, ObjectRef)
                       and native_identity(ref.native_scope) == (namespace, values[native])]
            if len(matches) != 1:
                raise PrepError("invalid_reference", "The native assignment must resolve to one supported object.",
                                {"field": logical, "native_id": values[native]})
            result[logical] = matches[0]
    elif keyword.startswith("/FUNCT/"):
        result = {"points": tuple((values[f"point_{i}_x"], values[f"point_{i}_y"])
                                  for i in range(len(values) // 2))}
    elif keyword.startswith("/INIVEL/TRA/"):
        result = {"velocity": tuple(values[name] for name in ("vx", "vy", "vz"))}
    elif keyword.startswith("/BCS/"):
        result = {"translations": tuple(values[name] for name in ("tx", "ty", "tz")),
                  "rotations": tuple(values[name] for name in ("rx", "ry", "rz"))}
    else:
        result = dict(values)
    if any(name not in specs or not specs[name].editable for name in result):
        raise PrepError("unsupported_card_text", "Native fields do not match editable provider properties.")
    # TEXT values are already in the native basis, never the current UI unit.
    if any(specs[name].unit_scales and dict(specs[name].unit_scales).get(specs[name].unit) != 1
           for name in result):
        raise PrepError("unsupported_card_text", "The provider default unit is not the native numeric basis.")
    return result


def _context(provider, target):
    card_info = provider._card(target)
    resource = provider.session._find_card(target.object_id)
    card = resource.card(target.object_id)
    fields = tuple(replace(item, line=item.line - card.start) for item in resource._schema(card))
    if not fields:
        raise PrepError("unsupported_card_text", "This card has no supported native text fields.")
    if card_info["keyword"].upper().startswith("/FUNCT/"):
        expected = {f"point_{i}_{axis}" for i in range(len(card.data) - 1) for axis in ("x", "y")}
        if {item.name for item in fields} != expected:
            raise PrepError("unsupported_card_text", "Every original curve field must be readable.")
    baseline = provider.session.card_text(target.object_id)
    reader = copy(resource)
    reader.lines = baseline.splitlines(keepends=True)
    if card_info["keyword"].upper().startswith("/FUNCT/"):
        for index in {item.line for item in fields}:
            body, ending = _lines(reader.lines[index])[0]
            if len(body) > 40 or not ending:
                raise PrepError("unsupported_card_text", "The existing curve writer cannot retain this numeric-row suffix or missing line ending.")
    if card_info["keyword"].upper().startswith("/BCS/"):
        positions = {"tx": 3, "ty": 4, "tz": 5, "rx": 7, "ry": 8, "rz": 9}
        if ({item.name for item in fields} != positions.keys()
                or any(item.start != positions[item.name] for item in fields)):
            raise PrepError("unsupported_card_text", "The existing boundary writer requires its supported boolean alignment.")
        line = reader.lines[fields[0].line]
        if line[:3] != "   " or line[6:7] != " ":
            raise PrepError("unsupported_card_text", "The existing boundary writer cannot retain this boolean padding.")
    specs = {spec.name: spec for spec in provider.properties(target)}
    values = {item.name: reader._read_field(item) for item in fields}
    logical = _logical_values(target, values, specs)
    if any(value != specs[name].value for name, value in logical.items()):
        raise PrepError("unsupported_card_text", "Native and provider field values do not match.")
    return baseline, fields, reader, specs, logical


@dataclass(frozen=True)
class CardTextDraft:
    target: ObjectRef
    document_epoch: str
    revision: int
    baseline: str
    _fields: tuple = field(repr=False)

    @property
    def ui_text(self):
        """Qt plain-text editors normalize native line endings to LF."""
        return self.baseline.replace("\r\n", "\n").replace("\r", "\n")

    def changes(self, provider, text) -> dict:
        """Return logical native values only; no resource or history is changed."""
        session = provider.session
        with session._lock:
            document = session._require()
            if (document.id != self.target.document_id or session._document_epoch != self.document_epoch
                    or document.revision != self.revision):
                raise PrepError("stale_card_text", "The document changed; keep the draft or reload the current card.")
            try:
                baseline, fields, reader, specs, before = _context(provider, self.target)
            except PrepError as exc:
                raise PrepError("stale_card_text", "The original card is no longer editable.") from exc
            if baseline != self.baseline or fields != self._fields:
                raise PrepError("stale_card_text", "The native card changed while its text was being edited.")
            if not isinstance(text, str):
                raise PrepError("invalid_card_text", "Native card text must be a string.")
            try:
                text.encode("latin1")
            except UnicodeError as exc:
                raise PrepError("invalid_card_text", "Native text must retain the source byte encoding.") from exc
            original, proposed = _lines(baseline), _lines(text)
            if len(original) != len(proposed) or any(bool(a[1]) != bool(b[1]) for a, b in zip(original, proposed)):
                raise PrepError("unsupported_card_text", "Keep every native row and its final line ending.")
            for index, ((old, ending), (new, _)) in enumerate(zip(original, proposed)):
                width = max(len(old), len(new))
                old_mask = list(old) + [None] * (width - len(old))
                new_mask = list(new) + [None] * (width - len(new))
                for item in fields:
                    if item.line == index:
                        start, stop = item.start, min(item.stop, width)
                        if start < stop:
                            old_mask[start:stop] = new_mask[start:stop] = [None] * (stop - start)
                if old_mask != new_mask:
                    raise PrepError("unsupported_card_text", "Only the supported fixed-width fields may change.", {"line": index + 1})
                proposed[index] = new + ending
            candidate = copy(reader)
            candidate.lines = proposed
            values = {}
            for item in fields:
                try:
                    value = candidate._read_field(item)
                    if value != reader._read_field(item):
                        reader._validated_value(item, value)
                    values[item.name] = value
                except (ValueError, IndexError, OverflowError) as exc:
                    raise PrepError("invalid_card_text", "A supported native field is malformed.", {"field": item.name}) from exc
            after = _logical_values(self.target, values, specs)
            return {name: value for name, value in after.items() if value != before[name]}


def prepare_card_text(provider, ref) -> CardTextDraft:
    """Capture one complete current card and its original writable field spans."""
    with provider.session._lock:
        baseline, fields, _, _, _ = _context(provider, ref)
        document = provider.session._require()
        return CardTextDraft(ref, provider.session._document_epoch, document.revision, baseline, fields)
