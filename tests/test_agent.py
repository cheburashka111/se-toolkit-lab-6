"""Regression tests for agent.py CLI.

These tests run agent.py as a subprocess and verify the JSON output structure.
Run with: uv run pytest tests/test_agent.py -v
"""

import json
import subprocess


def test_agent_output_structure():
    """Test that agent.py outputs valid JSON with required fields.

    This test:
    1. Runs agent.py with a simple test question
    2. Parses stdout as JSON
    3. Verifies 'answer' field exists and is non-empty
    4. Verifies 'source' field exists
    5. Verifies 'tool_calls' field exists and is an array
    """
    # Run agent.py as a subprocess using uv run
    result = subprocess.run(
        ["uv", "run", "agent.py", "What is 2+2?"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed with stderr: {result.stderr}"

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {e}\nStdout: {result.stdout}")

    # Verify 'answer' field exists and is non-empty
    assert "answer" in output, "Missing 'answer' field in output"
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert len(output["answer"].strip()) > 0, "'answer' must not be empty"

    # Verify 'source' field exists
    assert "source" in output, "Missing 'source' field in output"
    assert isinstance(output["source"], str), "'source' must be a string"

    # Verify 'tool_calls' field exists and is an array
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be an array"


def test_merge_conflict_question():
    """Test that agent uses read_file to answer git workflow questions.

    This test:
    1. Runs agent.py with a merge conflict question
    2. Verifies read_file is in tool_calls
    3. Verifies wiki/git-workflow.md is in the source
    """
    result = subprocess.run(
        ["uv", "run", "agent.py", "How do you resolve a merge conflict?"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed with stderr: {result.stderr}"

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {e}\nStdout: {result.stdout}")

    # Verify tool_calls contains read_file
    tools_used = [call["tool"] for call in output["tool_calls"]]
    assert "read_file" in tools_used, f"Expected read_file in tool_calls, got: {tools_used}"

    # Verify source contains wiki/git-workflow.md
    assert "wiki/git-workflow.md" in output["source"], \
        f"Expected wiki/git-workflow.md in source, got: {output['source']}"


def test_wiki_listing_question():
    """Test that agent uses list_files to answer wiki directory questions.

    This test:
    1. Runs agent.py with a wiki listing question
    2. Verifies list_files is in tool_calls
    """
    result = subprocess.run(
        ["uv", "run", "agent.py", "What files are in the wiki?"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed with stderr: {result.stderr}"

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {e}\nStdout: {result.stdout}")

    # Verify tool_calls contains list_files
    tools_used = [call["tool"] for call in output["tool_calls"]]
    assert "list_files" in tools_used, f"Expected list_files in tool_calls, got: {tools_used}"


if __name__ == "__main__":
    test_agent_output_structure()
    test_merge_conflict_question()
    test_wiki_listing_question()
    print("All tests passed!")
