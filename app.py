#!/usr/bin/env python3
"""
Panhellenic AI Tutor — Flask Backend
Multi-subject support: mathematics_prosanatolismoy, informatics, fysiki_prosanatolismoy
"""
import json, os, sys, re, uuid, hashlib, time, logging
from datetime import datetime, timezone
from collections import OrderedDict

from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context

# ── Structured logging
import logging as _logging
_logging.basicConfig(
    level=_logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logger = _logging.getLogger(__name__)
handler = _logging.StreamHandler()
handler.setFormatter(_logging.Formatter('{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}', datefmt='%Y-%m-%dT%H:%M:%S'))
logger.handlers = [handler]
logger.setLevel(_logging.INFO)

# ── Session cleanup
SESSION_TIMEOUT = 30 * 60
LAST_CLEANUP = time.time()

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    logger.warning("openai package not installed")

from predictor import calculate_topic_priorities, CURRENT_YEAR
from prompt_loader import load_prompts as _load_subject_prompts

# ── Fallback defaults (informatics) ─────────────────────────────────────────
_default_prompts = _load_subject_prompts("informatics")
build_trend_context = _default_prompts.build_trend_context
PREDICTION_SYSTEM_PROMPT = _default_prompts.PREDICTION_SYSTEM_PROMPT

# ── Per-session prompt resolution ──────────────────────────────────────────
_subject_prompts_cache = {}
def get_prompts(subject_id):
    """Get resolved prompts for a subject (cached)."""
    if subject_id not in _subject_prompts_cache:
        _subject_prompts_cache[subject_id] = _load_subject_prompts(subject_id)
    return _subject_prompts_cache[subject_id]

# ── Answer detection keywords ──────────────────────────────────────────────
MATH_ANSWER_KW = ['lim', 'int', 'frac', 'sqrt', 'sum', 'prod', 'infty',
                 'alpha', 'beta', 'gamma', 'delta', 'theta', 'lambda',
                 'derive', 'παράγωγ', 'ολοκλήρω', 'όριο', 'συνεχ',
                 'μονοτον', 'ακρότατ', 'εμβαδ', 'εξίσωση', 'συνάρτηση',
                 'απόδειξ', 'θεώρη', 'πίνακα', 'πίνακ', 'σύνολο',
                 'πραγματικ', 'φθίνουσα', 'αύξουσα', 'bolzano', 'rolle',
                 'πρόσημο', 'κυρτ', 'καμπ', 'ασύμπτωτ', 'τύπο']
CODE_ANSWER_KW = ['←','<-','τότε','επανάλαβε','διάβασε','γράψε','εμφάνισε',
                  'mod','div','τέλος_επανάληψης','τέλος_αν','μέχρις_ότου',
                  'περίπτωση','επίλεξε','αρχή_επανάληψης']
PHYSICS_ANSWER_KW = ['δύναμη','ταχύτητα','επιτάχυνση','ενέργεια','ορμή',
                     'κρούση','κύμα','ηλεκτρικό','μαγνητικό','πεδίο',
                     'νεύτων','ελατήριο','συχνότητα','περίοδο',
                     'φ','Φ','θερμότητα','ροπή','ισορροπία','τάση']

from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "subjects", "informatics")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions_classified.json")
QUESTIONS_V2_FILE = os.path.join(DATA_DIR, "questions_v2.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")

exam_data, ranked, details, trend_context = None, None, None, None
deepseek_client = None
sessions = {}
_response_cache = {}
MAX_CACHE_SIZE = 200

# ── LRU cache for v2 data (max 5 subjects) ─────────────────────────────────
MAX_V2_CACHE_SIZE = 5
_v2_cache = OrderedDict()

def cleanup_sessions():
    global LAST_CLEANUP
    now = time.time()
    if now - LAST_CLEANUP < 300: return
    LAST_CLEANUP = now
    expired = []
    for sid, sess in sessions.items():
        started = sess.get("started_at")
        if started:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(started)).total_seconds()
                if age > SESSION_TIMEOUT: expired.append(sid)
            except: pass
    for sid in expired: del sessions[sid]
    if expired: logger.info(f"Cleaned {len(expired)} expired sessions")

@app.before_request
def before_request():
    cleanup_sessions()

class AIError(Exception): pass
class APIError(AIError): pass
class ValidationError(AIError): pass

def load_data():
    global exam_data, ranked, details, trend_context
    if not os.path.exists(QUESTIONS_FILE):
        logger.error(f"Questions file not found: {QUESTIONS_FILE}")
        exam_data, ranked = [], []
        return
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        exam_data = json.load(f)
    ranked_priorities, details = calculate_topic_priorities(exam_data)
    ranked = [(t, s) for t, s in ranked_priorities if t not in ("ΠΛΗΡΟΦΟΡΙΚΗ:", "ΑΕΠΠ:", "")]
    trend_context = build_trend_context(ranked, details, top_n=5)
    logger.info(f"Loaded {len(exam_data)} questions, {len(ranked)} topics")

def init_deepseek():
    global deepseek_client
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY not set")
        return
    if not HAS_OPENAI:
        logger.warning("openai package not installed")
        return
    deepseek_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    logger.info("DeepSeek client ready")

def format_exam_question(question, tag=None, subject_id="informatics"):
    result = {
        "id": question["id"], "part": question["part"], "year": question["year"],
        "points": question["points"], "focus_tag": tag,
        "type": question.get("type", "open_ended_problem"),
        "question_text": question["question_text"],
        "tags": question.get("conceptual_tags", [])[:6],
    }
    v2_data = _load_v2_data(subject_id)
    if str(question["id"]) in v2_data:
        result["question_html"] = v2_data[str(question["id"])].get("question_html", "")
        result["answer_html"] = v2_data[str(question["id"])].get("answer_html", "")
        result["sub_questions"] = [
            {"number": s["number"], "content": s.get("content", "")}
            for s in v2_data[str(question["id"])].get("sections", [])
            if s["type"] == "sub_question"
        ]
    else:
        result["sub_questions"] = []
    dm = _load_diagram_map(subject_id)
    if str(question["id"]) in dm:
        result["diagram_urls"] = [{"path": d["path"].replace("static/", "", 1), "width": d.get("width"), "height": d.get("height"), "page": d.get("page", 1)} for d in dm[str(question["id"])].get("diagrams", [])]
    else:
        result["diagram_urls"] = []
    return result

def _load_v2_data(subject_id="informatics"):
    """Load v2 question data with LRU cache (max 5 subjects)."""
    if subject_id in _v2_cache:
        # Move to end (most recently used)
        _v2_cache.move_to_end(subject_id)
        return _v2_cache[subject_id]
    
    subject_cfg = load_subject_config(subject_id)
    data_dir = os.path.join(BASE_DIR, subject_cfg.get("data", {}).get("data_dir", "data/subjects/informatics"))
    v2_file = os.path.join(data_dir, "questions_v2.json")
    result = {}
    if os.path.exists(v2_file):
        with open(v2_file, encoding="utf-8") as f:
            result = {str(q["id"]): q for q in json.load(f)}
    
    # LRU eviction
    if len(_v2_cache) >= MAX_V2_CACHE_SIZE:
        _v2_cache.popitem(last=False)  # Remove oldest
        
    _v2_cache[subject_id] = result
    return result

_diagram_map_cache = {}
def _load_diagram_map(subject_id="informatics"):
    """Load diagram map per subject (separate files)."""
    if subject_id in _diagram_map_cache:
        return _diagram_map_cache[subject_id]
    
    # Try per-subject file first, fall back to shared
    subject_cfg = load_subject_config(subject_id)
    data_dir = os.path.join(BASE_DIR, subject_cfg.get("data", {}).get("data_dir", "data/subjects/informatics"))
    mf = os.path.join(data_dir, "diagram_map.json")
    if not os.path.exists(mf):
        # Fallback: shared diagram map
        mf = os.path.join(STATIC_DIR, "images", "exams", "diagram_map.json")
    
    if os.path.exists(mf):
        with open(mf, encoding="utf-8") as f:
            _diagram_map_cache[subject_id] = json.load(f)
    else:
        _diagram_map_cache[subject_id] = {}
    return _diagram_map_cache[subject_id]

def strip_reasoning(text):
    if not text: return text
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return text.replace('\r\n', '\n').replace('\r', '\n').replace('\t', '    ').strip()

def _cache_key(session):
    msgs = session.get("messages", [])
    if len(msgs) < 2: return None
    s = msgs[0].get("content", "")
    u = next((m["content"] for m in reversed(msgs) if m.get("role") == "user"), "")
    return hashlib.md5((s + "|||" + u).encode()).hexdigest()

HELPFUL_ERRORS = {
    "timeout": "Ο διακομιστής άργησε να απαντήσει. Δοκίμασε ξανά σε λίγο.",
    "rate_limit": "Πολλοί χρήστες αυτή τη στιγμή! Δοκίμασε ξανά σε λίγα δευτερόλεπτα.",
    "api_error": "Κάτι πήγε στραβά με το AI. Δοκίμασε ξανά ή χρησιμοποίησε το Hint.",
    "network": "Δεν μπορούμε να συνδεθούμε. Έλεγξε τη σύνδεσή σου και δοκίμασε ξανά.",
    "default": "Κάτι δεν πήγε καλά. Δοκίμασε ξανά ή πήγαινε στο επόμενο θέμα.",
}

def classify_error(e):
    msg = str(e).lower()
    if "timeout" in msg: return "timeout"
    if "429" in msg or "rate" in msg: return "rate_limit"
    if any(w in msg for w in ("key", "auth", "invalid")): return "api_error"
    if any(w in msg for w in ("refused", "unreachable", "resolve")): return "network"
    return "default"

def call_deepseek_with_retry(fn, *args, max_retries=1, **kwargs):
    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            category = classify_error(e)
            if attempt < max_retries and category in ("timeout", "rate_limit", "network"):
                logger.warning(f"Retry {attempt+1}/{max_retries} for {category}")
                time.sleep(2 ** attempt)
                continue
            raise APIError(HELPFUL_ERRORS.get(category, HELPFUL_ERRORS["default"]))

def _is_student_answer(msg, subject_id):
    """Detect if the message is a student answer submission.
    Driven by subject config `answer_detection`: 'math' | 'code' | 'physics' | 'none'.
    """
    if '?' in msg or ';' in msg:
        return False
    if any(qw in msg.lower() for qw in ['πώς', 'πως', 'τι ', 'γιατί', 'γιατι', 'πότε', 'ποτε', 'μπορείς', 'μπορεις', 'βοήθα', 'βοηθα', 'δεν ξέρω', 'δεν ξερω', 'δεν καταλαβαίν', 'δεν καταλαβαιν', 'εξήγησ', 'εξηγησ']):
        return False
    if len(msg) > 100 and '\n' in msg:
        return True
    cfg = load_subject_config(subject_id)
    mode = cfg.get("answer_detection", "code")
    if mode == "math":
        if any(k in msg.lower() for k in MATH_ANSWER_KW):
            return True
        stripped = msg.strip().replace(' ', '')
        if len(stripped) <= 50 and re.search(r'[\+\-\*/^=√∫∑∏]|\\frac|\\lim|\\int|\\sum|\\\\sqrt|[0-9]+[xXyYzZ]|[xXyYzZ]\^|[xXyYzZ]\d', stripped):
            return True
        return False
    elif mode == "code":
        return any(k in msg.lower() for k in CODE_ANSWER_KW)
    elif mode == "physics":
        return any(k in msg.lower() for k in PHYSICS_ANSWER_KW)
    else:
        return False

# ── Routes
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")

import json as _json
def load_subject_config(subject_id="informatics"):
    cfg_path = os.path.join(BASE_DIR, "subjects", f"{subject_id}.json")
    if not os.path.exists(cfg_path):
        cfg_path = os.path.join(BASE_DIR, "subjects", "informatics.json")
    with open(cfg_path, encoding="utf-8") as f:
        return _json.load(f)

@app.route("/api/session/start", methods=["POST"])
def start_session():
    sid = str(uuid.uuid4())
    cleanup_sessions()
    body = request.get_json(force=True) or {}
    subject_id = body.get("subject", "informatics")
    subject_cfg = load_subject_config(subject_id)
    parts = subject_cfg.get("parts", ["Θέμα 2"])
    data_dir = os.path.join(BASE_DIR, subject_cfg.get("data", {}).get("data_dir", "data/subjects/informatics"))
    qfile = os.path.join(data_dir, subject_cfg.get("data", {}).get("source_file", "questions_classified.json"))
    if os.path.exists(qfile):
        with open(qfile, encoding="utf-8") as f:
            global exam_data, ranked, details, trend_context
            exam_data = _json.load(f)
            ranked_priorities, details = calculate_topic_priorities(exam_data)
            ranked = [(t, s) for t, s in ranked_priorities if t not in ("ΠΛΗΡΟΦΟΡΙΚΗ:", "ΑΕΠΠ:", "", "ΜΑΘΗΜΑΤΙΚΑ:", "ΑΛΓΕΒΡΑ:")]
            trend_context = build_trend_context(ranked, details, top_n=5)
    if not exam_data:
        return jsonify({"error": "Δεν φορτώθηκαν τα δεδομένα. Δοκίμασε αργότερα."}), 500
    filter_topic = body.get("topic", "").strip()
    question, tag = None, None
    for tg, _ in ranked[:15]:
        for q in exam_data:
            if q["part"] in parts and tg in q.get("conceptual_tags", []):
                if filter_topic and filter_topic not in tg and filter_topic not in str(q.get("conceptual_tags", [])):
                    continue
                question, tag = q, tg; break
        if question: break
    if not question:
        import random
        candidates = [q for q in exam_data if q["part"] in parts]
        question = random.choice(candidates) if candidates else None
        tag = None
    if not question:
        return jsonify({"error": "Δεν βρέθηκαν ερωτήσεις."}), 500
    prompts = get_prompts(subject_id)
    tutor_prompt = prompts.GREEK_TUTOR_SYSTEM_PROMPT
    eval_prompt = prompts.EVALUATION_SYSTEM_PROMPT
    q_v2 = _load_v2_data(subject_id).get(str(question['id']), {})
    q_html = q_v2.get("question_html", question.get("question_text", ""))
    q_text = re.sub(r'<[^>]+>', ' ', q_html)[:3000].strip()
    q_text = re.sub(r'\s+', ' ', q_text)

    sp = (tutor_prompt + "\n\n" +
          "📋 ΤΡΕΧΟΥΣΑ ΑΣΚΗΣΗ:\n" +
          q_text + "\n\n" +
          f"Θέμα: {question['part']} — {question.get('points',0)} μονάδες, Έτος: {question.get('year','')}\n" +
          f"Έννοιες: {', '.join(question.get('conceptual_tags', [])[:5])}\n" +
          trend_context)
    sessions[sid] = {
        "messages": [{"role": "system", "content": sp}],
        "seen_ids": {question["id"]},
        "current_question": question, "current_tag": tag,
        "completed_count": 0, "total_points": 0,
        "started_at": datetime.now(timezone.utc).isoformat(), "history": [],
        "subject_id": subject_id,
        "eval_prompt": eval_prompt,
    }
    logger.info(f"Session started: {sid[:8]} [{subject_id}]")
    return jsonify({"session_id": sid, "question": format_exam_question(question, tag, subject_id),
                    "has_ai": deepseek_client is not None, "subject": subject_cfg,
                    "total_questions": len(exam_data)})

@app.route("/api/chat", methods=["POST"])
def chat():
    body = request.get_json(force=True) or {}
    sid = body.get("session_id", "")
    msg = body.get("message", "").strip()
    if not sid or sid not in sessions:
        return jsonify({"error": "Η συνεδρία έληξε. Ξεκίνα μια νέα."}), 400
    if not msg:
        return jsonify({"reply": None})
    sess = sessions[sid]
    subj_id = sess.get("subject_id", "informatics")
    sess["messages"].append({"role": "user", "content": msg})
    cmd = msg.lower()
    if cmd in {"exit", "quit", "έξοδος"}:
        return jsonify({"reply": "Η συνεδρία τερματίστηκε. Καλή επιτυχία! 🎓", "end_session": True})
    if cmd in {"λύση", "λυση", "solution", "απάντηση", "απαντηση"}:
        v2 = _load_v2_data(subj_id).get(str(sess["current_question"]["id"]), {})
        return jsonify({"is_solution": True, "answer_html": v2.get("llm_solution_html") or v2.get("answer_html") or sess["current_question"].get("answer_text", "")})
    if cmd in {"next", "επόμενο", "επομενο", "skip"}:
        return jsonify({"reply": None, "next_question": True})
    if cmd in {"hint", "βοήθεια", "βοηθεια", "help"}:
        return _handle_hint(sess)
    if not deepseek_client:
        return jsonify({"reply": "Το AI είναι προσωρινά μη διαθέσιμο. Χρησιμοποίησε το Hint ή πήγαινε στο επόμενο θέμα.", "no_ai": True})

    is_answer = _is_student_answer(msg, subj_id)

    subq_ctx = ""
    active_subq = body.get("active_subq", {})
    if active_subq and active_subq.get("number"):
        subq_ctx = f"\n\n[Ενεργό υποερώτημα: {active_subq.get('number')}. {active_subq.get('content', '')}]"

    hint_ctx = ""
    hs = sess.get("hint_state", {})
    if hs and hs.get("question_id") == str(sess["current_question"]["id"]):
        hc = hs.get("hintCount", 0)
        if hc > 0:
            sqs = _get_subquestions(str(sess["current_question"]["id"]), subj_id)
            subq_num = sqs[hs.get("subqIdx", 0)]["number"] if hs.get("subqIdx", 0) < len(sqs) else "?"
            hint_ctx = f"\n\n[O μαθητής μόλις είδε το hint #{hc} για το υποερώτημα {subq_num}. Αξιοποίησε το στην απάντησή σου.]"

    if not is_answer:
        try:
            ms = sess["messages"].copy()
            fact_check = ""
            cfg = load_subject_config(subj_id)
            if cfg.get("answer_detection") == "math" and _is_student_answer(msg, subj_id):
                qhtml = _load_v2_data(subj_id).get(str(sess["current_question"]["id"]), {}).get("answer_html", "")
                if qhtml:
                    plain_ans = re.sub(r'<[^>]+>', ' ', qhtml)[:500].strip()
                    fact_check = f"\n\n[ΠΡΟΣΟΧΗ: Ο μαθητής έγραψε μια μαθηματική απάντηση. Αν είναι ΛΑΘΟΣ, οδήγησέ τον στη σωστή κατεύθυνση. Μην πεις 'Σωστά!' αν δεν είναι. Σχετική λύση: {plain_ans}]"
            ms[-1] = {"role": "user", "content": msg + subq_ctx + hint_ctx + fact_check}
            resp = call_deepseek_with_retry(deepseek_client.chat.completions.create,
                                            model="deepseek-chat", messages=ms, temperature=0.4, max_tokens=500)
            reply = strip_reasoning(resp.choices[0].message.content or "Συγνώμη, κάτι πήγε στραβά.")
            sess["messages"].append({"role": "assistant", "content": reply})
            return jsonify({"reply": reply, "conversational": True})
        except APIError as e:
            return jsonify({"reply": str(e), "error": True})
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return jsonify({"reply": "Κάτι πήγε στραβά. Δοκίμασε ξανά σε λίγο.", "error": True})

    key = _cache_key(sess)
    if key and key in _response_cache:
        logger.info(f"Cache hit {sid[:8]}")
        return jsonify({"evaluation": _response_cache[key], "cached": True})
    try:
        q = sess["current_question"]
        eval_prompt = sess.get("eval_prompt",
            get_prompts(subj_id).EVALUATION_SYSTEM_PROMPT)
        em = [{"role": "system", "content": eval_prompt},
              {"role": "user", "content": f"Ερώτηση: {q.get('question_text','')[:2000]}\n\nΑπάντηση μαθητή: {msg}{subq_ctx}{hint_ctx}"}]
        resp = call_deepseek_with_retry(deepseek_client.chat.completions.create,
                                        model="deepseek-chat", messages=em, temperature=0.1, max_tokens=600,
                                        response_format={"type": "json_object"})
        raw = strip_reasoning(resp.choices[0].message.content or "{}")
        try: ev = json.loads(raw)
        except:
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            ev = json.loads(m.group(0)) if m else {"status": "info", "critique": raw[:300], "hint": "Δοκίμασε ξανά."}
        if key:
            if len(_response_cache) >= MAX_CACHE_SIZE: del _response_cache[next(iter(_response_cache))]
            _response_cache[key] = ev
        sess["messages"].append({"role": "assistant", "content": json.dumps(ev, ensure_ascii=False)})
        return jsonify({"evaluation": ev, "cached": False})
    except APIError as e:
        return jsonify({"evaluation": {"status": "info", "critique": str(e), "hint": "Δοκίμασε ξανά."}})
    except Exception as e:
        logger.error(f"Eval error: {e}")
        return jsonify({"evaluation": {"status": "info", "critique": "Σφάλμα αξιολόγησης.", "hint": "Δοκίμασε ξανά."}})

@app.route("/api/session/next", methods=["POST"])
def next_question():
    body = request.get_json(force=True) or {}
    sid = body.get("session_id", "")
    if sid not in sessions:
        return jsonify({"error": "Ξεκίνα νέα συνεδρία."}), 400
    s = sessions[sid]
    s.setdefault("history", []).append({
        "question": format_exam_question(s["current_question"], subject_id=s.get("subject_id", "informatics")),
        "messages": list(s["messages"])
    })
    s["completed_count"] += 1
    s["total_points"] += s["current_question"]["points"]
    import random
    subj_id = s.get("subject_id", "informatics")
    subject_cfg = load_subject_config(subj_id)
    parts = subject_cfg.get("parts", ["Θέμα 2", "Θέμα 4"])
    candidates = [x for x in exam_data if x["part"] in parts and x["id"] not in s["seen_ids"]]
    q = random.choice(candidates) if candidates else None
    if not q:
        return jsonify({"reply": "Δεν υπάρχουν άλλα θέματα! 🎓", "session_complete": True})
    s["seen_ids"].add(q["id"])
    s["current_question"] = q
    prompts = get_prompts(subj_id)
    tutor = prompts.GREEK_TUTOR_SYSTEM_PROMPT
    eval_prompt = prompts.EVALUATION_SYSTEM_PROMPT
    s["eval_prompt"] = eval_prompt
    q_v2 = _load_v2_data(subj_id).get(str(q['id']), {})
    q_html = q_v2.get("question_html", q.get("question_text", ""))
    q_text = re.sub(r'<[^>]+>', ' ', q_html)[:3000].strip()
    q_text = re.sub(r'\s+', ' ', q_text)

    s["messages"] = [{"role": "system", "content": (
        tutor + "\n\n" +
        "📋 ΤΡΕΧΟΥΣΑ ΑΣΚΗΣΗ:\n" +
        q_text + "\n\n" +
        f"Θέμα: {q['part']} — {q.get('points', 0)} μονάδες, Έτος: {q.get('year', '')}\n" +
        f"Έννοιες: {', '.join(q.get('conceptual_tags', [])[:5])}\n" +
        trend_context
    )}]
    s["hint_state"] = {"subqIdx": 0, "hintCount": 0, "totalSubqs": len(_get_subquestions(str(q["id"]), subj_id)) or 1}
    return jsonify({
        "question": format_exam_question(q, subject_id=subj_id),
        "stats": {"completed": s["completed_count"], "total_points": s["total_points"],
                  "remaining": len(exam_data) - len(s["seen_ids"])}
    })

@app.route("/api/session/previous", methods=["POST"])
def previous():
    body = request.get_json(force=True) or {}
    sid = body.get("session_id", "")
    if sid not in sessions: return jsonify({"error": "Έληξε."}), 400
    s = sessions[sid]; h = s.get("history", [])
    if not h: return jsonify({"error": "Δεν υπάρχει προηγούμενο."}), 400
    p = h.pop()
    pq = next((x for x in exam_data if x["id"] == p["question"]["id"]), None)
    if not pq: return jsonify({"error": "Δεν βρέθηκε."}), 500
    s["current_question"] = pq; s["messages"] = p["messages"]
    s["completed_count"] = max(0, s["completed_count"] - 1)
    s["total_points"] = max(0, s["total_points"] - pq.get("points", 0))
    return jsonify({
        "question": format_exam_question(pq, subject_id=s.get("subject_id", "informatics")),
        "stats": {"completed": s["completed_count"], "total_points": s["total_points"],
                  "remaining": len(exam_data) - len(s["seen_ids"])},
        "has_previous": len(h) > 0
    })

@app.route("/api/session/stats", methods=["POST"])
def stats():
    body = request.get_json(force=True) or {}
    sid = body.get("session_id", "")
    if sid not in sessions: return jsonify({"error": "Έληξε."}), 400
    s = sessions[sid]
    return jsonify({"completed": s["completed_count"], "total_points": s["total_points"],
                    "remaining": len(exam_data) - len(s["seen_ids"])})

@app.route("/api/topics")
def topics():
    return jsonify({"topics": [{"topic": t, "priority": round(s, 2)} for t, s in ranked[:10]],
                    "total_topics": len(ranked)})

@app.route("/api/questions/list")
def questions_list():
    """Return all question IDs with metadata for autocomplete."""
    subject_id = request.args.get("subject", "informatics")
    cfg = load_subject_config(subject_id)
    ddir = cfg.get("data", {}).get("data_dir", "data/subjects/informatics")
    src = cfg.get("data", {}).get("source_file", "questions_classified.json")
    qf = os.path.join(BASE_DIR, ddir, src)
    if not os.path.exists(qf):
        return jsonify({"ids": []})
    with open(qf, encoding="utf-8") as f:
        qs = json.load(f)
    return jsonify({"ids": [{"id": q["id"], "year": q.get("year",""), "part": q.get("part",""), "points": q.get("points",0), "tags": q.get("conceptual_tags", [])[:2]} for q in qs]})

@app.route("/api/session/jump", methods=["POST"])
def jump_question():
    """Jump to a specific question by ID."""
    body = request.get_json(force=True) or {}
    sid = body.get("session_id", "")
    tid = body.get("question_id")
    if not sid or sid not in sessions:
        return jsonify({"error": "Session ended"}), 400
    if not tid:
        return jsonify({"error": "No ID"}), 400
    s = sessions[sid]
    sj = s.get("subject_id", "informatics")
    q = next((x for x in exam_data if x["id"] == tid), None)
    if not q:
        return jsonify({"error": "ID not found"}), 404
    s["seen_ids"].add(q["id"])
    s["current_question"] = q
    pr = get_prompts(sj)
    s["eval_prompt"] = pr.EVALUATION_SYSTEM_PROMPT
    qv = _load_v2_data(sj).get(str(q["id"]), {})
    qh = qv.get("question_html", q.get("question_text", ""))
    qt = re.sub(r'<[^>]+>', ' ', qh)[:3000].strip()
    qt = re.sub(r'\s+', ' ', qt)
    sp = pr.GREEK_TUTOR_SYSTEM_PROMPT + "\n\n" + qt + "\n\n" + trend_context
    s["messages"] = [{"role": "system", "content": sp}]
    s["hint_state"] = {"subqIdx": 0, "hintCount": 0, "totalSubqs": len(_get_subquestions(str(q["id"]), sj)) or 1}
    logger.info(f"Jump: {sid[:8]} -> Q{tid}")
    return jsonify({"question": format_exam_question(q, subject_id=sj)})

@app.route("/api/guidelines")
def guidelines():
    subject_id = request.args.get("subject", "mathematics_prosanatolismoy")
    cfg = load_subject_config(subject_id)
    data_dir = os.path.join(BASE_DIR, cfg.get("data", {}).get("data_dir", "data/subjects/mathematics_prosanatolismoy"))
    gfile = os.path.join(data_dir, "sos_guidelines.json")
    if not os.path.exists(gfile):
        gfile2 = os.path.join(BASE_DIR, "data", "subjects", subject_id, "sos_guidelines.json")
        if os.path.exists(gfile2):
            gfile = gfile2
    if not os.path.exists(gfile):
        return jsonify({"available": False, "message": "Δεν έχει δημιουργηθεί ακόμα ο οδηγός SOS για αυτό το μάθημα."})
    with open(gfile, encoding="utf-8") as f:
        data = json.load(f)
    return jsonify({"available": True, "guidelines": data})

@app.route("/health")
def health():
    return jsonify({"status": "ok", "questions_loaded": len(exam_data) if exam_data else 0,
                    "deepseek_ready": deepseek_client is not None, "sessions": len(sessions)})

# ── Hints ───────────────────────────────────────────────────────────────────
def _get_subquestions(qid, subject_id="informatics"):
    v2 = _load_v2_data(subject_id).get(str(qid), {})
    return [{"number": s["number"], "content": s.get("content", "")}
            for s in v2.get("sections", []) if s["type"] == "sub_question"]

def _filter_answer_for_subq(full_answer, subq_number, subq_content):
    if not deepseek_client or not full_answer: return full_answer
    clean_answer = re.sub(r'<[^>]+>', ' ', full_answer)[:3000]
    try:
        resp = call_deepseek_with_retry(deepseek_client.chat.completions.create,
            model="deepseek-chat",
            messages=[{"role": "system", "content": "Είσαι βοηθός. Επέστρεψε ΜΟΝΟ το τμήμα της απάντησης που αφορά το συγκεκριμένο υποερώτημα. Κράτα τη φυσική γλώσσα."},
                      {"role": "user", "content": f"Πλήρης: {clean_answer}\nΥποερώτημα: {subq_number}\nΕκφώνηση: {subq_content}\nΑπάντηση μόνο για {subq_number}:"}],
            temperature=0.1, max_tokens=500)
        filtered = strip_reasoning(resp.choices[0].message.content or "")
        if filtered and len(filtered) > 15: return filtered.replace('\n', '<br>')
    except: pass
    return full_answer

def _handle_hint(sess):
    qid = str(sess["current_question"]["id"])
    subj = sess.get("subject_id", "informatics")
    v2 = _load_v2_data(subj).get(qid, {})
    sqs = _get_subquestions(qid, subj) or [{"number": "?", "content": ""}]
    hs = sess.get("hint_state", {"subqIdx": 0, "hintCount": 0, "totalSubqs": len(sqs)})
    si, hc = hs.get("subqIdx", 0), hs.get("hintCount", 0)
    if si >= len(sqs):
        return jsonify({"all_done": True, "hint_state": hs, "reply": "✅ Ολοκλήρωσες όλα τα υποερωτήματα!"})
    sn = sqs[si]["number"]
    hints = v2.get("hints", [])
    ht = hints[si]["hints"][hc]["hint_text"] if si < len(hints) and hc < len(hints[si].get("hints", [])) else None
    if not ht:
        hs["subqIdx"] = si + 1; hs["hintCount"] = 0; sess["hint_state"] = hs
        fa = v2.get("answer_html", "")
        filtered = _filter_answer_for_subq(fa, sn, sqs[si].get("content", "")) if deepseek_client else fa
        return jsonify({"html": filtered or fa, "hint_state": hs, "is_full_answer": True,
                        "reply": f"📚 Υποερώτημα {sn} — Πλήρης λύση."})
    hc += 1; hs["hintCount"] = hc; sess["hint_state"] = hs
    if hc >= 4:
        hs["subqIdx"] = si + 1; hs["hintCount"] = 0; sess["hint_state"] = hs
        fa = v2.get("answer_html", "")
        filtered = _filter_answer_for_subq(fa, sn, sqs[si].get("content", "")) if deepseek_client else fa
        return jsonify({"html": filtered or fa, "hint_state": hs, "is_full_answer": True,
                        "reply": f"📚 Υποερώτημα {sn} — Πλήρης λύση."})
    return jsonify({"html": f'<div class="hint-box"><b>Υποερώτημα {sn}</b><br><br>{ht}</div>',
                    "hint_state": hs, "subq_num": sn, "level": hc})

@app.route("/api/session/hint", methods=["POST"])
def hint_route():
    body = request.get_json(force=True) or {}
    sid = body.get("session_id", "")
    if sid not in sessions: return jsonify({"error": "Έληξε."}), 400
    sess = sessions[sid]
    ch = body.get("hint_state", {})
    sh = sess.get("hint_state", {})
    if ch:
        sh["subqIdx"] = ch.get("subqIdx", sh.get("subqIdx", 0))
        sh["hintCount"] = ch.get("hintCount", sh.get("hintCount", 0))
    qid = str(sess["current_question"]["id"])
    if sh.get("question_id") != qid:
        sh = {"subqIdx": 0, "hintCount": 0,
              "totalSubqs": len(_get_subquestions(qid)) or 1,
              "question_id": qid}
    sess["hint_state"] = sh
    return jsonify(_handle_hint(sess).get_json())

@app.route("/stream_chat", methods=["POST"])
def stream():
    body = request.get_json(force=True) or {}
    sid, msg = body.get("session_id", ""), body.get("message", "").strip()
    if sid not in sessions: return jsonify({"error": "Έληξε."}), 400
    sess = sessions[sid]; sess["messages"].append({"role": "user", "content": msg})
    def gen():
        full = ""
        try:
            for c in deepseek_client.chat.completions.create(
                    model="deepseek-chat", messages=sess["messages"].copy(),
                    temperature=0.2, max_tokens=500, stream=True):
                if c.choices and c.choices[0].delta.content:
                    t = c.choices[0].delta.content; full += t
                    yield f"data: {json.dumps({'token': t})}\n\n"
            yield f"data: {json.dumps({'done': True, 'full_reply': full})}\n\n"
            sess["messages"].append({"role": "assistant", "content": full})
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── Startup
load_data()
init_deepseek()
logger.info(f"App ready — {len(exam_data)} questions")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=5050)
    p.add_argument("--debug", action="store_true")
    a = p.parse_args()
    app.run(host="0.0.0.0", port=a.port, debug=a.debug)