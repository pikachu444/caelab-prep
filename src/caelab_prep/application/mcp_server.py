"""Optional stdio MCP adapter to an explicitly enabled, already-open GUI owner.

This process owns no PrepSession and imports no Qt, VTK or solver adapter. Every
operation forwards to the authenticated live endpoint and its normal commands.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from .live_transport import LiveClient, LiveRemoteError


def create_server(connection):
    try:
        from mcp.server import MCPServer
        from mcp.types import CallToolResult, TextContent, ToolAnnotations
    except ImportError as exc:
        raise RuntimeError("Install caelab-prep[mcp] to use the optional MCP adapter.") from exc

    client = LiveClient(connection)
    server = MCPServer("CAELab Prep live document", version="1.0", log_level="WARNING",
        instructions="This server controls one already-open Prep GUI document. Query prep_describe and exact typed targets before changes. "
        "Changes require its document_id/document_epoch/revision handle. Never guess native IDs, units or a newer revision. "
        "GUI drafts and modal/busy state are authoritative. A meshing result is a candidate, not an adopted model. "
        "Cancel only your own workflow with its returned capability. Connection failure never opens a replacement document.")
    read = ToolAnnotations(read_only_hint=True, open_world_hint=False)
    # These are not additive-only operations: scalar edits overwrite values and
    # Undo/Redo may remove objects. Advertise the conservative protocol hint.
    edit = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)
    save = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)

    def invoke(method, params=None, request_id=None):
        try:
            result = client.request(method, params or {}, request_id=request_id)
        except LiveRemoteError as exc:
            failure = {"error": {"code": exc.code, "message": exc.message, "details": exc.details}}
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(failure, ensure_ascii=True))],
                                  structured_content=failure, is_error=True)
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=True))],
                              structured_content=result, is_error=False)

    @server.tool(annotations=read, structured_output=False)
    def prep_describe() -> Any:
        """Read the actual open GUI document, complete handle, capabilities and draft/busy status."""
        return invoke("document.describe")

    @server.tool(annotations=read, structured_output=False)
    def prep_cards() -> Any:
        """List the current GUI provider's objects with exact typed references. Do not invent references."""
        return invoke("document.cards")

    @server.tool(annotations=read, structured_output=False)
    def prep_properties(target: dict[str, Any]) -> Any:
        """Read supported field values, kinds and unit choices for a typed reference from prep_cards."""
        return invoke("document.properties", {"target": target})

    @server.tool(annotations=read, structured_output=False)
    def prep_selection() -> Any:
        """Read the canonical selection currently displayed by the GUI."""
        return invoke("document.selection")

    @server.tool(annotations=edit, structured_output=False)
    def prep_select(handle: dict[str, Any], target: dict[str, Any], request_id: str | None = None) -> Any:
        """Select a real GUI object using the complete current handle; pending drafts are preserved and block selection."""
        return invoke("document.select", {"handle": handle, "target": target}, request_id)

    @server.tool(annotations=edit, structured_output=False)
    def prep_edit_scalar(handle: dict[str, Any], target: dict[str, Any], values: dict[str, Any],
                         units: dict[str, str] | None = None, request_id: str | None = None) -> Any:
        """Apply writable number/bool fields as one normal GUI command and one Undo step. Use advertised units; stale handles fail."""
        return invoke("document.edit", {"handle": handle, "target": target, "values": values, "units": units or {}}, request_id)

    @server.tool(annotations=edit, structured_output=False)
    def prep_undo(handle: dict[str, Any], request_id: str | None = None) -> Any:
        """Undo the shared document's last command; requires the current handle and no pending GUI draft."""
        return invoke("document.undo", {"handle": handle}, request_id)

    @server.tool(annotations=edit, structured_output=False)
    def prep_redo(handle: dict[str, Any], request_id: str | None = None) -> Any:
        """Redo the shared document's next command; requires the current handle and no pending GUI draft."""
        return invoke("document.redo", {"handle": handle}, request_id)

    @server.tool(annotations=save, structured_output=False)
    def prep_save(handle: dict[str, Any], path: str, request_id: str | None = None) -> Any:
        """Save the same open document as a .caeprep file at an explicit path; original solver inputs remain protected."""
        return invoke("document.save", {"handle": handle, "path": path}, request_id)

    @server.tool(annotations=read, structured_output=False)
    def prep_events(after: int) -> Any:
        """Read owner session/job events after a sequence; recover an expired cursor with prep_describe."""
        return invoke("events.since", {"after": after})

    @server.tool(annotations=edit, structured_output=False)
    def prep_mesh_start(handle: dict[str, Any], source: str, output: str, size: float,
                        dimension: int, interface_policy: str = "preserve", request_id: str | None = None) -> Any:
        """Start the existing GUI's real CAD mesh-candidate worker. Return workflow ID and private cancel capability; does not adopt a model."""
        return invoke("mesh.start", {"handle": handle, "source": source, "output": output, "size": size,
            "dimension": dimension, "interface_policy": interface_policy}, request_id)

    @server.tool(annotations=read, structured_output=False)
    def prep_job_get(job_id: str) -> Any:
        """Query an existing GUI workflow's generation, real task status, assets and error; no cancellation credential is disclosed."""
        return invoke("jobs.get", {"job_id": job_id})

    @server.tool(annotations=edit, structured_output=False)
    def prep_job_cancel(job_id: str, cancel_token: str, request_id: str | None = None) -> Any:
        """Request cancellation using the creator's workflow capability. Check the later actual status; atomic adoption cannot be cancelled."""
        return invoke("jobs.cancel", {"job_id": job_id, "cancel_token": cancel_token}, request_id)

    @server.tool(annotations=edit, structured_output=False)
    def prep_job_close(job_id: str, cancel_token: str, request_id: str | None = None) -> Any:
        """Close the creator's completed candidate window. Running tasks must finish or be cancelled first."""
        return invoke("jobs.close", {"job_id": job_id, "cancel_token": cancel_token}, request_id)

    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stdio MCP adapter for an already open Prep GUI")
    parser.add_argument("--connection", required=True, help="Private connection file created by the live GUI owner")
    args = parser.parse_args(argv)
    create_server(args.connection).run(transport="stdio")


if __name__ == "__main__":
    main()
