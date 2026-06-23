from __future__ import annotations

import asyncio
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent, CallToolResult

from gke_scout.guardrail.audit import AuditLog
from gke_scout.guardrail.policy import evaluate
from gke_scout.guardrail.redact import redact
from gke_scout.models import ToolCall

UPSTREAM_CONNECT_TIMEOUT = 30   # seconds to establish upstream MCP session
UPSTREAM_CALL_TIMEOUT = 60      # seconds per tool call to upstream

GKE_MCP_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


def _get_auth_headers() -> dict[str, str]:
    """Obtain a fresh OAuth2 access token via Application Default Credentials."""
    import google.auth
    import google.auth.transport.requests as g_requests
    credentials, _ = google.auth.default(scopes=GKE_MCP_SCOPES)
    credentials.refresh(g_requests.Request())
    return {"Authorization": f"Bearer {credentials.token}"}


async def handle_call_tool(
    name: str, arguments: dict, *, session, audit: AuditLog,
    call_timeout: int = UPSTREAM_CALL_TIMEOUT,
) -> CallToolResult:
    """Policy-guarded, timeout-wrapped tool call handler (extracted for testability)."""
    call = ToolCall(name=name, args=arguments or {})
    decision = evaluate(call)
    audit.record(call, decision)
    if not decision.allowed:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Refused: {decision.reason}")],
            isError=True,
        )
    try:
        raw = await asyncio.wait_for(
            session.call_tool(call.name, call.args),
            timeout=call_timeout)
        
        payload = raw.model_dump() if hasattr(raw, "model_dump") else raw
        
        is_error = False
        if hasattr(payload, "isError"):
            is_error = payload.isError
        elif isinstance(payload, dict):
            is_error = payload.get("isError", False)

        raw_content = []
        if hasattr(payload, "content") and payload.content is not None:
            raw_content = payload.content
        elif isinstance(payload, dict):
            raw_content = payload.get("content", [])

        redacted_content = []
        for c in raw_content:
            if hasattr(c, "type") and c.type == "text" and hasattr(c, "text"):
                redacted_content.append(TextContent(type="text", text=redact(c.text)))
            elif isinstance(c, dict) and c.get("type") == "text":
                redacted_content.append(TextContent(type="text", text=redact(c.get("text", ""))))
            else:
                redacted_content.append(c)

        raw_structured = None
        if hasattr(payload, "structuredContent") and payload.structuredContent is not None:
            raw_structured = payload.structuredContent
        elif isinstance(payload, dict):
            raw_structured = payload.get("structuredContent")

        redacted_structured = redact(raw_structured) if raw_structured is not None else None

        return CallToolResult(
            content=redacted_content,
            structuredContent=redacted_structured,
            isError=is_error,
        )
    except asyncio.TimeoutError:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: upstream tool '{call.name}' timed out after {call_timeout}s")],
            isError=True,
        )
    except BaseException as exc:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: tool call failed safely")],
            isError=True,
        )


async def serve(endpoint: str, audit_path: str) -> None:
    server = Server("gke-scout-guardrail")
    audit = AuditLog(audit_path)

    try:
        auth_headers = _get_auth_headers()
    except Exception as exc:
        sys.stderr.write(f"guardrail: ADC auth failed: {exc}\n")
        raise SystemExit(1) from exc

    try:
        ctx = streamablehttp_client(endpoint, headers=auth_headers)
        read, write, _ = await asyncio.wait_for(
            ctx.__aenter__(), timeout=UPSTREAM_CONNECT_TIMEOUT)
    except (asyncio.TimeoutError, Exception) as exc:
        sys.stderr.write(
            f"guardrail: failed to connect to upstream {endpoint}: {exc}\n")
        raise SystemExit(1) from exc

    try:
        session = ClientSession(read, write)
        await asyncio.wait_for(
            session.__aenter__(), timeout=UPSTREAM_CONNECT_TIMEOUT)
        await asyncio.wait_for(
            session.initialize(), timeout=UPSTREAM_CONNECT_TIMEOUT)
    except (asyncio.TimeoutError, Exception) as exc:
        sys.stderr.write(
            f"guardrail: upstream MCP handshake failed: {exc}\n")
        await ctx.__aexit__(None, None, None)
        raise SystemExit(1) from exc

    @server.list_tools()
    async def list_tools():
        return (await session.list_tools()).tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        return await handle_call_tool(name, arguments, session=session,
                                      audit=audit)

    try:
        async with stdio_server() as (r, w):
            await server.run(r, w, server.create_initialization_options())
    finally:
        try:
            await session.__aexit__(None, None, None)
        except BaseException:
            pass
        try:
            await ctx.__aexit__(None, None, None)
        except BaseException:
            pass


def main() -> None:
    endpoint = os.environ.get("GKE_SCOUT_UPSTREAM", "https://container.googleapis.com/mcp")
    audit_path = os.environ.get("GKE_SCOUT_AUDIT", os.path.expanduser("~/.gke-scout/audit.jsonl"))
    asyncio.run(serve(endpoint, audit_path))
