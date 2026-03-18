# Task 3: The System Agent

## Overview

Extend the agent from Task 2 to add a `query_api` tool that can query the deployed backend. This enables the agent to answer:
1. **Static system facts** - framework, ports, status codes (from wiki or source code)
2. **Data-dependent queries** - item count, scores, analytics (from live API)

## LLM Provider

- **Provider**: OpenRouter (same as Task 1-2)
- **Model**: `arcee-ai/trinity-mini:free` or faster model for iteration

## New Tool: `query_api`

Call the deployed backend API with authentication.

### Parameters

- `method` (string, required) - HTTP method: GET, POST, PUT, DELETE, etc.
- `path` (string, required) - API path, e.g., `/items/`, `/analytics/completion-rate`
- `body` (string, optional) - JSON request body for POST/PUT requests

### Returns

JSON string with:
- `status_code` - HTTP status code
- `body` - Response body as string (JSON or text)

### Authentication

- Use `LMS_API_KEY` from `.env.docker.secret`
- Add header: `X-API-Key: {LMS_API_KEY}`

### Implementation

```python
def query_api(method: str, path: str, body: str = None) -> str:
    """Call the backend API with authentication."""
    import os
    api_key = os.environ.get("LMS_API_KEY")
    base_url = os.environ.get("AGENT_API_BASE_URL", "http://localhost:42002")
    
    url = f"{base_url}{path}"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }
    
    # Make request with httpx
    # Return JSON string with status_code and body
```

## Environment Variables

The agent must read ALL configuration from environment variables (not hardcoded):

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for query_api auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for query_api (default: http://localhost:42002) | Optional, env or default |

**Important**: The autochecker injects its own values. Never hardcode these.

## System Prompt Update

Update the system prompt to guide tool selection:

1. **Wiki questions** ("According to the wiki...", "What files...") → use `list_files`, `read_file`
2. **System facts** ("What framework...", "What port...") → use `read_file` on source code (pyproject.toml, backend/main.py)
3. **Data queries** ("How many items...", "What is the score...") → use `query_api`
4. **Bug diagnosis** → use `query_api` to reproduce, then `read_file` to find the bug

## Output Format Update

The `source` field is now **optional** (string or missing):

```json
{
  "answer": "There are 120 items in the database.",
  "source": "wiki/items.md",  // optional - may not exist for API queries
  "tool_calls": [
    {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}, "result": "..."}
  ]
}
```

For system facts and data queries, there may not be a wiki source.

## Tool Schema

```python
{
    "type": "function",
    "function": {
        "name": "query_api",
        "description": "Call the backend API to query data or check system status. Use for questions about item counts, scores, analytics, or to test endpoints.",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, PUT, DELETE)"
                },
                "path": {
                    "type": "string",
                    "description": "API path (e.g., '/items/', '/analytics/completion-rate')"
                },
                "body": {
                    "type": "string",
                    "description": "JSON request body for POST/PUT (optional)"
                }
            },
            "required": ["method", "path"]
        }
    }
}
```

## Implementation Steps

1. Add `query_api` tool function with authentication
2. Add `query_api` to tool schemas
3. Update `load_env()` to also load `.env.docker.secret` for `LMS_API_KEY`
4. Update system prompt with tool selection guidance
5. Make `source` field optional in output
6. Test with `run_eval.py` and iterate

## Testing Strategy

Run the benchmark:

```bash
uv run run_eval.py
```

Expected question types:
1. Wiki lookup (e.g., "According to the wiki, what steps...")
2. System facts (e.g., "What Python web framework...")
3. Data queries (e.g., "How many items are in the database?")
4. Bug diagnosis
5. Reasoning

Add 2 regression tests:
1. `"What framework does the backend use?"` → expects `read_file` in tool_calls
2. `"How many items are in the database?"` → expects `query_api` in tool_calls

## Benchmark Iteration Workflow

When a question fails:
1. Read the feedback hint
2. Run with `--index N` to debug that specific question
3. Check if the right tool was called
4. Check if arguments were correct
5. Adjust tool descriptions or system prompt
6. Re-run

Common issues:
- Wrong tool chosen → improve system prompt
- Wrong arguments → clarify tool schema
- API authentication failed → check LMS_API_KEY loading
- Answer phrasing doesn't match → adjust prompt for precision

## Files to Update

- `agent.py` - Add query_api tool, update env loading, update system prompt
- `AGENT.md` - Document query_api, authentication, lessons learned (200+ words)
- `tests/test_agent.py` - Add 2 regression tests
- `plans/task-3.md` - Add benchmark score and iteration notes after first run

## Benchmark Status

**Initial Score**: Pending (OpenRouter rate limited)

**Known Issues to Fix**:
1. LLM calling query_api with empty arguments - need to improve tool schema descriptions
2. Default AGENT_API_BASE_URL should be http://localhost:42001 (backend port), not 42002 (Caddy)
3. Backend uses Bearer token auth, not X-API-Key header

**Iteration Plan**:
1. Fix query_api authentication (Bearer token)
2. Improve tool descriptions to ensure LLM passes correct arguments
3. Once rate limit resets, run full eval and iterate
