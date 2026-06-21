#!/usr/bin/env python3
"""
Panhellenic AI Tutor — Flask Backend
"""
import json, os, sys, re, uuid, hashlib, time, logging
from datetime import datetime, timezone

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
SESSION_TIMEOUT = 30 * 60  # 30 minutes
LAST_CLEANUP = time.time()

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    logger.warning("openai package not installed")

from predictor import calculate_topic_priorities, CURRENT_YEAR
from prompt_loader import load_prompts as _load_subject_prompts
_prompts = _load_subject_prompts("informatics")
GREEK_TUTOR_SYSTEM_PROMPT = _prompts.GREEK_TUTOR_SYSTEM_PROMPT
EVALUATION_SYSTEM_PROMPT = _prompts.EVALUATION_SYSTEM_PROMPT
PREDICTION_SYSTEM_PROMPT = _prompts.PREDICTION_SYSTEM_PROMPT
CORRECT_ANSWER_PROMPT = _prompts.CORRECT_ANSWER_PROMPT
PARTIAL_ANSWER_PROMPT = _prompts.PARTIAL_ANSWER_PROMPT
INCORRECT_ANSWER_PROMPT = _prompts.INCORRECT_ANSWER_PROMPT
COMMON_PANHELLENIC_TRAPS = _prompts.COMMON_PANHELLENIC_TRAPS
build_trend_context = _prompts.build_trend_context

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

def cleanup_sessions():
    """Remove stale sessions older than SESSION_TIMEOUT."""
    global LAST_CLEANUP
    now = time.time()
    if now - LAST_CLEANUP < 300:
        return
    LAST_CLEANUP = now
    expired = []
    for sid, sess in sessions.items():
        started = sess.get("started_at")
        if started:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(started)).total_seconds()
                if age > SESSION_TIMEOUT:
                    expired.append(sid)
            except: pass
    for sid in expired:
        del sessions[sid]
    if expired:
        logger.info(f"Cleaned {len(expired)} expired sessions")

@app.before_request
def before_request():
    cleanup_sessions()

class AIError(Exception):
    pass

class APIError(AIError):
    pass

class ValidationError(AIError):
    pass

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
    dm = _load_diagram_map()
    if str(question["id"]) in dm:
        result["diagram_urls"] = [{"path": d["path"].replace("static/", "", 1), "width": d.get("width"), "height": d.get("height"), "page": d.get("page", 1)} for d in dm[str(question["id"])].get("diagrams", [])]
    else:
        result["diagram_urls"] = []
    return result

_v2_cache = {}
def _load_v2_data(subject_id="informatics"):
    if subject_id in _v2_cache and _v2_cache[subject_id]:
        return _v2_cache[subject_id]
    subject_cfg = load_subject_config(subject_id)
    data_dir = os.path.join(BASE_DIR, subject_cfg.get("data", {}).get("data_dir", "data/subjects/informatics"))
    v2_file = os.path.join(data_dir, "questions_v2.json")
    result = {}
    if os.path.exists(v2_file):
        with open(v2_file, encoding="utf-8") as f:
            result = {str(q["id"]): q for q in json.load(f)}
    _v2_cache[subject_id] = result
    return result

_diagram_map_cache = None
def _load_diagram_map():
    global _diagram_map_cache
    if _diagram_map_cache is not None: return _diagram_map_cache
    mf = os.path.join(STATIC_DIR, "images", "exams", "diagram_map.json")
    if os.path.exists(mf):
        with open(mf, encoding="utf-8") as f: _diagram_map_cache = json.load(f)
    else: _diagram_map_cache = {}
    return _diagram_map_cache

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

# ── Routes
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")

# ── Subject config loader ──────────────────────────────────────────────────
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
    data_dir = os.path.join(BASE_DIR, subject_cfg.get("data", {}).get("data_dir", "data/trapeza_data_1_3_218"))
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
    question, tag = None, None
    for tg, _ in ranked[:15]:
        for q in exam_data:
            if q["part"] in parts and tg in q.get("conceptual_tags", []):
                question, tag = q, tg; break
        if question: break
    if not question:
        import random
        candidates = [q for q in exam_data if q["part"] in parts]
        question = random.choice(candidates) if candidates else None
        tag = None
    if not question:
        return jsonify({"error": "Δεν βρέθηκαν ερωτήσεις."}), 500
    try:
        subj_prompts = _load_subject_prompts(subject_id)
        tutor_prompt = subj_prompts.GREEK_TUTOR_SYSTEM_PROMPT
        eval_prompt = subj_prompts.EVALUATION_SYSTEM_PROMPT
    except:
        tutor_prompt = GREEK_TUTOR_SYSTEM_PROMPT
        eval_prompt = EVALUATION_SYSTEM_PROMPT
    sp = (tutor_prompt + "\n" +
          f"Θέμα: {question['part']} — {question.get('points',0)} μονάδες\n" +
          f"Έτος: {question.get('year','')}\n" +
          trend_context)
    sessions[sid] = {
        "messages": [{"role": "system", "content": sp}], "seen_ids": {question["id"]},
        "current_question": question, "current_tag": tag,
        "completed_count": 0, "total_points": 0,
        "started_at": datetime.now(timezone.utc).isoformat(), "history": [],
        "subject_id": subject_id,
    }
    logger.info(f"Session started: {sid[:8]} [{subject_id}]")
    return jsonify({"session_id": sid, "question": format_exam_question(question, tag, subject_id),
                    "has_ai": deepseek_client is not None, "subject": subject_cfg})
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
    sess["messages"].append({"role": "user", "content": msg})
    cmd = msg.lower()
    if cmd in {"exit", "quit", "έξοδος"}:
        return jsonify({"reply": "Η συνεδρία τερματίστηκε. Καλή επιτυχία! 🎓", "end_session": True})
    if cmd in {"λύση", "λυση", "solution", "απάντηση", "απαντηση"}:
        v2 = _load_v2_data(sess.get("subject_id", "informatics")).get(str(sess["current_question"]["id"]), {})
        return jsonify({"is_solution": True, "answer_html": v2.get("llm_solution_html") or v2.get("answer_html") or sess["current_question"].get("answer_text", "")})
    if cmd in {"next", "επόμενο", "επομενο", "skip"}:
        return jsonify({"reply": None, "next_question": True})
    if cmd in {"hint", "βοήθεια", "βοηθεια", "help"}:
        return _handle_hint(sess)
    if not deepseek_client:
        return jsonify({"reply": "Το AI είναι προσωρινά μη διαθέσιμο. Χρησιμοποίησε το Hint ή πήγαινε στο επόμενο θέμα.", "no_ai": True})

    code_kw = ['←','<-','τότε','επανάλαβε','διάβασε','γράψε','εμφάνισε','mod','div','τέλος_επανάληψης','τέλος_αν','μέχρις_ότου','περίπτωση','επίλεξε','αρχή_επανάληψης']
    is_answer = any(k in msg.lower() for k in code_kw) or (len(msg) > 150 and '\n' in msg)

    if not is_answer:
        try:
            # Inject active sub-question context into chat prompt
            subq_ctx = ""
            active_subq = body.get("active_subq", {})
            if active_subq and active_subq.get("number"):
                subq_ctx = f"\n\n[Ενεργό υποερώτημα: {active_subq.get('number')}. {active_subq.get('content', '')}]"
            ms = sess["messages"].copy(); ms[-1] = {"role":"user","content":msg + subq_ctx}
            resp = call_deepseek_with_retry(deepseek_client.chat.completions.create,
                                            model="deepseek-chat", messages=ms, temperature=0.4, max_tokens=500)
            reply = strip_reasoning(resp.choices[0].message.content or "Συγνώμη, κάτι πήγε στραβά.")
            sess["messages"].append({"role":"assistant","content":reply})
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
        em = [{"role":"system","content":EVALUATION_SYSTEM_PROMPT},
              {"role":"user","content": f"Ερώτηση: {q.get('question_text','')[:2000]}\n\nΑπάντηση μαθητή: {msg}{subq_ctx}"}]
        resp = call_deepseek_with_retry(deepseek_client.chat.completions.create,
                                        model="deepseek-chat", messages=em, temperature=0.1, max_tokens=600,
                                        response_format={"type":"json_object"})
        raw = strip_reasoning(resp.choices[0].message.content or "{}")
        try: ev = json.loads(raw)
        except:
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            ev = json.loads(m.group(0)) if m else {"status":"info","critique":raw[:300],"hint":"Δοκίμασε ξανά."}
        if key:
            if len(_response_cache) >= MAX_CACHE_SIZE: del _response_cache[next(iter(_response_cache))]
            _response_cache[key] = ev
        sess["messages"].append({"role":"assistant","content":json.dumps(ev, ensure_ascii=False)})
        return jsonify({"evaluation": ev, "cached": False})
    except APIError as e:
        return jsonify({"evaluation":{"status":"info","critique":str(e),"hint":"Δοκίμασε ξανά."}})
    except Exception as e:
        logger.error(f"Eval error: {e}")
        return jsonify({"evaluation":{"status":"info","critique":"Σφάλμα αξιολόγησης.","hint":"Δοκίμασε ξανά."}})

@app.route("/api/session/next", methods=["POST"])
def next_question():
    body = request.get_json(force=True) or {}
    sid = body.get("session_id","")
    if sid not in sessions:
        return jsonify({"error":"Ξεκίνα νέα συνεδρία."}),400
    s = sessions[sid]
    s.setdefault("history",[]).append({"question":format_exam_question(s["current_question"], subject_id=s.get("subject_id","informatics")),"messages":list(s["messages"])})
    s["completed_count"]+=1; s["total_points"]+=s["current_question"]["points"]
    import random
    subj_id = s.get("subject_id", "informatics")
    subject_cfg = load_subject_config(subj_id)
    parts = subject_cfg.get("parts", ["Θέμα 2", "Θέμα 4"])
    candidates = [x for x in exam_data if x["part"] in parts and x["id"] not in s["seen_ids"]]
    q = random.choice(candidates) if candidates else None
    if not q: return jsonify({"reply":"Δεν υπάρχουν άλλα θέματα! 🎓","session_complete":True})
    s["seen_ids"].add(q["id"]); s["current_question"]=q
    try:
        subj_p = _load_subject_prompts(subj_id)
        tutor = subj_p.GREEK_TUTOR_SYSTEM_PROMPT
    except:
        tutor = GREEK_TUTOR_SYSTEM_PROMPT
    s["messages"]=[{"role":"system","content":(tutor+"\n"+f"Θέμα: {q['part']}\n"+trend_context)}]
    s["messages"]=[{"role":"system","content":(GREEK_TUTOR_SYSTEM_PROMPT+"\n"+f"Θέμα: {q['part']}\n"+trend_context)}]
    return jsonify({"question":format_exam_question(q, subject_id=s.get("subject_id","informatics")),"stats":{"completed":s["completed_count"],"total_points":s["total_points"],"remaining":len(exam_data)-len(s["seen_ids"])}})

@app.route("/api/session/previous", methods=["POST"])
def previous():
    body = request.get_json(force=True) or {}
    sid = body.get("session_id","")
    if sid not in sessions: return jsonify({"error":"Ξεκίνα νέα συνεδρία."}),400
    s = sessions[sid]; h = s.get("history",[])
    if not h: return jsonify({"error":"Δεν υπάρχει προηγούμενο θέμα."}),400
    p = h.pop()
    pq = next((x for x in exam_data if x["id"]==p["question"]["id"]),None)
    if not pq: return jsonify({"error":"Το προηγούμενο θέμα δεν βρέθηκε."}),500
    s["current_question"]=pq; s["messages"]=p["messages"]
    s["completed_count"]=max(0,s["completed_count"]-1)
    s["total_points"]=max(0,s["total_points"]-pq.get("points",0))
    return jsonify({"question":format_exam_question(pq, subject_id=s.get("subject_id","informatics")),"stats":{"completed":s["completed_count"],"total_points":s["total_points"],"remaining":len(exam_data)-len(s["seen_ids"])},"has_previous":len(h)>0})

@app.route("/api/session/stats", methods=["POST"])
def stats():
    body = request.get_json(force=True) or {}
    sid = body.get("session_id","")
    if sid not in sessions: return jsonify({"error":"Έληξε."}),400
    s = sessions[sid]
    return jsonify({"completed":s["completed_count"],"total_points":s["total_points"],"remaining":len(exam_data)-len(s["seen_ids"])})

@app.route("/api/topics")
def topics():
    return jsonify({"topics":[{"topic":t,"priority":round(s,2)} for t,s in ranked[:10]],"total_topics":len(ranked)})

@app.route("/health")
def health():
    return jsonify({"status":"ok","questions_loaded":len(exam_data) if exam_data else 0,"deepseek_ready":deepseek_client is not None,"sessions":len(sessions)})

# ── Hints
def _get_subquestions(qid, subject_id="informatics"):
    v2 = _load_v2_data(subject_id).get(str(qid),{})
    return [{"number":s["number"],"content":s.get("content","")} for s in v2.get("sections",[]) if s["type"]=="sub_question"]

def _filter_answer_for_subq(full_answer, subq_number, subq_content):
    """Use LLM to extract only the answer portion relevant to a specific sub-question."""
    if not deepseek_client or not full_answer:
        return full_answer
    clean_answer = re.sub(r'<[^>]+>', ' ', full_answer)[:3000]
    try:
        resp = call_deepseek_with_retry(deepseek_client.chat.completions.create,
            model="deepseek-chat",
            messages=[{"role":"system","content":"Είσαι βοηθός. Από το πλήρες κείμενο απάντησης, επέστρεψε ΜΟΝΟ το τμήμα που αντιστοιχεί στο συγκεκριμένο υποερώτημα. Κράτα τη φυσική γλώσσα, μην προσθέσεις τίποτα δικό σου."},
                      {"role":"user","content":f"Πλήρης απάντηση:\n{clean_answer}\n\nΥποερώτημα: {subq_number}\nΕκφώνηση: {subq_content}\n\nΕπέστρεψε μόνο την απάντηση για το υποερώτημα {subq_number}, αυτολεξεί όπως είναι στο κείμενο:"}],
            temperature=0.1, max_tokens=500)
        filtered = strip_reasoning(resp.choices[0].message.content or "")
        if filtered and len(filtered) > 15:
            return filtered.replace('\n', '<br>')
    except Exception as e:
        logger.warning(f"Answer filtering failed for subq {subq_number}: {e}")
    return full_answer  # fallback

def _handle_hint(sess):
    qid = str(sess["current_question"]["id"])
    subj = sess.get("subject_id", "informatics")
    v2 = _load_v2_data(subj).get(qid,{})
    sqs = _get_subquestions(qid, subj) or [{"number":"?","content":""}]
    hs = sess.get("hint_state",{"subqIdx":0,"hintCount":0,"totalSubqs":len(sqs)})
    si, hc = hs.get("subqIdx",0), hs.get("hintCount",0)
    if si >= len(sqs): return jsonify({"all_done":True,"hint_state":hs,"reply":"✅ Ολοκλήρωσες όλα τα υποερωτήματα!"})
    sn = sqs[si]["number"]
    hints = v2.get("hints",[])
    ht = hints[si]["hints"][hc]["hint_text"] if si < len(hints) and hc < len(hints[si].get("hints",[])) else None
    if not ht:
        hs["subqIdx"]=si+1; hs["hintCount"]=0; sess["hint_state"]=hs
        full_answer = v2.get("answer_html","")
        filtered = _filter_answer_for_subq(full_answer, sn, sqs[si].get("content","")) if deepseek_client else full_answer
        return jsonify({"html": filtered or full_answer, "hint_state":hs,"is_full_answer":True,"reply":f"📚 Υποερώτημα {sn} — Πλήρης λύση."})
    hc+=1; hs["hintCount"]=hc; sess["hint_state"]=hs
    if hc >= 4:
        hs["subqIdx"]=si+1; hs["hintCount"]=0; sess["hint_state"]=hs
        full_answer = v2.get("answer_html","")
        filtered = _filter_answer_for_subq(full_answer, sn, sqs[si].get("content","")) if deepseek_client else full_answer
        return jsonify({"html": filtered or full_answer, "hint_state":hs,"is_full_answer":True,"reply":f"📚 Υποερώτημα {sn} — Πλήρης λύση."})
    return jsonify({"html":f'<div class="hint-box"><b>Υποερώτημα {sn}</b><br><br>{ht}</div>',"hint_state":hs,"subq_num":sn,"level":hc})

@app.route("/api/session/hint", methods=["POST"])
def hint():
    body = request.get_json(force=True) or {}
    sid = body.get("session_id","")
    if sid not in sessions: return jsonify({"error":"Έληξε η συνεδρία. Ξεκίνα νέα."}),400
    sess = sessions[sid]
    ch = body.get("hint_state",{})
    sh = sess.get("hint_state",{})
    if ch:
        sh["subqIdx"] = ch.get("subqIdx", sh.get("subqIdx",0))
        sh["hintCount"] = ch.get("hintCount", sh.get("hintCount",0))
    if sh.get("question_id") != str(sess["current_question"]["id"]):
        sh = {"subqIdx":0,"hintCount":0,"totalSubqs":len(_get_subquestions(str(sess["current_question"]["id"]))) or 1,"question_id":str(sess["current_question"]["id"])}
    sess["hint_state"] = sh
    return jsonify(_handle_hint(sess).get_json())

@app.route("/stream_chat", methods=["POST"])
def stream():
    body = request.get_json(force=True) or {}
    sid, msg = body.get("session_id",""), body.get("message","").strip()
    if sid not in sessions: return jsonify({"error":"Έληξε."}),400
    sess = sessions[sid]; sess["messages"].append({"role":"user","content":msg})
    def gen():
        full = ""
        try:
            for c in deepseek_client.chat.completions.create(model="deepseek-chat",messages=sess["messages"].copy(),temperature=0.2,max_tokens=500,stream=True):
                if c.choices and c.choices[0].delta.content:
                    t=c.choices[0].delta.content; full+=t
                    yield f"data: {json.dumps({'token':t})}\n\n"
            yield f"data: {json.dumps({'done':True,'full_reply':full})}\n\n"
            sess["messages"].append({"role":"assistant","content":full})
        except Exception as e:
            yield f"data: {json.dumps({'error':str(e)})}\n\n"
    return Response(stream_with_context(gen()),mimetype="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

# ── Startup
load_data()
init_deepseek()
logger.info(f"App ready — {len(exam_data)} questions")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(); p.add_argument("--port",type=int,default=5050); p.add_argument("--debug",action="store_true")
    a = p.parse_args()
    app.run(host="0.0.0.0",port=a.port,debug=a.debug)