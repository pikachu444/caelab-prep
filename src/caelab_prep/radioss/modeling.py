"""Small native writers for supported modelling commands; no example-deck dependency.

Formats: Altair Radioss 2024 /MAT/LAW1, /PROP/TYPE1 and /PART reference pages.
https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/mat_law1_elast_starter_r.htm
https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/prop_type1_shell_starter_r.htm
https://2024.help.altair.com/2024/hwsolvers/rad/topics/solvers/rad/part_starter_r.htm
"""
import math
import re

from ..cae_core.errors import PrepError


def native_identity(keyword):
    words = keyword.strip().upper().split("/")
    if len(words) >= 4 and words[1] in ("MAT", "PROP") and words[3].isdigit():
        return words[1], int(words[3])
    if (len(words) in (3, 4) and words[1] == "PART" and words[2].isdigit()
            and (len(words) == 3 or words[3].isdigit())):
        return "PART", int(words[2])
    return None


def title(name):
    if (not isinstance(name, str) or not name.strip() or name.startswith(("/", "#"))
            or any(c in name for c in "\r\n\x00")):
        raise PrepError("invalid_name", "A nonempty single-line card name is required.")
    data = name.encode("utf-8")
    if len(data) > 100:
        raise PrepError("invalid_name", "The native card title must fit in 100 bytes.")
    return data.decode("latin1")


def real(value, *, positive=False, poisson=False):
    try:
        if isinstance(value, bool): raise ValueError()
        value = float(value)
        if not math.isfinite(value) or (positive and value <= 0) or (poisson and not -1 < value < .5):
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        raise PrepError("invalid_value", "Use finite values: density, modulus and thickness > 0; -1 < Poisson ratio < 0.5.") from None
    text = repr(value)
    if len(text) > 20:
        text = format(value, ".12E")
    if len(text) > 20:
        raise PrepError("field_overflow", "The value does not fit a native field.")
    return text.rjust(20)


def integer(value):
    if type(value) is not int or not 1 <= value <= 9999999999:
        raise PrepError("invalid_native_id", "Native IDs must be positive integers fitting ten columns.")
    return f"{value:10d}"


def material_block(identifier, name, density, young_modulus, poisson_ratio, *, newline="\n"):
    integer(identifier)
    return newline.join((f"/MAT/LAW1/{identifier}", title(name), real(density, positive=True),
                         real(young_modulus, positive=True) + real(poisson_ratio, poisson=True), ""))


def shell_block(identifier, name, thickness, *, newline="\n"):
    """Explicit QEPH elastic-shell profile; existing properties are never regenerated."""
    integer(identifier)
    return newline.join((f"/PROP/SHELL/{identifier}", title(name),
        f"{24:10d}{4:10d}{2:10d}{2:10d}" + " " * 20 + real(1) + " " * 20,
        real(0) * 4 + real(.015),
        f"{0:10d}" + " " * 10 + real(thickness, positive=True) + real(5 / 6) + f"{2:10d}{0:10d}", ""))


def copy_block(text, identifier, *, name=None, newline="\n"):
    integer(identifier)
    lines = text.splitlines(keepends=True)
    if not lines:
        raise PrepError("invalid_card", "The source card is empty.")
    words = lines[0].strip().split("/")
    if len(words) < 4 or words[1].upper() not in ("MAT", "PROP"):
        raise PrepError("unsupported_operation", "Only material and property cards can be copied.")
    ending = "\r\n" if lines[0].endswith("\r\n") else "\n" if lines[0].endswith("\n") else "\r" if lines[0].endswith("\r") else newline
    words[3] = str(identifier)
    lines[0] = "/".join(words) + ending
    if any(re.match(r"^\s*#(?:include|enddata)\b", line, re.I) for line in lines):
        raise PrepError("unsupported_operation", "A card containing file directives cannot be copied.")
    if name is not None:
        index = next((i for i, line in enumerate(lines[1:], 1) if line.strip() and not line.lstrip().startswith("#")), None)
        if index is None:
            raise PrepError("invalid_card", "The source card has no title.")
        old = lines[index]
        ending = "\r\n" if old.endswith("\r\n") else "\n" if old.endswith("\n") else "\r" if old.endswith("\r") else newline
        lines[index] = title(name) + ending
    result = "".join(lines)
    return result if result.endswith(("\r", "\n")) else result + newline
