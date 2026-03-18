# Task 2: The Documentation Agent

## Overview

Extend the agent from Task 1 to support tool calling. The agent will have two tools (`read_file`, `list_files`) to navigate the project wiki and answer questions based on actual documentation.

## LLM Provider

- **Provider**: OpenRouter (same as Task 1)
- **Model**: `arcee-ai/trinity-mini:free` (supports tool calling)
- **API**: OpenAI-compatible chat completions endpoint

## Tool Definitions

### `read_file`

Reads a file from the project repository.

- **Parameters**: `path` (string) — relative path from project root
- **Returns**: File contents as string, or error message if file doesn't exist
- **Security**: Reject paths with `../` traversal or absolute paths

### `list_files`

Lists files and directories at a given path.

- **Parameters**: `path` (string) — relative directory path from project root
- **Returns**: Newline-separated listing of entries
- **Security**: Reject paths with `../` traversal or paths outside project directory

## Tool Schemas (Function Calling)

Tools will be defined as OpenAI-compatible function schemas:

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file in the project repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path from project root"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given path",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path from project root"}
                },
                "required": ["path"]
            }
        }
    }
]
```

## Agentic Loop

The agent will implement the following loop:

1. **Send**: User question + tool definitions + system prompt to LLM
2. **Receive**: LLM response with either:
   - `tool_calls` array → execute tools, append results, go to step 1
   - Text message (no tool calls) → final answer, output JSON and exit
3. **Limit**: Maximum 10 tool calls per question

### Message Format

Messages will follow OpenAI chat format:

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question}
]

# After each tool call:
messages.append({"role": "assistant", "content": None, "tool_calls": [...]})
messages.append({"role": "tool", "tool_call_id": "...", "content": tool_result})
```

### System Prompt Strategy

The system prompt will instruct the LLM to:
1. Use `list_files` to discover wiki files
2. Use `read_file` to find specific information
3. Always include a source reference (file path + section anchor) in the answer
4. Call tools iteratively until it has enough information

## Path Security

Both tools will validate paths:

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

## Output Format

```json
{
  "answer": "The LLM's answer",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."},
    {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
  ]
}
```

## Implementation Steps

1. Add `PROJECT_ROOT` constant for path resolution
2. Implement `read_file` tool with security checks
3. Implement `list_files` tool with security checks
4. Define tool schemas for LLM
5. Update `call_llm` to support tool calling (messages array, tools parameter)
6. Implement agentic loop in `main()`
7. Track tool calls with results for output
8. Extract source from LLM answer (or infer from last read_file)
9. Update output JSON to include `source` field

## Testing Strategy

Two regression tests:

1. **Test merge conflict question**: `"How do you resolve a merge conflict?"`
   - Expects `read_file` in tool_calls
   - Expects `wiki/git-workflow.md` in source

2. **Test wiki listing question**: `"What files are in the wiki?"`
   - Expects `list_files` in tool_calls
