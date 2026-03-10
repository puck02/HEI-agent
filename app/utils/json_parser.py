"""
JSON parsing utilities for LLM responses.
Handles markdown-wrapped JSON from various LLM providers.
"""

import json
import re
from typing import Any


def extract_json_from_response(content: str) -> str:
    """
    Extract JSON from LLM response that might be wrapped in markdown code blocks.
    
    Handles formats like:
    - ```json\n{...}\n```
    - ```\n{...}\n```
    - Raw JSON
    - JSON with leading/trailing whitespace or text
    """
    if not content:
        return content
    
    content = content.strip()
    
    # Try to extract from ```json ... ``` blocks
    json_block_match = re.search(r'```json\s*([\s\S]*?)\s*```', content, re.IGNORECASE)
    if json_block_match:
        return json_block_match.group(1).strip()
    
    # Try to extract from ``` ... ``` blocks
    code_block_match = re.search(r'```\s*([\s\S]*?)\s*```', content)
    if code_block_match:
        extracted = code_block_match.group(1).strip()
        # Verify it looks like JSON
        if extracted.startswith('{') or extracted.startswith('['):
            return extracted
    
    # Try to find JSON object/array in the content
    # Find first { or [ and match to corresponding closing bracket
    # Check both, pick whichever appears first in the content
    candidates = []
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start_idx = content.find(start_char)
        if start_idx != -1:
            candidates.append((start_idx, start_char, end_char))
    
    # Sort by position — prefer the bracket that appears first
    candidates.sort(key=lambda x: x[0])
    
    for start_idx, start_char, end_char in candidates:
            # Find the matching closing bracket
            depth = 0
            in_string = False
            escape_next = False
            for i, char in enumerate(content[start_idx:], start=start_idx):
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\':
                    escape_next = True
                    continue
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == start_char:
                    depth += 1
                elif char == end_char:
                    depth -= 1
                    if depth == 0:
                        return content[start_idx:i+1]
    
    # Return original content if no extraction possible
    return content


def parse_llm_json(content: str) -> Any:
    """
    Parse JSON from LLM response, handling markdown wrapping.
    
    Args:
        content: Raw LLM response content
        
    Returns:
        Parsed JSON data
        
    Raises:
        json.JSONDecodeError: If JSON parsing fails after extraction
    """
    extracted = extract_json_from_response(content)
    return json.loads(extracted)
