"""
Reframe MCP Service delegating to official ClickHouse/mcp-clickhouse server distribution.
"""
from typing import Dict, Any, Optional, List
import os
import json
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import structlog
import mcp_clickhouse

logger = structlog.get_logger(__name__)

app = FastAPI(title="ClickHouse MCP Protocol Server (delegating to official mcp-clickhouse)")

# Configure official mcp-clickhouse environment variables
os.environ.setdefault("CLICKHOUSE_HOST", "localhost")
os.environ.setdefault("CLICKHOUSE_PORT", "8123")
os.environ.setdefault("CLICKHOUSE_USER", "reframe_runtime")
os.environ.setdefault("CLICKHOUSE_PASSWORD", "")
os.environ.setdefault("CLICKHOUSE_DATABASE", "reframe")
os.environ.setdefault("CLICKHOUSE_SECURE", "false")


def execute_via_official_mcp(query: str) -> List[Dict[str, Any]]:
    """Executes query using official ClickHouse/mcp-clickhouse run_query tool."""
    raw_res = mcp_clickhouse.run_query(query)
    try:
        parsed = json.loads(raw_res)
        if isinstance(parsed, dict) and "columns" in parsed and "rows" in parsed:
            cols = parsed["columns"]
            return [dict(zip(cols, row)) for row in parsed["rows"]]
        if isinstance(parsed, list):
            return parsed
        return [{"raw": raw_res}]
    except Exception:
        return [{"raw": raw_res}]


@app.post("/mcp")
async def mcp_jsonrpc_endpoint(req: Request):
    """
    Standard MCP JSON-RPC 2.0 protocol endpoint handling `tools/call` for `run_query`
    using official ClickHouse/mcp-clickhouse execution engine.
    """
    body = await req.json()
    req_id = body.get("id", "1")
    method = body.get("method", "")
    params = body.get("params", {})

    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "run_query",
                        "description": "Official ClickHouse MCP tool for executing queries against ClickHouse",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                            },
                            "required": ["query"],
                        },
                    }
                ]
            }
        })

    if method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})
        if tool_name == "run_query":
            query = args.get("query", "")
            try:
                rows = execute_via_official_mcp(query)
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({"data": rows}),
                            }
                        ]
                    }
                })
            except Exception as e:
                logger.error("official_mcp_tool_execution_failed", error=str(e))
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32603,
                        "message": str(e),
                    }
                }, status_code=500)

    return JSONResponse({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": -32601,
            "message": f"Method '{method}' not found",
        }
    }, status_code=404)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")
