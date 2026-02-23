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
    response = requests.post(
        MCP_URL,
        data=json.dumps(payload),
        headers={"Accept": "application/json", "Content-Type": "application/json"}
    )
    print(f"\n--- Raw Response for {method} ---")
    print("Status:", response.status_code)
    print("Body:", response.text[:300], "..." if len(response.text) > 300 else "")
    print("--- End Raw ---\n")

    try:
        return MCPResponse.model_validate(response.json())
    except Exception as e:
        print("Pydantic failed, returning raw JSON")
        print("Error:", e)
        return response.json()


# ---------------------------------------------------------
#  Context detection from member query
# ---------------------------------------------------------
def detect_context(query: str) -> str:
    query = query.lower()
    if any(k in query for k in ["drug", "alcohol", "substance", "overuse", "sud"]):
        return "sud"
    elif any(k in query for k in ["anxiety", "stress", "worry", "panic"]):
        return "anxiety"
    elif any(k in query for k in ["depression", "sad", "mood", "hopeless"]):
        return "depression"
    elif any(k in query for k in ["youth", "child", "teen", "adolescent"]):
        return "youth-bh"
    else:
        return "general"  # default fallback


# ---------------------------------------------------------
#  Change this to test different member queries
# ---------------------------------------------------------
MEMBER_QUERY = "I am struggling with drug and alcohol overuse"


# ==========================================================
#  STEP 1: Call the Tool (existing behavior)
# ==========================================================
print("=" * 60)
print("STEP 1: Calling tool - employerassestfastapi-local")
print("=" * 60)

tool_result = mcp_call("tools/call", {
    "name": "employerassestfastapi-local",
    "arguments": {}
})

all_docs = []
try:
    content_text = tool_result.root["result"]["content"][0]["text"]
    all_data = json.loads(content_text)
    all_docs = all_data[0].get("Docs", [])
    print(f"✅ Tool returned {len(all_docs)} total documents")
except Exception as e:
    print(f"❌ Tool call failed: {e}")


# ==========================================================
#  STEP 2: Get Prompt with member query + detected context
# ==========================================================
print("=" * 60)
print("STEP 2: Getting prompt - behavioral-health-context-router")
print("=" * 60)

context = detect_context(MEMBER_QUERY)
print(f"Detected context from query: '{context}'")

prompt_result = mcp_call("prompts/get", {
    "name": "behavioral-health-context-router",
    "arguments": {
        "member_query": MEMBER_QUERY,
        "context": context
    }
})

messages = []
try:
    messages = prompt_result.root.get("result", {}).get("messages", [])
    print(f"✅ Prompt returned {len(messages)} message(s)")
    for msg in messages:
        role = msg.get("role")
        text = msg.get("content", {}).get("text", "")
        print(f"  Role    : {role}")
        print(f"  Content : {text[:200]}...")
except Exception as e:
    print(f"❌ Prompt call failed: {e}")
    print(json.dumps(prompt_result.root, indent=2))


# ==========================================================
#  STEP 3: Read Resource matching the detected context
# ==========================================================
print("=" * 60)
print(f"STEP 3: Reading resource - resource://bcbsnc/{context}")
print("=" * 60)

resource_result = mcp_call("resources/read", {
    "uri": f"resource://bcbsnc/{context}"
})

resource_docs = []
try:
    contents = resource_result.root.get("result", {}).get("contents", [])
    print(f"✅ Resource returned {len(contents)} content block(s)")
    for content in contents:
        data = json.loads(content.get("text", "{}"))
        resource_docs = data.get("docs", [])
        print(f"\n  Context : {data.get('context')}")
        print(f"  Docs    : {len(resource_docs)} relevant documents")
        for doc in resource_docs:
            link = (
                doc.get("onEnglishAction") or
                doc.get("onEnglishEmailSave") or
                doc.get("onEnglishVideoAction") or
                "N/A"
            )
            print(f"    - {doc.get('name')}")
            print(f"      {link}")
except Exception as e:
    print(f"❌ Resource read failed: {e}")
    print(json.dumps(resource_result.root, indent=2))


# ==========================================================
#  STEP 4: Cross-check — filter tool docs by context
# ==========================================================
print("=" * 60)
print(f"STEP 4: Filtering tool docs by context '{context}'")
print("=" * 60)

CONTEXT_KEYWORDS = {
    "sud":        ["substance", "sud", "drug", "alcohol"],
    "anxiety":    ["anxiety", "stress", "mental health"],
    "depression": ["depression", "mood", "mental health"],
    "youth-bh":   ["youth", "ybh", "young", "adolescent"],
    "general":    []
}

keywords = CONTEXT_KEYWORDS.get(context, [])
filtered_docs = [
    doc for doc in all_docs
    if not keywords or any(
        kw in doc.get("name", "").lower() or
        kw in doc.get("description", "").lower()
        for kw in keywords
    )
] or all_docs  # fallback to all if nothing matched

print(f"✅ Filtered {len(filtered_docs)} docs from tool response:")
for doc in filtered_docs:
    link = (
        doc.get("onEnglishAction") or
        doc.get("onEnglishEmailSave") or
        doc.get("onEnglishVideoAction") or
        "N/A"
    )
    print(f"  - {doc.get('name')}")
    print(f"    {link}")


# ==========================================================
#  SUMMARY
# ==========================================================
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  Member Query    : {MEMBER_QUERY}")
print(f"  Detected Context: {context}")
print(f"  Tool docs total : {len(all_docs)}")
print(f"  Filtered docs   : {len(filtered_docs)}")
print(f"  Resource docs   : {len(resource_docs)}")
print(f"  Prompt messages : {len(messages)}")
print("=" * 60)
