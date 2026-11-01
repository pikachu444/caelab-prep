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
    index = {"MAT": 3, "PROP": 3, "PART": 2, "FUNCT": 2, "GRNOD": 3,
             "SURF": 3, "BCS": 2, "CLOAD": 2, "INIVEL": 3, "INTER": 3, "TABLE": 3}.get(words[1] if len(words) > 1 else "")
    if index is not None and len(words) > index and words[index].isdigit():
        if words[1] == "PART" and (len(words) not in (3, 4) or (len(words) == 4 and not words[3].isdigit())):
            return None
        return ("FUNCT" if words[1] == "TABLE" else words[1]), int(words[index])
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
        f"{0:10d}" + " " * 10 + real(thickness, positive=True) + real(5 / 6) + " " * 10 + f"{2:10d}{0:10d}", ""))


def copy_block(text, identifier, *, name=None, newline="\n"):
    integer(identifier)
    lines = text.splitlines(keepends=True)
    if not lines:
        raise PrepError("invalid_card", "The source card is empty.")
    words = lines[0].strip().split("/")
    identity = native_identity(lines[0])
    if identity is None:
        raise PrepError("unsupported_operation", "This native identity cannot be copied.")
    ending = "\r\n" if lines[0].endswith("\r\n") else "\n" if lines[0].endswith("\n") else "\r" if lines[0].endswith("\r") else newline
    index = 2 if words[1].upper() in ("PART", "FUNCT", "BCS", "CLOAD") else 3
    words[index] = str(identifier)
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


def curve_points(points):
    """Application profile: at least two finite points, strictly increasing X."""
    if not isinstance(points, (list, tuple)) or len(points) < 2:
        raise PrepError("invalid_curve", "A curve requires at least two X/Y points.")
    rows, previous = [], None
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise PrepError("invalid_curve", "Each curve point requires X and Y.")
        row = real(point[0]) + real(point[1])
        x = float(row[:20])
        if previous is not None and x <= previous:
            raise PrepError("invalid_curve", "Curve X values must be strictly increasing.")
        previous = x
        rows.append(row)
    return rows


def curve_block(identifier, name, points, *, newline="\n"):
    integer(identifier)
    return newline.join([f"/FUNCT/{identifier}", title(name), *curve_points(points), ""])


def member_block(keyword, identifier, name, members, *, newline="\n"):
    integer(identifier)
    fields = [integer(member) for member in members]
    return newline.join([f"/{keyword}/{identifier}", title(name),
                         *["".join(fields[i:i + 10]) for i in range(0, len(fields), 10)], ""])


def bool_vector(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3 or any(type(item) is not bool for item in value):
        raise PrepError("invalid_value", "Choose three Boolean degrees of freedom.")
    return "".join("1" if item else "0" for item in value)


def boundary_block(identifier, name, group, translations, rotations, *, newline="\n"):
    integer(identifier)
    row = "   " + bool_vector(translations) + " " + bool_vector(rotations) + f"{0:10d}" + integer(group)
    return newline.join((f"/BCS/{identifier}", title(name), row, ""))


def load_block(identifier, name, group, curve, direction, scale, *, newline="\n"):
    integer(identifier)
    if direction not in ("X", "Y", "Z", "XX", "YY", "ZZ"):
        raise PrepError("invalid_value", "Load direction must be X, Y, Z, XX, YY or ZZ.")
    row = integer(curve) + f"{direction:>10}{0:10d}{0:10d}" + integer(group) + " " * 10 + real(1) + real(scale)
    return newline.join((f"/CLOAD/{identifier}", title(name), row, ""))


def velocity_block(identifier, name, group, velocity, *, newline="\n"):
    integer(identifier)
    if not isinstance(velocity, (list, tuple)) or len(velocity) != 3:
        raise PrepError("invalid_value", "Initial velocity requires three finite components.")
    row = "".join(real(value) for value in velocity) + integer(group) + f"{0:10d}"
    return newline.join((f"/INIVEL/TRA/{identifier}", title(name), row, ""))


def contact_block(identifier, name, secondary, main, friction, *, newline="\n"):
    """Radioss 2024 TYPE7 penalty contact, shell variable-gap profile.

    Official inter_type7_starter_r.htm and radioss2024 INTER/inter_type7.cfg.
    Explicit supported settings avoid inheritance from /DEFAULT/INTER/TYPE7.
    """
    integer(identifier)
    friction_field = real(friction)
    if float(friction) < 0:
        raise PrepError("invalid_value", "Friction must be finite and nonnegative.")
    rows = [integer(secondary) + integer(main) + f"{1000:10d}{0:10d}{1:10d}" + " " * 10 + f"{0:10d}{1000:10d}{0:10d}{0:10d}",
            real(1) + real(0) * 2 + " " * 20 + f"{0:10d}",
            real(0) + real(1e30) + real(.4) + real(0) + f"{1:10d}{3:10d}",
            real(1) + friction_field + real(0) * 2 + real(1e30),
            "       000" + " " * 20 + f"{1000:10d}" + real(.05) + real(1) + real(.2),
            f"{0:10d}{0:10d}" + real(0) + f"{2:10d}{0:10d}{0:10d}" + real(1) + f"{0:10d}"]
    return newline.join([f"/INTER/TYPE7/{identifier}", title(name), *rows, ""])


def solid_block(identifier, name, *, newline="\n"):
    """2024 TYPE14 explicit linear tetra4 profile, verified with Starter/Engine.

    prop_type14_solid_starter_r.htm; FORMAT(radioss2023) prop_p14_solid.cfg.
    """
    integer(identifier)
    return newline.join([f"/PROP/SOLID/{identifier}", title(name),
        "".join(f"{value:10d}" for value in (1, 4, 0, 0, 0, 0, 1000, 1)) + real(0),
        "".join(real(value) for value in (1.1, .05, .1, 0, 0)), real(0) * 5, ""])


def engine_input(run_name, end_time, output_interval):
    """One explicit run with animation output, in the Starter's working units."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_name):
        raise PrepError("invalid_export_name", "Use an ASCII solver basename containing letters, numbers, _, - or . only.")
    end = real(end_time, positive=True).strip()
    interval = real(output_interval, positive=True).strip()
    if float(interval) > float(end):
        raise PrepError("invalid_value", "Output interval must not exceed the end time.")
    return f"#RADIOSS ENGINE\n/RUN/{run_name}/1\n{end}\n/ANIM/DT\n0 {interval}\n".encode("ascii")
