#!/usr/bin/env python3
"""
build_questions_universal.py — Convert raw items to questions_v2 for any subject

Reads items_raw.json (from scrape_subject.py) and creates questions_v2.json
with structured sections, pre-rendered HTML, and question classification.

Usage:
    python3 build_questions_universal.py --slug fysiki_prosanatolismoy
    python3 build_questions_universal.py --all
"""

import json, os, re, argparse, html as _html
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PARTS = ["Θέμα Α", "Θέμα Β", "Θέμα Γ", "Θέμα Δ"]

# ── PROTECTED: Never overwrite these — hours of manual work ──────────────────
PROTECTED_SLUGS = {"mathematics", "informatics", "mathimatika_prosanatolismoy", "pliroforiki"}

def esc(s):
    return _html.escape(s) if s else ""

def parse_parts(items):
    parts_seen = set()
    for item in items:
        q = item.get("question", "")
        if not isinstance(q, str):
            q = str(q) if q else ""
        m = re.findall(r'(ΘΕΜΑ\s+[Α-ΔA])', q)
        parts_seen.update(m)
    normalized = []
    for p in sorted(parts_seen):
        p = p.upper().replace("A", "Α")
        normalized.append(p)
    return normalized if normalized else DEFAULT_PARTS

def _safe_str(val):
    """Ensure value is a string."""
    if val is None: return ""
    if isinstance(val, str): return val
    if isinstance(val, (dict, list)):
        try: return json.dumps(val, ensure_ascii=False)
        except: return str(val)
    return str(val)

def classify_question(text):
    if not text: return "open_ended_problem"
    t = text.lower()
    if 'σωστό' in t and 'λάθος' in t: return "true_false"
    if 'επιλέξτε' in t or 'επιλογή' in t: return "multiple_choice"
    if 'αντιστοιχ' in t or 'στήλη' in t: return "matching"
    return "open_ended_problem"

def build_sections(question_text):
    sections = []
    for line in question_text.replace('\r\n','\n').replace('\r','\n').split('\n'):
        line = line.strip()
        if not line: continue
        if re.match(r'^(ΘΕΜΑ\s+[Α-Δ])', line, re.IGNORECASE):
            sections.append({"type":"section_header","content":line})
        elif re.match(r'^([α-ωΑ-Ω])\s*[\)\.]\s*(.*)', line):
            m = re.match(r'^([α-ωΑ-Ω])\s*[\)\.]\s*(.*)', line)
            sections.append({"type":"sub_question","number":m.group(1)+")","content":m.group(2)})
        elif re.match(r'\(?Μονάδες\s+(\d+)\)?', line, re.IGNORECASE):
            sections.append({"type":"points","content":line})
        else:
            sections.append({"type":"text","content":line})
    return sections

def build_question_html(sections):
    html = []
    for s in sections:
        if s["type"] == "section_header":
            html.append(f'<div class="sec-header">{esc(s["content"])}</div>')
        elif s["type"] == "sub_question":
            html.append(f'<div class="subq"><span class="subq-num">{esc(s["number"])}</span> <span class="subq-text">{esc(s["content"])}</span></div>')
        elif s["type"] == "points":
            m = re.search(r'Μονάδες\s+(\d+)', s["content"])
            html.append(f'<div class="points-chip">⭐ {m.group(1) if m else "?"} μονάδες</div>')
        elif s["type"] == "text":
            html.append(f'<p class="text-content">{esc(s["content"])}</p>')
    return "\n".join(html)

def build_answer_html(answer_text):
    if not answer_text: return ""
    lines = answer_text.replace('\r\n','\n').replace('\r','\n').split('\n')
    return "\n".join(f'<div class="sol-step"><div class="sol-step-text">{esc(l.strip())}</div></div>' for l in lines if l.strip())

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--slug")
    p.add_argument("--all", action="store_true")
    a = p.parse_args()

    data_root = os.path.join(BASE_DIR, "data", "subjects")
    targets = []
    if a.all:
        for slug in os.listdir(data_root):
            if slug in PROTECTED_SLUGS:
                continue
            ip = os.path.join(data_root, slug, "items_raw.json")
            vp = os.path.join(data_root, slug, "questions_v2.json")
            if os.path.exists(ip) and not os.path.exists(vp):
                targets.append(slug)
        print(f"📚 {len(targets)} subjects")
    else:
        targets = [a.slug] if a.slug else []

    total = 0
    for slug in targets:
        ip = os.path.join(data_root, slug, "items_raw.json")
        vp = os.path.join(data_root, slug, "questions_v2.json")
        print(f"\n📝 {slug}...")
        with open(ip, encoding="utf-8") as f:
            items = json.load(f)
        parts = parse_parts(items)
        built = []
        for item in items:
            qt = _safe_str(item.get("question",""))
            at = _safe_str(item.get("answer", item.get("solution","")))
            secs = build_sections(qt)
            built.append({
                "id": item["id"],
                "year": item.get("date","")[:4] if item.get("date") else "?",
                "part": parts[0] if parts else "Θέμα Α",
                "points": item.get("durationMin", 10),
                "type": classify_question(qt),
                "conceptual_tags": (item.get("keywords","") or "").split(",") if item.get("keywords") else [],
                "sections": secs,
                "question_html": build_question_html(secs),
                "answer_html": build_answer_html(at),
                "answer_text": at[:3000] if at else "",
            })
        with open(vp, "w", encoding="utf-8") as f:
            json.dump(built, f, ensure_ascii=False, indent=2)
        print(f"  ✅ {len(built)} questions")
        total += len(built)
        # Update config
        cp = os.path.join(BASE_DIR, "subjects", f"{slug}.json")
        if os.path.exists(cp):
            with open(cp, encoding="utf-8") as f: cfg = json.load(f)
            cfg["parts"] = parts
            with open(cp, "w", encoding="utf-8") as f: json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"\n✅ {len(targets)} subjects, {total} questions")

if __name__ == "__main__":
    main()