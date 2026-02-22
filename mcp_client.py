import json
import uuid
import requests

MCP_URL = "http://localhost:4444/mcp/fd477fc295cf488da8c16219e2af894b"

def mcp_call(method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params or {}
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    response = requests.post(
        MCP_URL,
        data=json.dumps(payload),
        headers=headers
    )

    print("\n--- Response for", method, "---")
    print("Status:", response.status_code)
    print("Body:", response.text)
    print("--- End ---\n")




# 2. Call your tool
mcp_call("tools/call", {
    "name": "employerassestfastapi-local",
    "arguments": {}
})