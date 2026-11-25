import pytest


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["keys_configured"] == 2
    assert data["cache_enabled"] is True


def test_chat_live_inference_and_caching(client):
    # Session 1: First message should be LIVE_INFERENCE
    payload1 = {
        "session_id": "test-session-1",
        "message": "What is the capital of France?",
        "system_prompt": "You are a helpful assistant."
    }
    resp1 = client.post("/chat", json=payload1)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["session_id"] == "test-session-1"
    assert "Paris" in data1["reply"]
    assert data1["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert data1["metadata"]["key_id"] == "key_1"
    assert data1["metadata"]["fallback_attempts"] == 0
    assert data1["metadata"]["input_tokens"] > 0
    assert data1["metadata"]["output_tokens"] > 0
    assert data1["metadata"]["latency_ms"] >= 0

    # Session 2: Same first message and system prompt -> should be LLM_CACHE
    payload2 = {
        "session_id": "test-session-2",
        "message": "What is the capital of France?",
        "system_prompt": "You are a helpful assistant."
    }
    resp2 = client.post("/chat", json=payload2)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["session_id"] == "test-session-2"
    assert data2["reply"] == data1["reply"]
    assert data2["metadata"]["resolution_source"] == "LLM_CACHE"
    assert data2["metadata"]["key_id"] is None
    assert data2["metadata"]["fallback_attempts"] == 0
    # Token usage matches cached response
    assert data2["metadata"]["input_tokens"] == data1["metadata"]["input_tokens"]
    assert data2["metadata"]["output_tokens"] == data1["metadata"]["output_tokens"]

    # Different message in session 3 -> must NOT come from cache
    payload3 = {
        "session_id": "test-session-3",
        "message": "Who are you?",
        "system_prompt": "You are a helpful assistant."
    }
    resp3 = client.post("/chat", json=payload3)
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert data3["metadata"]["key_id"] == "key_1"


def test_chat_failover_single_key(client):
    # Simulate key_1=429: should failover to key_2 with 200
    payload = {
        "session_id": "test-failover-1",
        "message": "Testing failover from key 1"
    }
    headers = {"X-Simulate-Failure": "key_1=429"}
    resp = client.post("/chat", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["key_id"] == "key_2"
    assert data["metadata"]["fallback_attempts"] == 1
    assert data["metadata"]["resolution_source"] == "LIVE_INFERENCE"

    # Simulate key_1=500: should also failover to key_2
    payload2 = {
        "session_id": "test-failover-2",
        "message": "Testing 500 error failover"
    }
    headers2 = {"X-Simulate-Failure": "key_1=500"}
    resp2 = client.post("/chat", json=payload2, headers=headers2)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["metadata"]["key_id"] == "key_2"
    assert data2["metadata"]["fallback_attempts"] == 1


def test_chat_failover_all_keys_failed(client):
    # Simulate *=429: all keys fail -> 503 {"detail": "all providers unavailable"}
    session_id = "test-all-failed"
    payload = {
        "session_id": session_id,
        "message": "This request should fail on all keys"
    }
    headers = {"X-Simulate-Failure": "*=429"}
    resp = client.post("/chat", json=payload, headers=headers)
    assert resp.status_code == 503
    data = resp.json()
    assert data["detail"] == "all providers unavailable"

    # Verify nothing was added to history
    history_resp = client.get(f"/sessions/{session_id}/messages")
    assert history_resp.status_code == 404
    assert history_resp.json()["detail"] == "session not found"


def test_validation_errors(client):
    # Missing session_id
    resp = client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 422
    assert "detail" in resp.json()

    # Empty message
    resp = client.post("/chat", json={"session_id": "s1", "message": "   "})
    assert resp.status_code == 422
    assert "detail" in resp.json()

    # Message over 4000 characters
    long_msg = "a" * 4001
    resp = client.post("/chat", json={"session_id": "s1", "message": long_msg})
    assert resp.status_code == 422
    assert "detail" in resp.json()

    # Malformed JSON
    resp = client.post(
        "/chat",
        content="not a json",
        headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_sessions_history_and_multiturn(client):
    session_id = "s-multiturn-123"

    # First turn
    resp1 = client.post("/chat", json={
        "session_id": session_id,
        "message": "First message"
    })
    assert resp1.status_code == 200

    # Second turn
    resp2 = client.post("/chat", json={
        "session_id": session_id,
        "message": "Second message"
    })
    assert resp2.status_code == 200

    # Retrieve history
    hist_resp = client.get(f"/sessions/{session_id}/messages")
    assert hist_resp.status_code == 200
    data = hist_resp.json()
    assert data["session_id"] == session_id
    messages = data["messages"]
    assert len(messages) == 4  # 2 user messages, 2 assistant messages

    # Check chronological ordering
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "First message"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["metadata"]["resolution_source"] is not None
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "Second message"
    assert messages[3]["role"] == "assistant"


def test_unknown_session_not_found(client):
    resp = client.get("/sessions/nonexistent-session-id/messages")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "session not found"}
