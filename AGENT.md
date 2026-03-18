# Agent Architecture

## Overview

`agent.py` is a CLI tool that connects to an LLM via the OpenAI-compatible chat completions API. It implements an **agentic loop** with tool calling capabilities, allowing the LLM to interact with the local file system through `read_file` and `list_files` tools, and query the deployed backend API through `query_api`. This enables the agent to answer questions based on actual project documentation, source code, and live system data.

## LLM Provider

- **Provider**: OpenRouter (openrouter.ai)
- **Model**: `arcee-ai/trinity-mini:free` (free tier with tool calling support)
- **API Endpoint**: `https://openrouter.ai/api/v1/chat/completions`

> **Note**: Free models on OpenRouter can be temporarily rate-limited. If you encounter 429 errors, try switching to a different free model in `.env.agent.secret`.

## Configuration

The agent reads configuration from multiple environment files:

### `.env.agent.secret` (LLM configuration)
```bash
LLM_API_KEY=sk-or-...           # Your OpenRouter API key
LLM_API_BASE=https://openrouter.ai/api/v1
LLM_MODEL=arcee-ai/trinity-mini:free
```

### `.env.docker.secret` (Backend API authentication)
```bash
LMS_API_KEY=my-secret-api-key   # Backend API key for query_api auth
```

### Environment variables (optional overrides)
```bash
AGENT_API_BASE_URL=http://localhost:42001  # Backend API base URL (default)
```

> **Important**: The autochecker injects its own values for all these variables. Never hardcode credentials or URLs.

## Usage

```bash
uv run agent.py "Your question here"
```

### Example

```bash
$ uv run agent.py "How many items are in the database?"
Using model: arcee-ai/trinity-mini:free

[Loop iteration 1]
Calling LLM API...
Tool call: query_api with args {'method': 'GET', 'path': '/items/'}
  Executing query_api(GET /items/)

[Loop iteration 2]
Calling LLM API...
LLM provided final answer (no tool calls)

Completed in 3.42s
{"answer": "There are 42 items in the database.", "source": "", "tool_calls": [...]}
```

## Output Format

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "The LLM's response text",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",  // optional
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, \"body\": \"[...]\"}"
    }
  ]
}
```

- `answer` (string, required): The LLM's answer to the question
- `source` (string, optional): The wiki file path with optional section anchor. Empty for API queries or general knowledge questions.
- `tool_calls` (array, required): All tool calls made during the agentic loop. Each entry has:
  - `tool`: Tool name (`read_file`, `list_files`, or `query_api`)
  - `args`: Arguments passed to the tool
  - `result`: The tool's return value

All debug and error messages go to **stderr**, only valid JSON goes to **stdout**.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Command Line   │ ──► │   agent.py   │ ──► │  LLM API        │
│  (question)     │     │  (CLI tool)  │     │  (OpenRouter)   │
└─────────────────┘     └──────────────┘     └─────────────────┘
                              │  ▲
                              │  │
                              ▼  │
                       ┌──────────────┐
                       │  Tools       │
                       │  - read_file │
                       │  - list_files│
                       │  - query_api │
                       └──────────────┘
                              │
                              ▼
                       ┌──────────────┐
                       │  JSON Output │
                       │  (stdout)    │
                       └──────────────┘
```

### Agentic Loop

The agent implements the following loop:

1. **Send**: User question + tool definitions + system prompt to LLM
2. **Receive**: LLM response
   - If `tool_calls` present → execute each tool, append results as `tool` role messages, go to step 1
   - If no tool calls → final answer, output JSON and exit
3. **Limit**: Maximum 10 tool calls per question

```
Question ──▶ LLM ──▶ tool calls? ──yes──▶ execute tools ──▶ back to LLM
                         │
                         no
                         │
                         ▼
                    JSON output
```

### Components

1. **`load_env()`**: Loads environment variables from `.env.agent.secret` and `.env.docker.secret`
2. **`get_llm_config()`**: Extracts and validates LLM configuration
3. **`is_safe_path()`**: Validates paths to prevent directory traversal attacks
4. **`read_file(path)`**: Reads file contents with security checks
5. **`list_files(path)`**: Lists directory contents with security checks
6. **`query_api(method, path, body)`**: Calls the backend API with Bearer token authentication
7. **`get_tool_schemas()`**: Returns OpenAI-compatible tool schemas
8. **`execute_tool(name, args)`**: Executes a tool by name with given arguments
9. **`call_llm(messages, tools)`**: Makes HTTP POST request to the LLM API with tool support
10. **`extract_source_from_messages()`**: Extracts source reference from conversation
11. **`main()`**: Entry point - implements the agentic loop

## Tool Definitions

### `read_file`

Reads the contents of a file in the project repository.

- **Parameters**: `path` (string) — relative path from project root
- **Returns**: File contents as string, or error message if file doesn't exist
- **Security**: Rejects paths with `../` traversal or absolute paths
- **Use cases**: Wiki documentation, source code (pyproject.toml, backend/*.py)

### `list_files`

Lists files and directories at a given path.

- **Parameters**: `path` (string) — relative directory path from project root
- **Returns**: Newline-separated listing of entries, or error message
- **Security**: Rejects paths with `../` traversal or paths outside project directory
- **Use cases**: Discovering wiki files, exploring project structure

### `query_api`

Calls the deployed backend API with authentication.

- **Parameters**: 
  - `method` (string) — HTTP method (GET, POST, PUT, DELETE)
  - `path` (string) — API path (e.g., `/items/`, `/analytics/completion-rate`)
  - `body` (string, optional) — JSON request body for POST/PUT
- **Returns**: JSON string with `status_code` and `body`
- **Authentication**: Bearer token via `Authorization: Bearer {LMS_API_KEY}`
- **Use cases**: Data-dependent queries (item counts, scores, analytics), testing endpoints

## System Prompt

The system prompt instructs the LLM to select tools based on question type:

1. **Wiki/documentation questions** → use `list_files` and `read_file` on wiki/ directory
2. **System facts** → use `read_file` on source code (pyproject.toml, backend/main.py)
3. **Data-dependent questions** → use `query_api` to fetch live data
4. **Bug diagnosis** → use `query_api` to reproduce, then `read_file` to find the bug
5. **General knowledge** → answer directly without tools

## Tool Selection Strategy

The agent's tool selection is guided by the system prompt and tool descriptions:

| Question Type | Example | Expected Tools |
|--------------|---------|----------------|
| Wiki lookup | "According to the wiki..." | `list_files`, `read_file` |
| System fact | "What framework..." | `read_file` (pyproject.toml) |
| Data query | "How many items..." | `query_api` |
| Bug diagnosis | "Why does /api return 500?" | `query_api`, then `read_file` |

## Path Security

Both file tools validate paths to prevent directory traversal attacks:

```python
def is_safe_path(path: str) -> bool:
    """Check if path is safe (no traversal outside project)."""
    if path.startswith('/'):
        return False
    if '..' in path:
        return False
    resolved = (PROJECT_ROOT / path).resolve()
    return str(resolved).startswith(str(PROJECT_ROOT))
```

## Error Handling

- **Missing API key**: Exits with error to stderr
- **Rate limit (429)**: Exits with helpful message suggesting retry or model switch
- **HTTP errors**: Returns status code and error in tool result
- **Timeout**: 60-second timeout on API calls, 30-second timeout on backend API
- **Invalid response**: Exits with parse error
- **Unsafe path**: Returns error message in tool result (doesn't crash)
- **File not found**: Returns error message in tool result
- **Backend unavailable**: Returns connection error in tool result

## Lessons Learned

### Benchmark Iteration

During development, several issues were discovered and fixed:

1. **Empty tool arguments**: The LLM initially called `query_api` with empty `method` and `path` arguments. This was fixed by improving the tool schema descriptions to be more explicit about required parameters and providing clear examples.

2. **Authentication mismatch**: The backend uses Bearer token authentication (`Authorization: Bearer <key>`), not the `X-API-Key` header. This was discovered by testing the API directly with curl.

3. **Wrong default port**: The default `AGENT_API_BASE_URL` was initially set to port 42002 (Caddy), but the backend runs on port 42001. Updated to use the correct port.

4. **Rate limiting**: OpenRouter's free tier has a 50 requests/day limit. For development, use `run_eval.py --index N` to test individual questions instead of running the full eval repeatedly.

5. **Source field optionality**: For data-dependent questions answered via `query_api`, there may not be a wiki source. The `source` field is now optional (can be an empty string).

### Tool Description Design

Effective tool descriptions are critical. Key principles:
- Be explicit about when to use each tool
- Provide concrete examples of parameter values
- Explain what the tool returns
- Mention authentication requirements

## Testing

Run the regression tests:

```bash
uv run pytest tests/test_agent.py -v
```

Tests verify:
- Agent exits with code 0
- Output is valid JSON
- `answer`, `source`, and `tool_calls` fields exist
- Correct tools are called for specific question types:
  - Wiki questions → `read_file`, `list_files`
  - System facts → `read_file`
  - Data queries → `query_api`

## Files

- `agent.py` - Main CLI agent with agentic loop
- `.env.agent.secret` - LLM configuration (gitignored)
- `.env.docker.secret` - Backend API key (gitignored)
- `tests/test_agent.py` - Regression tests (5 tests)
- `plans/task-1.md` - Task 1 implementation plan
- `plans/task-2.md` - Task 2 implementation plan
- `plans/task-3.md` - Task 3 implementation plan with benchmark notes
