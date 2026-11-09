def mesh_view(self, *, mutable: bool = False) -> dict:
    """Return shared, nested read-only geometry plus current small stamps.

    Geometry identity is stable until a structural command, Undo/Redo of
    that command, or document replacement. ``mutable=True`` explicitly
    materializes detached lists/dicts for editing or JSON serialization.
    Neither form permits mutations of the document through this view.
    """
    with self._lock:
        document = self._require()
        if self._projection_cache is None:
            _n17_t = _n17_clock()
            nodes: dict[int, list[float]] = {}; node_resources: dict[int, list[str]] = {}; cells = []; diagnostics = []
            for resource in self._deck_resources(document):
                projection = resource.mesh_projection()
                for identifier, point in zip(projection["node_ids"], projection["points"]):
                    node_resources.setdefault(identifier, []).append(resource.id)
                    if identifier in nodes:
                        diagnostics.append({"severity": "warning", "code": "duplicate_global_node_id",
                            "message": f"INCLUDE 전체에서 절점 ID {identifier}가 중복돼 표시가 부분적입니다."})
                    else:
                        nodes[identifier] = point
                cells.extend(projection["cells"]); diagnostics.extend(projection["diagnostics"])
            _n17_mark("native_parse_and_merge", _n17_t)
            _n17_t = _n17_clock()
            valid = []
            for cell in cells:
                if all(node in nodes for node in cell["nodes"]):
                    valid.append(cell)
                else:
                    diagnostics.append({"severity": "warning", "code": "missing_display_nodes",
                        "message": f"요소 {cell['id']}의 참조 절점이 없어 표시하지 못했습니다."})
            identifiers = sorted(nodes)
            _n17_mark("validate_connectivity_and_sort_nodes", _n17_t)
            _n17_t = _n17_clock()
            parts = {}
            for resource in self._deck_resources(document):
                for card in resource.cards:
                    identity = native_identity(card.keyword)
                    if identity and identity[0] == "PART":
                        parts.setdefault(identity[1], []).append((resource.id, card))
            part_refs = {identifier: readonly({"resource_id": matches[0][0], "native_scope": matches[0][1].keyword})
                         for identifier,matches in parts.items() if len(matches)==1}
            for cell in valid: cell["part_ref"] = part_refs.get(cell.get("part_id"))
            _n17_mark("shared_part_reference_resolution", _n17_t)
            _n17_t = _n17_clock()
            cache = freeze_mesh_payload(points=(nodes[i] for i in identifiers), node_ids=identifiers,
                cells=valid, diagnostics=diagnostics, document_id=document.id, node_resources=node_resources)
            _n17_mark("owned_payload_seal", _n17_t)
            _n17_t = _n17_clock()
            by_id, by_part = {}, {}
            for cell in cache["cells"]:
                by_id[cell["id"]] = (*by_id.get(cell["id"], ()), cell)
                by_part.setdefault(cell.get("part_id"), []).append(cell)
            self._projection_cache = cache
            self._projection_index = {"cells_by_id": by_id, "cells_by_part": by_part}
            _n17_mark("index_build", _n17_t)
        result = {**self._projection_cache, "revision": document.revision,
                "document_epoch": self._document_epoch, "projection_revision": self._projection_revision,
                "resource_revisions": readonly({key: resource.state_token() for key, resource in document.resources.items()})}
        if mutable:
            result = mutable_projection(result)
            result["immutable_projection"] = False
        return result
