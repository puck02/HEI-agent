#!/usr/bin/env python3
"""Comprehensive chat endpoint test."""
import json
import subprocess
import time
import sys

BASE = "http://localhost:8011"

def curl_post(url, data, token=None):
    headers = ["-H", "Content-Type: application/json"]
    if token:
        headers += ["-H", f"Authorization: Bearer {token}"]
    cmd = ["curl", "-s", "-X", "POST", url] + headers + ["-d", json.dumps(data)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return json.loads(result.stdout)

# Login
print("Logging in...")
login = curl_post(f"{BASE}/auth/login", {"username": "abc", "password": "Test123456"})
if "access_token" not in login:
    print(f"Login failed: {login}")
    sys.exit(1)
token = login["access_token"]
print("Login OK\n")

# Tests
tests = [
    ("1. Simple greeting", "你好"),
    ("2. Health complaint (was empty)", "我最近身体不太舒服"),
    ("3. Health risk analysis (was empty)", "你觉得我的身体有什么潜在的隐患吗"),
    ("4. Health status analysis", "分析一下我的健康状况"),
    ("5. Model identity", "你是什么模型？"),
    ("6. Do you know me?", "你了解我吗？"),
]

session_id = None
results = []
for name, message in tests:
    print(f"=== {name} ===")
    print(f"Message: {message}")
    start = time.time()
    body = {"message": message}
    if session_id:
        body["session_id"] = session_id
    resp = curl_post(f"{BASE}/api/v1/chat", body, token)
    elapsed = round(time.time() - start, 1)
    
    answer = resp.get("answer", "")
    session_id = resp.get("session_id", session_id)
    agent = resp.get("agent_used", "")
    
    status = "OK" if len(answer) > 0 else "EMPTY!"
    print(f"Status: {status} | Length: {len(answer)} | Time: {elapsed}s | Agent: {agent}")
    print(f"Answer: {answer[:200]}")
    print()
    results.append((name, status, len(answer), elapsed))
    
    # Brief pause between requests to avoid rate limiting
    time.sleep(3)

# Summary
print("=" * 60)
print("SUMMARY")
print("=" * 60)
all_ok = True
for name, status, length, elapsed in results:
    flag = "✅" if status == "OK" else "❌"
    print(f"{flag} {name}: {status} (len={length}, {elapsed}s)")
    if status != "OK":
        all_ok = False

if all_ok:
    print("\nAll tests passed!")
else:
    print("\nSome tests FAILED!")
    sys.exit(1)
