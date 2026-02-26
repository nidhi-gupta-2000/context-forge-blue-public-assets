import json
import sys
import uuid
import requests
from typing import Any
from pydantic import RootModel
import anthropic

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()  # ← must be before anthropic.Anthropic()

MCP_URL = "http://localhost:4444/mcp/fd477fc295cf488da8c16219e2af894b"
claude = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


# ---------------------------------------------------------
#  Pydantic passthrough model
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
    try:
        return MCPResponse.model_validate(response.json())
    except Exception as e:
        return response.json()


# ---------------------------------------------------------
#  LLM Step 1: Detect context from member query
# ---------------------------------------------------------
def detect_context_llm(member_query: str) -> str:
    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        system="""You are a behavioral health context classifier.
Given a member query, return ONLY one of these exact values:
- anxiety
- depression  
- sud
- youth-bh
- general

Return just the single word/phrase, nothing else.""",
        messages=[
            {"role": "user", "content": member_query}
        ]
    )
    context = response.content[0].text.strip().lower()
    # Validate it's one of the allowed values
    allowed = ["anxiety", "depression", "sud", "youth-bh", "general"]
    return context if context in allowed else "general"


# ---------------------------------------------------------
#  LLM Step 2: Summarize docs into member-friendly response
# ---------------------------------------------------------
def summarize_docs_llm(member_query: str, context: str, docs: list, prompt_text: str = "") -> str:
    docs_text = json.dumps(docs, indent=2)
    if prompt_text:
        # Use the MCP prompt as the user message, append docs to it
        user_content = f"{prompt_text}\n\nAvailable resources:\n{docs_text}"
    else:
        user_content = f"""Member query: {member_query}
Context: {context}
Available resources: {docs_text}

Please provide a helpful response for this member."""
    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system="""You are a compassionate BCBSNC benefits advisor helping members
find behavioral health resources. Given the member's concern and a list of
available resources, provide a warm, helpful response that:
1. Acknowledges their concern briefly
2. Lists the most relevant 2-3 resources with their links
3. Encourages them to reach out for help""",
        messages=[{"role": "user", "content": user_content}]
    )
    return response.content[0].text


# ---------------------------------------------------------
#  Change this to test different member queries
# ---------------------------------------------------------
MEMBER_QUERY = "I've been feeling really down lately and can't find motivation"


# ==========================================================
#  STEP 1: LLM detects context (replaces keyword matching)
# ==========================================================
print("=" * 60)
print("STEP 1: LLM detecting context from member query")
print("=" * 60)
print(f"Member query: {MEMBER_QUERY}")

context = detect_context_llm(MEMBER_QUERY)
print(f"✅ LLM detected context: '{context}'")


# ==========================================================
#  STEP 2: Get prompt from MCP
# ==========================================================
print("=" * 60)
print("STEP 2: Getting prompt from MCP")
print("=" * 60)

prompt_result = mcp_call("prompts/get", {
    "name": "behavioral-health-context-router",
    "arguments": {
        "member_query": MEMBER_QUERY,
        "context": context
    }
})
messages = []
prompt_text = ""
try:
    raw = prompt_result.root
    # Check for MCP-level error first
    if raw.get("error"):
        print(f"❌ MCP error: {raw['error']}")
    else:
        result = raw.get("result", {})
        messages = result.get("messages", [])

        if not messages:
            print(f"⚠️  0 messages returned. Raw result: {json.dumps(result, indent=2)[:500]}")
        else:
            prompt_text = messages[0]["content"]["text"]
            print(f"✅ Prompt returned {len(messages)} message(s)")
            print(f"   Prompt text: {prompt_text[:200]}...")
except Exception as e:
    print(f"❌ Prompt extraction failed: {e}")
    print(f"   Raw response: {json.dumps(prompt_result.root, indent=2)[:500]}")
    messages = []


# ==========================================================
#  STEP 3: Read matching resource
# ==========================================================
print("=" * 60)
print(f"STEP 3: Reading resource for context: {context}")
print("=" * 60)

resource_result = mcp_call("resources/read", {
    "uri": f"resource://bcbsnc/{context}"
})

resource_docs = []
try:
    contents = resource_result.root.get("result", {}).get("contents", [])
    for content in contents:
        data = json.loads(content.get("text", "{}"))
        resource_docs = data.get("docs", [])
    print(f"✅ Resource returned {len(resource_docs)} curated docs")
except Exception as e:
    print(f"❌ Resource failed: {e}")


# ==========================================================
#  STEP 4: Call tool for dynamic docs
# ==========================================================
print("=" * 60)
print("STEP 4: Calling tool for dynamic docs")
print("=" * 60)

tool_result = mcp_call("tools/call", {
    "name": "employerassestfastapi-local",
    "arguments": {}
})

tool_docs = []
try:
    content_text = tool_result.root["result"]["content"][0]["text"]
    all_data = json.loads(content_text)
    all_docs = all_data[0].get("Docs", [])

    # Filter by context keywords as backup
    CONTEXT_KEYWORDS = {
        "sud":        ["substance", "sud", "drug", "alcohol"],
        "anxiety":    ["anxiety", "stress", "mental health"],
        "depression": ["depression", "mood", "mental health"],
        "youth-bh":   ["youth", "ybh", "young", "adolescent"],
        "general":    []
    }
    keywords = CONTEXT_KEYWORDS.get(context, [])
    tool_docs = [
        doc for doc in all_docs
        if not keywords or any(
            kw in doc.get("name", "").lower() or
            kw in doc.get("description", "").lower()
            for kw in keywords
        )
    ] or all_docs
    print(f"✅ Tool returned {len(tool_docs)} filtered docs")
except Exception as e:
    print(f"❌ Tool failed: {e}")


# ==========================================================
#  STEP 5: Merge resource + tool docs (deduplicate)
# ==========================================================
print("=" * 60)
print("STEP 5: Merging resource and tool docs")
print("=" * 60)

existing_names = {doc["name"] for doc in resource_docs}
additional_docs = [doc for doc in tool_docs if doc["name"] not in existing_names]
final_docs = resource_docs + additional_docs
print(f"✅ Final merged docs: {len(final_docs)} ({len(resource_docs)} curated + {len(additional_docs)} additional)")


# ==========================================================
#  STEP 6: LLM summarizes into member-friendly response
# ==========================================================
print("=" * 60)
print("STEP 6: LLM generating member response")
print("=" * 60)

final_response = summarize_docs_llm(MEMBER_QUERY, context, final_docs, prompt_text)
print(f"\n{'=' * 60}")
print("FINAL RESPONSE TO MEMBER:")
print('=' * 60)
print(final_response)


# ==========================================================
#  SUMMARY
# ==========================================================
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  Member Query    : {MEMBER_QUERY}")
print(f"  LLM Context     : {context}")
print(f"  Resource docs   : {len(resource_docs)}")
print(f"  Tool docs       : {len(tool_docs)}")
print(f"  Final merged    : {len(final_docs)}")
print("=" * 60)