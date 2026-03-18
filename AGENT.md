# Agent Architecture

## Overview

`agent.py` is a CLI tool that connects to an LLM via the OpenAI-compatible chat completions API. It implements an **agentic loop** with tool calling capabilities, allowing the LLM to interact with the local file system through `read_file` and `list_files` tools to answer questions based on actual project documentation.

## LLM Provider

- **Provider**: OpenRouter (openrouter.ai)
- **Model**: `arcee-ai/trinity-mini:free` (free tier with tool calling support)
- **API Endpoint**: `https://openrouter.ai/api/v1/chat/completions`

> **Note**: Free models on OpenRouter can be temporarily rate-limited. If you encounter 429 errors, try switching to a different free model in `.env.agent.secret`.

## Configuration

The agent reads configuration from `.env.agent.secret` in the project root:

```bash
LLM_API_KEY=sk-or-...           # Your OpenRouter API key
LLM_API_BASE=https://openrouter.ai/api/v1
LLM_MODEL=arcee-ai/trinity-mini:free
```

## Usage

```bash
uv run agent.py "Your question here"
```

### Example

```bash
$ uv run agent.py "How do you resolve a merge conflict?"
Using model: arcee-ai/trinity-mini:free

[Loop iteration 1]
Calling LLM API...
Tool call: list_files with args {'path': 'wiki'}
  Executing list_files('wiki')
Tool call: read_file with args {'path': 'wiki/git-workflow.md'}
  Executing read_file('wiki/git-workflow.md')

[Loop iteration 2]
Calling LLM API...
LLM provided final answer (no tool calls)

Completed in 8.42s
{"answer": "...", "source": "wiki/git-workflow.md#resolving-merge-conflicts", "tool_calls": [...]}
```

## Output Format

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "The LLM's response text",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "# Git workflow\n\n..."
    }
  ]
}
```

- `answer` (string, required): The LLM's answer to the question
- `source` (string, required): The wiki file path with optional section anchor that contains the answer
- `tool_calls` (array, required): All tool calls made during the agentic loop. Each entry has:
  - `tool`: Tool name (`read_file` or `list_files`)
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

1. **`load_env()`**: Loads environment variables from `.env.agent.secret`
2. **`get_llm_config()`**: Extracts and validates LLM configuration
3. **`is_safe_path()`**: Validates paths to prevent directory traversal attacks
4. **`read_file(path)`**: Reads file contents with security checks
5. **`list_files(path)`**: Lists directory contents with security checks
6. **`get_tool_schemas()`**: Returns OpenAI-compatible tool schemas
7. **`execute_tool(name, args)`**: Executes a tool by name with given arguments
8. **`call_llm(messages, tools)`**: Makes HTTP POST request to the LLM API with tool support
9. **`extract_source_from_messages()`**: Extracts source reference from conversation
10. **`main()`**: Entry point - implements the agentic loop

## Tool Definitions

### `read_file`

Reads the contents of a file in the project repository.

- **Parameters**: `path` (string) — relative path from project root
- **Returns**: File contents as string, or error message if file doesn't exist
- **Security**: Rejects paths with `../` traversal or absolute paths

### `list_files`

Lists files and directories at a given path.

- **Parameters**: `path` (string) — relative directory path from project root
- **Returns**: Newline-separated listing of entries, or error message
- **Security**: Rejects paths with `../` traversal or paths outside project directory

## System Prompt

The system prompt instructs the LLM to:

1. Use `list_files` to discover what files exist in relevant directories
2. Use `read_file` to read the contents of specific files
3. Find the exact section that answers the question
4. Include a source reference in the format: `filepath.md#section-anchor`
5. Section anchors are lowercase with hyphens instead of spaces

## Path Security

Both tools validate paths to prevent directory traversal attacks:

```python
def is_safe_path(path: str) -> bool:
    """Check if path is safe (no traversal outside project)."""
    # Reject absolute paths
    if path.startswith('/'):
        return False
    # Reject path traversal
    if '..' in path:
        return False
    # Resolve and check it's within project root
    resolved = (PROJECT_ROOT / path).resolve()
    return str(resolved).startswith(str(PROJECT_ROOT))
```

## Error Handling

- **Missing API key**: Exits with error to stderr
- **Rate limit (429)**: Exits with helpful message suggesting retry or model switch
- **HTTP errors**: Exits with status code and error details
- **Timeout**: 60-second timeout on API calls
- **Invalid response**: Exits with parse error
- **Unsafe path**: Returns error message in tool result (doesn't crash)
- **File not found**: Returns error message in tool result

## Testing

Run the regression tests:

```bash
uv run pytest tests/test_agent.py -v
```

Tests verify:
- Agent exits with code 0
- Output is valid JSON
- `answer`, `source`, and `tool_calls` fields exist
- Tool calls are populated when tools are used
- Specific tools are called for specific questions

## Files

- `agent.py` - Main CLI agent with agentic loop
- `.env.agent.secret` - LLM configuration (gitignored)
- `tests/test_agent.py` - Regression tests
- `plans/task-1.md` - Task 1 implementation plan
- `plans/task-2.md` - Task 2 implementation plan
