import os
import sys
from pathlib import Path
import uvicorn

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR))

# Configure strict real production runtime environment
os.environ["REFRAME_RUNTIME_MODE"] = "real"
os.environ["REAL_INTEGRATION_VALIDATION"] = "true"
os.environ["USE_REAL_MCP"] = "true"
os.environ["MCP_ENDPOINT_URL"] = "http://127.0.0.1:8001/mcp"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "")
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GEMINI_MODEL"] = "gemini-3.6-flash"

if __name__ == "__main__":
    uvicorn.run("apps.api.main:app", host="127.0.0.1", port=8000, log_level="info")
