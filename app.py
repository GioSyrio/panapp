#!/usr/bin/env python3
"""
Panhellenic AI Tutor — Flask Backend

Wraps the Python pipeline (predictor + prompts + DeepSeek) behind a REST API
and serves a single-page frontend for interactive tutoring.

Usage:
    python3 app.py                      # runs on http://localhost:5050
    DEEPSEEK_API_KEY=sk-... python3 app.py
    python3 app.py --port 8080
"""

import json
import os
import sys
import re
import uuid
import hashlib
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context

# ── Optional: OpenAI client (graceful if not installed) ──────────────────
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# ── Our modules ─────────────────────────────────────────────────────────
from predictor import calculate_topic_priorities, CURRENT_YEAR
from prompts import (
    GREEK_TUTOR_SYSTEM_PROMPT,
    EVALUATION_SYSTEM_PROMPT,
    PREDICTION_SYSTEM_PROMPT,
    CORRECT_ANSWER_PROMPT,
    PARTIAL_ANSWER_PROMPT,
    INCORRECT_ANSWER_PROMPT,
    COMMON_PANHELLENIC_TRAPS,
    build_trend_context,
)

# ── Config ───────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "trapeza_data_1_3_218")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions_classified.json")
QUESTIONS_V2_FILE = os.path.join(DATA_DIR, "questions_v2.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")

# ── Global state ─────────────────────────────────────────────────────────
exam_data = None
ranked = None
details = None
trend_context = None
deepseek_client = None
sessions = {}  # session_id → {messages, seen_ids, current_question, ...}


def load_data():
    """Load questions and compute priorities once on startup."""
    global exam_data, ranked, details, trend_context
    if not os.path.exists(QUESTIONS_FILE):
        print(f"ERROR: {QUESTIONS_FILE} not found. Run build_questions.py first.")
        sys.exit(1)
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        exam_data = json.load(f)
    ranked_priorities, details = calculate_topic_priorities(exam_data)
    noise = {"ΠΛΗΡΟΦΟΡΙΚΗ:", "ΑΕΠΠ:", ""}
    ranked = [(t, s) for t, s in ranked_priorities if t not in noise]
    trend_context = build_trend_context(ranked, details, top_n=5)
    print(f"Loaded {len(exam_data)} questions. {len(ranked)} topics ranked.")


def init_deepseek():
    """Initialize DeepSeek client if API key is set."""
    global deepseek_client
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("WARNING: DEEPSEEK_API_KEY not set. AI evaluation disabled.")
        return
    if not HAS_OPENAI:
        print("WARNING: openai package not installed. AI evaluation disabled.")
        return
    deepseek_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    print("DeepSeek client ready.")


# ── Helpers ──────────────────────────────────────────────────────────────

def pick_question(part, exclude_ids=None):
    """Select a question by priority for the given part."""
    exclude_ids = exclude_ids or set()
    part_data = [q for q in exam_data if q["part"] == part]
    for tag, _ in ranked[:15]:
        candidates = [
            q for q in part_data
            if tag in q.get("conceptual_tags", [])
            and q["id"] not in exclude_ids
        ]
        if candidates:
            candidates.sort(key=lambda q: len(q.get("conceptual_tags", [])), reverse=True)
            return candidates[0], tag
    # Fallback
    import random
    remaining = [q for q in part_data if q["id"] not in exclude_ids]
    if not remaining:
        remaining = [q for q in exam_data if q["id"] not in exclude_ids]
    return (random.choice(remaining), None) if remaining else (None, None)


def build_system_prompt(question):
    """Build the full system prompt with Greek tutor persona + exam context."""
    question_text = question.get("question_text", "")[:2500]
    answer_text = question.get("answer_text", "")[:2500]
    tags = ", ".join(question.get("conceptual_tags", [])[:5])

    return (
        GREEK_TUTOR_SYSTEM_PROMPT + "\n\n"
        "📋 Η ΑΣΚΗΣΗ ΠΟΥ ΔΟΥΛΕΥΕΙ Ο ΜΑΘΗΤΗΣ:\n"
        f"Θέμα: {question.get('part', '')} — {question.get('points', 0)} μονάδες\n"
        f"Έτος: {question.get('year', '')}\n"
        f"Έννοιες: {tags}\n\n"
        "ΕΚΦΩΝΗΣΗ:\n"
        f"{question_text}\n\n"
        "ΕΝΔΕΙΚΤΙΚΗ ΑΠΑΝΤΗΣΗ (για τη δική σου γνώση — ΜΗΝ την αποκαλύψεις εκτός αν ο μαθητής "
        "τη ζητήσει ρητά με 'λύση' ή 'δείξε μου την απάντηση'):\n"
        f"{answer_text}\n\n"
        + trend_context
    )


# ── Caching ──────────────────────────────────────────────────────────────

# Simple in-memory cache for AI responses
# Key: md5(system_prompt_hash + last_user_message), Value: assistant reply
_response_cache = {}
MAX_CACHE_SIZE = 200


def _cache_key(session):
    """Generate a cache key from the conversation context."""
    messages = session.get("messages", [])
    if len(messages) < 2:
        return None
    # Hash: system prompt (first msg) + last user message
    system = messages[0].get("content", "") if messages else ""
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = m.get("content", "")
            break
    raw = system + "|||" + last_user
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def strip_reasoning(text):
    """Clean DeepSeek output: remove <think>, normalize line endings, strip tabs."""
    if not text:
        return text
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\t', '    ')
    return text.strip()


def format_exam_question(question, tag=None):
    """Create a display-friendly version of the question for the frontend."""
    result = {
        "id": question["id"],
        "part": question["part"],
        "year": question["year"],
        "points": question["points"],
        "focus_tag": tag,
        "type": question.get("type", "open_ended_problem"),
        "question_text": question["question_text"],
        "tags": question.get("conceptual_tags", [])[:6],
    }

    # Inject pre-rendered HTML from questions_v2.json (DOCX-native) when available
    v2_data = _load_v2_data()
    qid_str = str(question["id"])
    if qid_str in v2_data:
        result["question_html"] = v2_data[qid_str].get("question_html", "")
        result["answer_html"] = v2_data[qid_str].get("answer_html", "")

    # Include all diagram images if available
    diagram_map = _load_diagram_map()
    if qid_str in diagram_map:
        diagrams = diagram_map[qid_str].get("diagrams", [])
        is_docx = diagram_map[qid_str].get("source") == "docx"
        result["diagram_urls"] = [
            {
                "path": d["path"].replace("static/", "", 1),
                "width": d.get("width", 0),
                "height": d.get("height", 0),
                "page": d.get("page", 1),
                "is_diagram": is_docx,
                "is_embedded": d.get("is_embedded", False),
                "is_subregion": d.get("is_subregion", False),
            }
            for d in diagrams
        ]
    else:
        result["diagram_urls"] = []

    return result


_v2_cache = None

def _load_v2_data():
    """Load questions_v2.json (lazy, cached)."""
    global _v2_cache
    if _v2_cache is not None:
        return _v2_cache
    v2_file = os.path.join(DATA_DIR, "questions_v2.json")
    if os.path.exists(v2_file):
        import json as _json
        with open(v2_file, encoding="utf-8") as f:
            arr = _json.load(f)
        _v2_cache = {str(q["id"]): q for q in arr}
    else:
        _v2_cache = {}
    return _v2_cache


_diagram_map_cache = None  # lazy-loaded cache


def _load_diagram_map():
    """Load the diagram map from disk (cached in memory)."""
    global _diagram_map_cache
    if _diagram_map_cache is not None:
        return _diagram_map_cache
    import json as _json
    import os as _os
    map_file = _os.path.join(STATIC_DIR, "images", "exams", "diagram_map.json")
    if _os.path.exists(map_file):
        with open(map_file, encoding="utf-8") as f:
            _diagram_map_cache = _json.load(f)
    else:
        _diagram_map_cache = {}
    return _diagram_map_cache


# ── Jinja Filter ───────────────────────────────────────────────────────────

PSEUDOCODE_KEYWORDS = re.compile(
    r'^(Αλγόριθμος\s+\w|ΠΡΟΓΡΑΜΜΑ|ΤΕΛΟΣ_ΠΡΟΓΡΑΜΜΑΤΟΣ|ΜΕΤΑΒΛΗΤΕΣ|ΑΚΕΡΑΙΕΣ|ΠΡΑΓΜΑΤΙΚΕΣ|'
    r'ΧΑΡΑΚΤΗΡΕΣ|ΛΟΓΙΚΕΣ|ΣΤΑΘΕΡΕΣ|ΑΡΧΗ\b|ΓΙΑ\s|ΟΣΟ\s|ΑΝ\s|\d{1,2}\s)'
)
SECTION_HEADER_RE = re.compile(r'^(ΘΕΜΑ\s+\d+)', re.IGNORECASE)
SUBQ_RE = re.compile(r'^(\d+\.\d+)\s+')
POINTS_RE = re.compile(r'Μονάδες\s+\d+', re.IGNORECASE)


def _line_is_code(line):
    """Detect if a line is pseudocode."""
    return bool(PSEUDOCODE_KEYWORDS.match(line.strip()))


def format_question_text(text):
    """Jinja filter: format raw question text into safe, styled HTML."""
    if not text:
        return ""

    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = text.split('\n')

    result = []
    in_code = False
    code_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_code:
                code_lines.append('')
            else:
                result.append('<br>')
            continue

        # Section headers (ΘΕΜΑ 2)
        sec_match = SECTION_HEADER_RE.match(stripped)
        if sec_match:
            if in_code:
                result.append(format_code_block(code_lines))
                code_lines = []
                in_code = False
            escaped = _escape(stripped)
            result.append(f'<div class="section-header">{escaped}</div>')
            continue

        # Check if next line continues code
        next_line = lines[lines.index(line) + 1].strip() if lines.index(line) + 1 < len(lines) else ''
        next_is_code = _line_is_code(next_line)

        if _line_is_code(stripped) and next_is_code and not in_code:
            in_code = True
            code_lines = [stripped]
            continue

        if in_code:
            if _line_is_code(stripped):
                code_lines.append(stripped)
                continue
            else:
                result.append(format_code_block(code_lines))
                code_lines = []
                in_code = False

        # Points info
        if POINTS_RE.match(stripped):
            result.append(f'<span class="points-badge">{_escape(stripped)}</span>')
            continue

        # Sub-question markers
        subq_match = SUBQ_RE.match(stripped)
        if subq_match:
            label = _escape(subq_match.group(1))
            rest = _escape(stripped[len(subq_match.group(0)):])
            result.append(f'<div class="subq-card"><strong>{label}</strong> {rest}</div>')
            continue

        # Plain text
        result.append(f'<p class="mb-1">{_escape(stripped)}</p>')

    if in_code and code_lines:
        result.append(format_code_block(code_lines))

    return '\n'.join(result)


def _escape(s):
    """Simple HTML escape."""
    return s.replace('&', '&').replace('<', '<').replace('>', '>').replace('"', '"')


def format_code_block(lines):
    """Format a block of pseudocode lines as a styled <pre> block."""
    code = '\n'.join(lines)
    escaped = _escape(code)
    return f'<pre class="code-block">{escaped}</pre>'


# Register the filter
app.jinja_env.filters['format_question_text'] = format_question_text


# ── Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the frontend."""
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/session/start", methods=["POST"])
def start_session():
    """Initialize a new tutoring session. Returns first question."""
    session_id = str(uuid.uuid4())
    # Pick Θέμα 2 first
    question, tag = pick_question("Θέμα 2")
    if not question:
        return jsonify({"error": "No questions available."}), 500

    system_prompt = build_system_prompt(question)
    sessions[session_id] = {
        "messages": [{"role": "system", "content": system_prompt}],
        "seen_ids": {question["id"]},
        "current_question": question,
        "current_tag": tag,
        "completed_count": 0,
        "total_points": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "history": [],  # list of previous questions: [{question, tag, messages, seen_ids_snapshot}]
    }

    return jsonify({
        "session_id": session_id,
        "question": format_exam_question(question, tag),
        "has_ai": deepseek_client is not None,
        "message": "Καλή αρχή! Γράψε την απάντησή σου ή ξεκίνα με ερωτήσεις.",
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    """Send a student message and get AI feedback."""
    body = request.get_json(force=True)
    session_id = body.get("session_id")
    user_input = body.get("message", "").strip()

    if not session_id or session_id not in sessions:
        return jsonify({"error": "Invalid session."}), 400
    if not user_input:
        return jsonify({"reply": None})

    session = sessions[session_id]
    session["messages"].append({"role": "user", "content": user_input})

    # Check for special commands
    cmd = user_input.lower()
    if cmd in {"exit", "quit", "έξοδος"}:
        return jsonify({"reply": "Η συνεδρία τερματίστηκε. Καλή επιτυχία! 🎓", "end_session": True})

    if cmd in {"λύση", "λυση", "solution", "απάντηση", "απαντηση"}:
        qid = str(session["current_question"]["id"])
        v2 = _load_v2_data().get(qid, {})
        # Prefer LLM-generated solution (offline), fall back to DOCX, then raw
        llm_html = v2.get("llm_solution_html", "")
        if llm_html:
            return jsonify({"is_solution": True, "answer_html": llm_html, "source": "llm"})
        answer_html = v2.get("answer_html", "")
        if answer_html:
            return jsonify({"is_solution": True, "answer_html": answer_html, "source": "docx"})
        answer = session["current_question"].get("answer_text", "Δεν υπάρχει καταχωρημένη λύση.")
        return jsonify({"reply": answer, "is_solution": True, "source": "raw"})

    if cmd in {"next", "επόμενο", "επομενο", "skip", "παράβλεψη"}:
        return jsonify({"reply": None, "next_question": True})

    # Hint command
    if cmd in {"hint", "βοήθεια", "βοηθεια", "help"}:
        return _handle_hint(session)

    # Call DeepSeek if available
    if deepseek_client and HAS_OPENAI:
        # Detect if this is a conversational message or an answer submission.
        # Short messages (<100 chars) without pseudocode keywords → conversational.
        # Messages with code-like patterns or substantial length → evaluation.
        # Answer detection: must have BOTH substantial length AND code-like structure
        # not just a long question or casual mention of algorithm concepts.
        code_keywords = [
            '←', '<-', 'τότε', 'επανάλαβε', 'διάβασε', 'γράψε', 'εμφάνισε',
            'mod', 'div', 'τέλος_επανάληψης', 'τέλος_αν', 'μέχρις_ότου',
            'περίπτωση', 'επίλεξε', 'αρχή_επανάληψης'
        ]
        has_code_structure = any(kw in user_input.lower() for kw in code_keywords)
        is_long = len(user_input) > 150
        has_newlines = '\n' in user_input
        # An answer must have code structure, OR be very long with newlines (multi-line pseudocode)
        is_answer = has_code_structure or (is_long and has_newlines)

        if not is_answer:
            # Conversational: use the tutor system prompt with chat history
            eval_messages = session["messages"].copy()
            eval_messages[-1] = {"role": "user", "content": user_input}
            try:
                response = deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=eval_messages,
                    temperature=0.4,
                    max_tokens=500,
                )
                reply = strip_reasoning(response.choices[0].message.content or "")
                if not reply:
                    reply = "Συγνώμη, κάτι πήγε στραβά. Μπορείς να ξαναπροσπαθήσεις;"
                session["messages"].append({"role": "assistant", "content": reply})
                return jsonify({"reply": reply, "conversational": True})
            except Exception as e:
                print(f"  ❌ DeepSeek (conversational) error: {e}")
                return jsonify({"reply": f"Ωχ! {e}"})

        # Answer submission: use structured JSON evaluation
        cache_hit = False
        key = _cache_key(session)

        if key and key in _response_cache:
            eval_data = _response_cache[key]
            cache_hit = True
            print(f"  ⚡ Cache hit for session {session_id[:8]}")
        else:
            try:
                # Build evaluation prompt with question context
                q = session["current_question"]
                qtype = q.get("type", "open_ended_problem")
                eval_messages = [
                    {"role": "system", "content": EVALUATION_SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"Ερώτηση ({qtype}): {q.get('question_text', '')[:2000]}\n\n"
                        f"Ενδεικτική απάντηση: {q.get('answer_text', '')[:1000]}\n\n"
                        f"Απάντηση μαθητή: {user_input}"
                    )}
                ]

                response = deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=eval_messages,
                    temperature=0.1,
                    max_tokens=600,
                    response_format={"type": "json_object"},
                )
                raw = response.choices[0].message.content or "{}"
                raw = strip_reasoning(raw)

                # Parse JSON, with safe fallback
                try:
                    eval_data = json.loads(raw)
                except json.JSONDecodeError:
                    # Try to extract JSON from markdown code block
                    m = re.search(r'\{.*\}', raw, re.DOTALL)
                    if m:
                        try:
                            eval_data = json.loads(m.group(0))
                        except json.JSONDecodeError:
                            eval_data = {"status": "info", "critique": raw[:300], "hint": "Μπορείς να μου εξηγήσεις τι σκέφτεσαι;"}
                    else:
                        eval_data = {"status": "info", "critique": raw[:300], "hint": "Μπορείς να μου εξηγήσεις τι σκέφτεσαι;"}

                # Populate cache
                if key:
                    if len(_response_cache) >= MAX_CACHE_SIZE:
                        oldest = next(iter(_response_cache))
                        del _response_cache[oldest]
                    _response_cache[key] = eval_data
                    print(f"  💾 Cached evaluation (key={key[:12]}...)")

            except Exception as e:
                print(f"  ❌ DeepSeek error: {e}")
                return jsonify({
                    "evaluation": {"status": "info", "critique": f"⚠️ Κάτι πήγε στραβά: {e}", "hint": "Δοκίμασε ξανά ή πληκτρολόγησε 'hint' για βοήθεια."},
                    "error": True,
                })

        session["messages"].append({"role": "assistant", "content": json.dumps(eval_data, ensure_ascii=False)})
        return jsonify({"evaluation": eval_data, "cached": cache_hit})

    # Fallback: friendly no-AI response
    return jsonify({
        "evaluation": {
            "status": "info",
            "critique": "Το AI evaluation είναι προσωρινά απενεργοποιημένο. Μπορείς να δεις την επίσημη λύση ή να προχωρήσεις στο επόμενο θέμα.",
            "hint": "Πληκτρολόγησε 'hint' για βοήθεια ή 'next' για το επόμενο θέμα."
        },
        "no_ai": True,
    })


@app.route("/api/session/next", methods=["POST"])
def next_question():
    """Move to the next question (alternating Θέμα 2 / Θέμα 4)."""
    body = request.get_json(force=True)
    session_id = body.get("session_id")

    if not session_id or session_id not in sessions:
        return jsonify({"error": "Invalid session."}), 400

    session = sessions[session_id]
    # Save current question to history before moving
    session.setdefault("history", []).append({
        "question": format_exam_question(session["current_question"], session.get("current_tag")),
        "messages": list(session["messages"]),
    })
    session["completed_count"] += 1
    session["total_points"] += session["current_question"]["points"]

    # Alternate
    if session["completed_count"] % 2 == 0:
        part = "Θέμα 2"
    else:
        part = "Θέμα 4"

    question, tag = pick_question(part, session["seen_ids"])
    if not question:
        return jsonify({
            "reply": "Δεν υπάρχουν άλλα θέματα. Εξαιρετική δουλειά! 🎓",
            "session_complete": True,
        })

    session["seen_ids"].add(question["id"])
    session["current_question"] = question
    session["current_tag"] = tag

    # Reset messages with new system prompt
    system_prompt = build_system_prompt(question)
    session["messages"] = [{"role": "system", "content": system_prompt}]

    return jsonify({
        "question": format_exam_question(question, tag),
        "stats": {
            "completed": session["completed_count"],
            "total_points": session["total_points"],
            "remaining": len(exam_data) - len(session["seen_ids"]),
        },
    })


@app.route("/api/session/previous", methods=["POST"])
def previous_question():
    """Go back to the previous question if available."""
    body = request.get_json(force=True)
    session_id = body.get("session_id")

    if not session_id or session_id not in sessions:
        return jsonify({"error": "Invalid session."}), 400

    session = sessions[session_id]
    history = session.get("history", [])
    if not history:
        return jsonify({"error": "No previous question."}), 400

    # Pop the last entry from history
    prev = history.pop()
    prev_question = prev["question"]
    prev_messages = prev["messages"]

    # Restore the previous question and messages
    question = next((q for q in exam_data if q["id"] == prev_question["id"]), None)
    if not question:
        return jsonify({"error": "Previous question not found in database."}), 500

    session["current_question"] = question
    session["current_tag"] = prev_question.get("focus_tag")
    session["messages"] = prev_messages
    session["completed_count"] = max(0, session["completed_count"] - 1)
    session["total_points"] = max(0, session["total_points"] - question.get("points", 0))

    return jsonify({
        "question": format_exam_question(question, session.get("current_tag")),
        "stats": {
            "completed": session["completed_count"],
            "total_points": session["total_points"],
            "remaining": len(exam_data) - len(session["seen_ids"]),
        },
        "has_previous": len(history) > 0,
    })


@app.route("/api/session/stats", methods=["POST"])
def session_stats():
    """Get current session statistics."""
    body = request.get_json(force=True)
    session_id = body.get("session_id")

    if not session_id or session_id not in sessions:
        return jsonify({"error": "Invalid session."}), 400

    session = sessions[session_id]
    return jsonify({
        "completed": session["completed_count"],
        "total_points": session["total_points"],
        "remaining": len(exam_data) - len(session["seen_ids"]),
        "total_questions": len(exam_data),
        "current_part": session["current_question"]["part"],
        "current_id": session["current_question"]["id"],
    })


@app.route("/api/topics", methods=["GET"])
def list_topics():
    """Return the top priority topics (for debug/transparency)."""
    top = [{"topic": t, "priority": round(s, 2)} for t, s in ranked[:10]]
    return jsonify({"topics": top, "total_topics": len(ranked), "target_year": CURRENT_YEAR})


# ── Hint system ──────────────────────────────────────────────────────────

def _get_subquestions(qid):
    """Extract sub-question numbers from a question's sections."""
    v2 = _load_v2_data().get(str(qid), {})
    sections = v2.get("sections", [])
    subs = [s for s in sections if s["type"] == "sub_question"]
    return [{"number": s["number"], "content": s.get("content", "")} for s in subs]


def _handle_hint(session):
    """Serve 3-tier Socratic hints (Level 1→2→3) per sub-question from pre-built data."""
    qid = str(session["current_question"]["id"])
    v2 = _load_v2_data().get(qid, {})

    subqs = _get_subquestions(qid)
    total_subqs = len(subqs) if subqs else 1

    hint_state = session.get("hint_state", {"subqIdx": 0, "hintCount": 0, "totalSubqs": total_subqs})
    sidx = hint_state.get("subqIdx", 0)
    hcnt = hint_state.get("hintCount", 0)
    hint_state["totalSubqs"] = total_subqs

    if sidx >= total_subqs:
        return jsonify({"all_done": True, "hint_state": hint_state,
                        "reply": "✅ Ολοκλήρωσες όλα τα υποερωτήματα! Πάμε στο επόμενο θέμα."})

    subq_num = subqs[sidx]["number"] if subqs else "?"
    subq_label = f"Υποερώτημα {subq_num}"
    current_level = hcnt + 1  # 1, 2, or 3

    # Get pre-built hint from offline data
    hints_data = v2.get("hints", [])
    hint_text = None

    if hints_data and sidx < len(hints_data):
        subq_hints = hints_data[sidx].get("hints", [])
        if hcnt < len(subq_hints):
            hint_text = subq_hints[hcnt].get("hint_text", "")

    if not hint_text:
        # Fallback: no pre-built hints yet — use answer text
        hint_state["subqIdx"] = sidx + 1
        hint_state["hintCount"] = 0
        session["hint_state"] = hint_state
        ans_html = v2.get("answer_html", "")
        if not ans_html:
            ans_text = session["current_question"].get("answer_text", "")
            ans_html = f'<div class="sol-step"><div class="sol-step-text">{ans_text}</div></div>'
        return jsonify({
            "html": ans_html,
            "hint_state": hint_state,
            "is_full_answer": True,
            "reply": f"📚 {subq_label} — Πλήρης λύση (δεν υπάρχουν προκατασκευασμένα hints ακόμα)."
        })

    hcnt += 1
    hint_state["hintCount"] = hcnt
    session["hint_state"] = hint_state

    if hcnt >= 4:
        # Max hints — show full answer
        hint_state["subqIdx"] = sidx + 1
        hint_state["hintCount"] = 0
        session["hint_state"] = hint_state
        ans_html = v2.get("answer_html", "")
        if not ans_html:
            ans_text = session["current_question"].get("answer_text", "")
            ans_html = f'<div class="sol-step"><div class="sol-step-text">{ans_text}</div></div>'
        return jsonify({
            "html": ans_html,
            "hint_state": hint_state,
            "is_full_answer": True,
            "reply": f"📚 {subq_label} — Πλήρης λύση. Μελέτησέ την και πάμε παρακάτω!"
        })

    level_labels = {1: "Έννοια", 2: "Δομή", 3: "Σκαλωσιά"}
    level_label = level_labels.get(current_level, str(current_level))

    html = f'<div class="hint-box"><b>{subq_label} • {level_label} (Επίπεδο {current_level}/3)</b><br><br>{hint_text}</div>'
    return jsonify({
        "html": html,
        "hint_state": hint_state,
        "subq_num": subq_num,
        "level": current_level,
    })


@app.route("/api/session/hint", methods=["POST"])
def session_hint():
    """Get the next hint step for the current question."""
    body = request.get_json(force=True)
    session_id = body.get("session_id")
    if not session_id or session_id not in sessions:
        return jsonify({"error": "Invalid session."}), 400

    session = sessions[session_id]
    qid = str(session["current_question"]["id"])
    # Reset hint state if question changed (stale from previous question)
    current_hint = session.get("hint_state", {})
    if not current_hint or current_hint.get("question_id") != qid:
        subqs = _get_subquestions(qid)
        session["hint_state"] = {
            "subqIdx": 0, "hintCount": 0, "totalSubqs": len(subqs) or 1,
            "question_id": qid
        }
    
    return jsonify(_handle_hint(session).get_json())


@app.route("/stream_chat", methods=["POST"])
def stream_chat():
    """Stream AI response via Server-Sent Events."""
    body = request.get_json(force=True)
    session_id = body.get("session_id")
    user_input = body.get("message", "").strip()

    if not session_id or session_id not in sessions:
        return jsonify({"error": "Invalid session."}), 400
    if not user_input or not deepseek_client:
        return jsonify({"error": "No AI available."}), 400

    session = sessions[session_id]
    session["messages"].append({"role": "user", "content": user_input})

    # Build messages for streaming (conversational mode only)
    eval_messages = session["messages"].copy()
    eval_messages[-1] = {"role": "user", "content": user_input}

    def generate():
        full_reply = ""
        try:
            response = deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=eval_messages,
                temperature=0.2,
                max_tokens=500,
                stream=True,
            )
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_reply += token
                    # SSE format: "data: <payload>\n\n"
                    yield f"data: {json.dumps({'token': token})}\n\n"
            
            # Send completion event with full reply
            yield f"data: {json.dumps({'done': True, 'full_reply': full_reply})}\n\n"
            session["messages"].append({"role": "assistant", "content": full_reply})
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@app.route("/health")
def health():
    """Health check."""
    return jsonify({
        "status": "ok",
        "questions_loaded": len(exam_data) if exam_data else 0,
        "deepseek_ready": deepseek_client is not None,
        "sessions": len(sessions),
    })


# ── Main ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Panhellenic AI Tutor Backend")
    parser.add_argument("--port", type=int, default=5050, help="Server port")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()

    load_data()
    init_deepseek()

    print(f"  Server: http://localhost:{args.port}")
    print(f"  DeepSeek: {'✓' if deepseek_client else '✗ (set DEEPSEEK_API_KEY)'}")
    print(f"  Questions: {len(exam_data)}")
    print(f"  Topics: {len(ranked)}")
    print()

    app.run(host="0.0.0.0", port=args.port, debug=args.debug)