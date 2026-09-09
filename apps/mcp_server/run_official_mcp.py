"""
Official ClickHouse MCP Server Runner.
Launches the official ClickHouse/mcp-clickhouse server distribution (v0.4.1+).
"""
import os
import sys
from mcp_clickhouse.main import main

if __name__ == "__main__":
    # Ensure standard ClickHouse connection environment defaults
    os.environ.setdefault("CLICKHOUSE_HOST", "localhost")
    os.environ.setdefault("CLICKHOUSE_PORT", "8123")
    os.environ.setdefault("CLICKHOUSE_USER", "reframe_runtime")
    os.environ.setdefault("CLICKHOUSE_PASSWORD", "")
    os.environ.setdefault("CLICKHOUSE_DATABASE", "reframe")
    os.environ.setdefault("CLICKHOUSE_SECURE", "false")
    os.environ.setdefault("CLICKHOUSE_ALLOW_WRITE_ACCESS", "true")
    
    print("Starting Official ClickHouse MCP Server (ClickHouse/mcp-clickhouse)...")
    main()
