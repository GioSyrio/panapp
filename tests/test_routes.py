#!/usr/bin/env python3
"""Test: API routes — health, session start, chat, hints."""
import os, sys, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import app

client = app.test_client()

def test_health():
    resp = client.get("/health")
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["deepseek_ready"] == True
    assert data["questions_loaded"] > 0

def test_subjects():
    resp = client.get("/api/subjects")
    data = resp.get_json()
    assert len(data["subjects"]) >= 3
    ids = [s["id"] for s in data["subjects"]]
    assert "informatics" in ids
    assert "mathematics_prosanatolismoy" in ids
    assert "fysiki_prosanatolismoy" in ids

def test_session_start():
    for subj in ["informatics", "mathematics_prosanatolismoy", "fysiki_prosanatolismoy"]:
        resp = client.post("/api/session/start", json={"subject": subj})
        data = resp.get_json()
        assert "session_id" in data
        assert "question" in data
        assert data["question"]["id"] is not None
        assert len(data["question"]["question_html"]) > 0

def test_chat():
    resp = client.post("/api/session/start", json={"subject": "informatics"})
    sid = resp.get_json()["session_id"]
    
    # Solution
    resp = client.post("/api/chat", json={"session_id": sid, "message": "λύση"})
    data = resp.get_json()
    assert data["is_solution"] == True
    
    # Next
    resp = client.post("/api/chat", json={"session_id": sid, "message": "next"})
    data = resp.get_json()
    assert data["next_question"] == True

def test_hint():
    resp = client.post("/api/session/start", json={"subject": "fysiki_prosanatolismoy"})
    sid = resp.get_json()["session_id"]
    resp = client.post("/api/session/hint", json={"session_id": sid, "hint_state": {}})
    data = resp.get_json()
    assert "html" in data or "reply" in data

def test_jump():
    resp = client.post("/api/session/start", json={"subject": "mathematics_prosanatolismoy"})
    sid = resp.get_json()["session_id"]
    resp = client.post("/api/session/jump", json={"session_id": sid, "question_id": 23196})
    data = resp.get_json()
    assert data["question"]["id"] == 23196

def test_humanities_session():
    """Test session start for a humanities subject."""
    resp = client.post("/api/session/start", json={"subject": "istoria"})
    data = resp.get_json()
    assert "session_id" in data
    assert "question" in data
    assert data["question"]["id"] is not None
    assert len(data["question"]["question_html"]) > 0
    # Verify subject config is returned
    assert data["subject"]["name"] == "Ιστορία"

def test_humanities_chat():
    """Test chat commands for humanities."""
    resp = client.post("/api/session/start", json={"subject": "istoria"})
    sid = resp.get_json()["session_id"]
    
    # Solution command
    resp = client.post("/api/chat", json={"session_id": sid, "message": "λύση"})
    data = resp.get_json()
    assert data["is_solution"] == True
    
    # Next command
    resp = client.post("/api/chat", json={"session_id": sid, "message": "επόμενο"})
    data = resp.get_json()
    assert data["next_question"] == True

def test_humanities_hint():
    """Test hint functionality for humanities."""
    resp = client.post("/api/session/start", json={"subject": "neoelliniki_glossa_kai_logotechnia"})
    sid = resp.get_json()["session_id"]
    resp = client.post("/api/session/hint", json={"session_id": sid, "hint_state": {}})
    data = resp.get_json()
    assert "html" in data or "reply" in data

if __name__ == "__main__":
    tests = [test_health, test_subjects, test_session_start, test_chat, test_hint, test_jump,
             test_humanities_session, test_humanities_chat, test_humanities_hint]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed")