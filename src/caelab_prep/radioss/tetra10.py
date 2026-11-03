"""The native TETRA10 two-row record; midsides are in Radioss order."""
from ..cae_core.errors import PrepError


def records(lines, data):
    if len(data) % 2:
        raise PrepError("invalid_tetra10", "TETRA10 requires an element-ID row and a ten-node row.")
    result = []
    try:
        for position in range(0, len(data), 2):
            id_row, node_row = data[position:position + 2]
            first, second = lines[id_row].rstrip("\r\n"), lines[node_row].rstrip("\r\n")
            identifier = int(first[:10])
            nodes = tuple(int(second[index:index + 10]) for index in range(0, 100, 10))
            if (identifier <= 0 or first[10:].strip() or second[100:].strip()
                    or any(node <= 0 for node in nodes) or len(set(nodes)) != 10):
                raise ValueError()
            result.append((identifier, nodes, id_row, node_row))
    except (ValueError, IndexError):
        raise PrepError("invalid_tetra10", "Invalid fixed-width TETRA10 ID or ten-node record.") from None
    return tuple(result)
