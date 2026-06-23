from __future__ import annotations

import asyncio
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from gke_triage.guardrail.audit import AuditLog
from gke_triage.guardrail.policy import evaluate
from gke_triage.guardrail.redact import redact
from gke_triage.models import ToolCall


async def serve(endpoint: str, audit_path: str) -> None:
    server = Server("gke-triage-guardrail")
    audit = AuditLog(audit_path)

    async with streamablehttp_client(endpoint) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            @server.list_tools()
            async def list_tools():
                return (await session.list_tools()).tools

            @server.call_tool()
            async def call_tool(name: str, arguments: dict):
                call = ToolCall(name=name, args=arguments or {})
                decision = evaluate(call)
                audit.record(call, decision)
                if not decision.allowed:
                    return [{"type": "text", "text": f"Refused: {decision.reason}"}]
                raw = await session.call_tool(call.name, call.args)
                payload = raw.model_dump() if hasattr(raw, "model_dump") else raw
                return [{"type": "text", "text": str(redact(payload))}]

            async with stdio_server() as (r, w):
                await server.run(r, w, server.create_initialization_options())


def main() -> None:
    endpoint = os.environ.get("GKE_TRIAGE_UPSTREAM", "https://container.googleapis.com/mcp")
    audit_path = os.environ.get("GKE_TRIAGE_AUDIT", os.path.expanduser("~/.gke-triage/audit.jsonl"))
    asyncio.run(serve(endpoint, audit_path))
