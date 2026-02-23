import json
import uuid
import requests
from typing import Any
from pydantic import RootModel

MCP_URL = "http://localhost:4444/mcp/fd477fc295cf488da8c16219e2af894b"


# ---------------------------------------------------------
#  Pydantic passthrough model (accepts ANY JSON)
# ---------------------------------------------------------
class MCPResponse(RootModel[Any]):
    pass


# ---------------------------------------------------------
#  MCP call wrapper
# ---------------------------------------------------------
def mcp_call(method: str, params: dict | None = None):
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

    print("\n--- Raw Response for", method, "---")
    print("Status:", response.status_code)
    print("Body:", response.text)
    print("--- End Raw ---\n")

    # Parse with permissive RootModel
    try:
        parsed = MCPResponse.model_validate(response.json())
    except Exception as e:
        print("Pydantic failed, returning raw JSON instead")
        print("Error:", e)
        return response.json()

    return parsed


# ---------------------------------------------------------
#  Step 1: List all tools and inspect stored schema
# ---------------------------------------------------------
print("=" * 60)
print("STEP 1: Checking tools/list to inspect stored outputSchema")
print("=" * 60)

tools_result = mcp_call("tools/list", {})
print("\n--- Tools List (Full) ---")
print(json.dumps(tools_result.root, indent=2))
print("--- End Tools List ---\n")

# Extract and print just the relevant tool's schema
try:
    tools = tools_result.root.get("result", {}).get("tools", [])
    print(f"Total tools found: {len(tools)}\n")
    for tool in tools:
        print(f"Tool: {tool.get('name')}")
        print(f"  Description: {tool.get('description', 'N/A')}")
        print(f"  Input Schema:  {json.dumps(tool.get('inputSchema', {}), indent=4)}")
        print(f"  Output Schema: {json.dumps(tool.get('outputSchema', 'NOT DEFINED'), indent=4)}")
        print()
except Exception as e:
    print(f"Could not parse tools list: {e}")


# ---------------------------------------------------------
#  Step 2: Call the behavior health tool
# ---------------------------------------------------------
print("=" * 60)
print("STEP 2: Calling employerassestfastapi-local tool")
print("=" * 60)

result = mcp_call("tools/call", {
    "name": "employerassestfastapi-local",
    "arguments": {}
})

raw = result.root
tool_result = raw.get("result", {})

print("\n--- Structured Content ---")
print(tool_result)
print("--- End Structured Content ---\n")

# ---------------------------------------------------------
#  Step 3: Try to parse content if successful
# ---------------------------------------------------------
print("=" * 60)
print("STEP 3: Parsing response content")
print("=" * 60)

is_error = tool_result.get("isError", True)
content = tool_result.get("content", [])

if is_error:
    print("❌ Tool call failed!")
    for item in content:
        print(f"   Error: {item.get('text', 'Unknown error')}")
else:
    print("✅ Tool call succeeded!")
    for item in content:
        text = item.get("text", "")
        # Try to parse as JSON if it looks like JSON
        try:
            data = json.loads(text)
            print(f"\nParsed {len(data)} category/categories:\n")
            for category in data:
                print(f"  Title:   {category.get('title')}")
                print(f"  Summary: {category.get('summary', '')[:80]}...")
                docs = category.get("Docs", [])
                print(f"  Docs:    {len(docs)} documents")
                for doc in docs:
                    print(f"    - {doc.get('name')}")
                print()
        except json.JSONDecodeError:
            print("Response is plain text (not JSON):")
            print(text)
            