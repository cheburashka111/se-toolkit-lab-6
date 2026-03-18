#!/usr/bin/env python3
"""
Agent CLI - Connects to an LLM and answers questions using tools.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON with 'answer', 'source' (optional), and 'tool_calls' fields to stdout.
    All debug/error messages go to stderr.
"""

import json
import os
import sys
import time
from pathlib import Path

import httpx


# Project root is the directory containing agent.py
PROJECT_ROOT = Path(__file__).parent.resolve()

# Maximum tool calls per question
MAX_TOOL_CALLS = 10


def load_env() -> dict[str, str]:
    """Load environment variables from .env.agent.secret and .env.docker.secret."""
    env_vars = {}
    
    # Load LLM config from .env.agent.secret
    env_file = PROJECT_ROOT / ".env.agent.secret"
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    
    # Load LMS_API_KEY from .env.docker.secret
    docker_env_file = PROJECT_ROOT / ".env.docker.secret"
    if docker_env_file.exists():
        with open(docker_env_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    # Only add if not already set
                    if key.strip() not in env_vars:
                        env_vars[key.strip()] = value.strip()
    
    return env_vars


def get_llm_config(env_vars: dict[str, str]) -> tuple[str, str, str]:
    """Extract LLM configuration from environment variables."""
    api_key = env_vars.get("LLM_API_KEY")
    api_base = env_vars.get("LLM_API_BASE")
    model = env_vars.get("LLM_MODEL")

    if not api_key or api_key == "your-llm-api-key-here":
        print("Error: LLM_API_KEY not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    if not api_base:
        print("Error: LLM_API_BASE not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    if not model:
        print("Error: LLM_MODEL not set in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    return api_key, api_base, model


def is_safe_path(path: str) -> bool:
    """Check if path is safe (no traversal outside project)."""
    # Reject absolute paths
    if path.startswith('/'):
        return False
    # Reject path traversal
    if '..' in path:
        return False
    # Resolve and check it's within project root
    try:
        resolved = (PROJECT_ROOT / path).resolve()
        return str(resolved).startswith(str(PROJECT_ROOT))
    except Exception:
        return False


def read_file(path: str) -> str:
    """Read the contents of a file in the project repository.
    
    Args:
        path: Relative path from project root
        
    Returns:
        File contents as string, or error message if file doesn't exist
    """
    if not is_safe_path(path):
        return f"Error: Unsafe path '{path}' - path traversal not allowed"
    
    file_path = PROJECT_ROOT / path
    
    if not file_path.exists():
        return f"Error: File '{path}' not found"
    
    if not file_path.is_file():
        return f"Error: '{path}' is not a file"
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """List files and directories at a given path.

    Args:
        path: Relative directory path from project root

    Returns:
        Newline-separated listing of entries, or error message
    """
    if not is_safe_path(path):
        return f"Error: Unsafe path '{path}' - path traversal not allowed"

    dir_path = PROJECT_ROOT / path

    if not dir_path.exists():
        return f"Error: Directory '{path}' not found"

    if not dir_path.is_dir():
        return f"Error: '{path}' is not a directory"

    try:
        entries = sorted(dir_path.iterdir())
        lines = [entry.name for entry in entries]
        return '\n'.join(lines)
    except Exception as e:
        return f"Error listing directory: {e}"


def query_api(method: str, path: str, body: str = None) -> str:
    """Call the backend API with authentication.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        path: API path (e.g., '/items/', '/analytics/completion-rate')
        body: JSON request body for POST/PUT (optional)

    Returns:
        JSON string with status_code and body
    """
    # Get configuration from environment
    lms_api_key = os.environ.get("LMS_API_KEY")
    agent_api_base_url = os.environ.get("AGENT_API_BASE_URL", "http://localhost:42001")
    
    if not lms_api_key:
        return json.dumps({
            "status_code": 401,
            "body": "Error: LMS_API_KEY not set in environment"
        })
    
    url = f"{agent_api_base_url}{path}"
    
    # Backend uses Bearer token authentication
    headers = {
        "Authorization": f"Bearer {lms_api_key}",
        "Content-Type": "application/json",
    }
    
    print(f"  Executing query_api({method} {path})", file=sys.stderr)
    
    try:
        with httpx.Client(timeout=30.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                data = json.loads(body) if body else {}
                response = client.post(url, headers=headers, json=data)
            elif method.upper() == "PUT":
                data = json.loads(body) if body else {}
                response = client.put(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            else:
                return json.dumps({
                    "status_code": 400,
                    "body": f"Error: Unsupported method '{method}'"
                })
            
            result = {
                "status_code": response.status_code,
                "body": response.text
            }
            return json.dumps(result)
    except httpx.ConnectError as e:
        return json.dumps({
            "status_code": 0,
            "body": f"Error: Cannot connect to API at {url} - {e}"
        })
    except Exception as e:
        return json.dumps({
            "status_code": 0,
            "body": f"Error: {e}"
        })


def get_tool_schemas() -> list[dict]:
    """Return the tool schemas for LLM function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file in the project repository. Use this to read documentation files in the wiki/ directory to find answers, or to read source code files (pyproject.toml, backend/*.py) for system facts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path from project root (e.g., 'wiki/git-workflow.md', 'pyproject.toml', 'backend/main.py')"
                        }
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories at a given path. Use this to discover what files exist in a directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from project root (e.g., 'wiki', 'backend')"
                        }
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": "Call the backend API to query data or check system status. Use for questions about item counts, scores, analytics, or to test endpoints. For data-dependent questions like 'How many items...' or 'What is the completion rate...'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "description": "HTTP method (GET, POST, PUT, DELETE)"
                        },
                        "path": {
                            "type": "string",
                            "description": "API path (e.g., '/items/', '/analytics/completion-rate', '/health')"
                        },
                        "body": {
                            "type": "string",
                            "description": "JSON request body for POST/PUT requests (optional)"
                        }
                    },
                    "required": ["method", "path"]
                }
            }
        }
    ]


def execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return the result.

    Args:
        name: Tool name ('read_file', 'list_files', or 'query_api')
        args: Tool arguments

    Returns:
        Tool result as string
    """
    if name == "read_file":
        path = args.get("path", "")
        print(f"  Executing read_file('{path}')", file=sys.stderr)
        return read_file(path)
    elif name == "list_files":
        path = args.get("path", "")
        print(f"  Executing list_files('{path}')", file=sys.stderr)
        return list_files(path)
    elif name == "query_api":
        method = args.get("method", "GET")
        path = args.get("path", "")
        body = args.get("body")
        print(f"  Executing query_api({method} {path})", file=sys.stderr)
        return query_api(method, path, body)
    else:
        return f"Error: Unknown tool '{name}'"


SYSTEM_PROMPT = """You are a documentation and system assistant. You have access to tools that let you read files, list directories, and query the backend API.

Tool selection guide:
1. **Wiki/documentation questions** ("According to the wiki...", "What files are in...") → use list_files and read_file on wiki/ directory
2. **System facts** ("What framework...", "What port...", "What status code...") → use read_file on source code (pyproject.toml, backend/main.py, backend/*.py)
3. **Data-dependent questions** ("How many items...", "What is the score...", "What is the completion rate...") → use query_api to fetch live data
4. **Bug diagnosis** → use query_api to reproduce the issue, then read_file to find the buggy code
5. **General knowledge** (math, facts unrelated to the project) → answer directly without tools

When using read_file for wiki questions:
- Find the exact section that answers the question
- Include a source reference in the format: filepath.md#section-anchor
- Section anchors are lowercase with hyphens (e.g., "resolving-merge-conflicts")

For data-dependent questions, always use query_api - do not guess values.

Always provide a complete answer. Never respond with an empty answer."""


def call_llm(
    messages: list[dict],
    api_key: str,
    api_base: str,
    model: str,
    tools: list[dict] = None,
    timeout: float = 60.0
) -> dict:
    """Call the LLM API and return the response.
    
    Args:
        messages: List of message dicts in OpenAI format
        api_key: API key for authentication
        api_base: Base URL for the API
        model: Model name
        tools: Optional list of tool schemas
        timeout: Request timeout in seconds
        
    Returns:
        LLM response data dict
    """
    url = f"{api_base}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body = {
        "model": model,
        "messages": messages,
    }
    
    if tools:
        body["tools"] = tools

    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=body)

        if response.status_code == 429:
            print("Error: Rate limited by the API provider", file=sys.stderr)
            try:
                error_data = response.json()
                print(f"Details: {error_data}", file=sys.stderr)
            except Exception:
                print(f"Response: {response.text}", file=sys.stderr)
            print("Try again later or switch to a different free model", file=sys.stderr)
            sys.exit(1)

        response.raise_for_status()
        return response.json()


def extract_source_from_messages(messages: list[dict]) -> str:
    """Try to extract source reference from the conversation.
    
    Looks for file paths mentioned in tool calls or answers.
    """
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if content:
                # Look for wiki/*.md patterns
                import re
                matches = re.findall(r'wiki/[\w-]+\.md', content)
                if matches:
                    # Also look for section anchor
                    anchor_match = re.search(r'wiki/[\w-]+\.md#[\w-]+', content)
                    if anchor_match:
                        return anchor_match.group()
                    return matches[0]
    return ""


def main() -> None:
    """Main entry point."""
    # Parse command-line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"Your question here\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    # Load configuration
    env_vars = load_env()
    api_key, api_base, model = get_llm_config(env_vars)

    print(f"Using model: {model}", file=sys.stderr)

    # Initialize messages with system prompt
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question}
    ]

    # Get tool schemas
    tools = get_tool_schemas()

    # Track all tool calls for output
    all_tool_calls = []

    # Agentic loop
    tool_call_count = 0
    start_time = time.time()

    while tool_call_count < MAX_TOOL_CALLS:
        print(f"\n[Loop iteration {tool_call_count + 1}]", file=sys.stderr)
        print("Calling LLM API...", file=sys.stderr)

        # Call LLM
        response_data = call_llm(messages, api_key, api_base, model, tools)

        # Extract assistant message
        try:
            assistant_message = response_data["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            print(f"Error: Unexpected API response format: {e}", file=sys.stderr)
            print(f"Response: {response_data}", file=sys.stderr)
            sys.exit(1)

        # Check for tool calls
        tool_calls = assistant_message.get("tool_calls", [])

        if not tool_calls:
            # No tool calls - this is the final answer
            print("LLM provided final answer (no tool calls)", file=sys.stderr)
            # Add the assistant message to messages so we can extract the answer
            messages.append(assistant_message)
            break

        # Add assistant message with tool calls to messages
        messages.append(assistant_message)

        # Execute each tool call
        for tool_call in tool_calls:
            tool_call_id = tool_call.get("id")
            function = tool_call.get("function", {})
            tool_name = function.get("name")
            
            # Parse arguments - OpenRouter uses 'arguments' (string JSON)
            try:
                arguments_str = function.get("arguments", "{}")
                tool_args = json.loads(arguments_str) if arguments_str else {}
            except json.JSONDecodeError:
                tool_args = {}

            print(f"Tool call: {tool_name} with args {tool_args}", file=sys.stderr)

            # Execute tool
            tool_result = execute_tool(tool_name, tool_args)

            # Record tool call for output
            all_tool_calls.append({
                "tool": tool_name,
                "args": tool_args,
                "result": tool_result
            })

            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": tool_result
            })

            tool_call_count += 1

    else:
        # Hit max tool calls
        print(f"Reached maximum tool calls ({MAX_TOOL_CALLS})", file=sys.stderr)

    # Get final answer from last assistant message
    final_answer = ""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content")
            # Check if this is a plain message (no tool_calls) or has content
            if content and not msg.get("tool_calls"):
                final_answer = content
                break
            # Also accept messages with content even if they had tool_calls
            if content and final_answer == "":
                final_answer = content

    # If still no answer, try to get any non-empty content
    if not final_answer:
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                final_answer = msg.get("content")
                break

    # Try to extract source
    source = extract_source_from_messages(messages)
    
    # If no source found, try to infer from last read_file call
    if not source and all_tool_calls:
        for call in reversed(all_tool_calls):
            if call["tool"] == "read_file":
                source = call["args"].get("path", "")
                break

    elapsed = time.time() - start_time
    print(f"\nCompleted in {elapsed:.2f}s", file=sys.stderr)

    # Output JSON result
    result = {
        "answer": final_answer,
        "source": source,
        "tool_calls": all_tool_calls,
    }

    # Output only valid JSON to stdout
    print(json.dumps(result))


if __name__ == "__main__":
    main()
