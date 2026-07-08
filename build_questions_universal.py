#!/usr/bin/env python3
"""
build_questions_universal.py — Convert raw items to questions_v2 for any subject

Reads items_raw.json (from scrape_subject.py) and creates questions_v2.json
with structured sections, pre-rendered HTML, question classification, and
empty hint scaffolding for later LLM enrichment.

Usage:
    python3 build_questions_universal.py --slug fysiki_prosanatolismoy
    python3 build_questions_universal.py --all
    python3 build_questions_universal.py --slug istoria --force
"""

import json, os, re, argparse, html as _html
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PARTS = ["Θέμα Α", "Θέμα Β", "Θέμα Γ", "Θέμα Δ"]

# ── PROTECTED: Never overwrite these — hours of manual work ──────────────────
PROTECTED_SLUGS = {
    "mathematics", "informatics", "mathimatika_prosanatolismoy", "pliroforiki",
    # Humanities — expensive LLM-generated data
    "istoria", "istoria_prosanatolismoy",
    "neoelliniki_glossa_kai_logotechnia",
    "latinika", "archaia_elliniki_glossa_kai_grammateia___archaia_ellinika",
}

def esc(s):
    return _html.escape(s) if s else ""

def parse_parts(items):
    """Detect all part labels across the item set."""
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
        # Normalize "ΘΕΜΑ Α" -> "Θέμα Α" (capital correct, accent)
        p = p.replace("ΘΕΜΑ", "Θέμα")
        normalized.append(p)
    return normalized if normalized else DEFAULT_PARTS

def detect_part_from_text(text):
    """Detect the part (Θέμα Α-Δ) from a single question's text."""
    if not text:
        return None
    # Pattern: "3ο ΘΕΜΑ", "ΘΕΜΑ Γ", "Θέμα Δ", "1ο θέμα"
    m = re.search(r'(\d)[οη]\s*(ΘΕΜΑ|θέμα)', text, re.IGNORECASE)
    if m:
        num = int(m.group(1))
        if 1 <= num <= 4:
            return f"Θέμα {['Α','Β','Γ','Δ'][num-1]}"
    m = re.search(r'(ΘΕΜΑ|Θέμα|θέμα)\s*([Α-ΔA])', text)
    if m:
        letter = m.group(2).upper().replace("A", "Α")
        return f"Θέμα {letter}"
    return None

def extract_points_from_text(text):
    """Extract points (μονάδες) from question text. Returns int or None."""
    if not text:
        return None
    # Pattern: "Μονάδες 25", "(Μονάδες 15)", "μονάδες 10", "(25 μονάδες)"
    m = re.search(r'\(?Μονάδες\s+(\d+)\)?', text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r'\(?(\d+)\s*μονάδες?\)?', text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None

def extract_conceptual_tags(item):
    """Extract conceptual tags from raw item's material/learning_outcomes/keywords."""
    tags = []
    # 1. From material names (most common in humanities raw data)
    for mat in item.get("material", []):
        name = mat.get("name", "")
        if name:
            # Clean numbering prefixes like "4. ", "3.1 "
            cleaned = re.sub(r'^\d+(\.\d+)*\s*', '', name).strip()
            if cleaned:
                tags.append(cleaned)
    # 2. From keywords
    kw = item.get("keywords", "")
    if kw and isinstance(kw, str) and kw.strip():
        tags.extend([t.strip() for t in kw.split(",") if t.strip()])
    # 3. From learning outcomes
    for lo in item.get("learning_outcomes", []):
        if isinstance(lo, str) and lo.strip():
            tags.append(lo.strip())
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique

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
    """Build structured sections from raw question text.
    
    Detects: section headers (ΘΕΜΑ Α), sub-questions (α., β., γ., α), β), etc.),
    points lines (Μονάδες 25), and plain text.
    Handles humanities multi-paragraph source texts.
    """
    sections = []
    for line in question_text.replace('\r\n','\n').replace('\r','\n').split('\n'):
        line = line.strip()
        if not line:
            continue
        # Section header: "ΘΕΜΑ Α", "ΘΕΜΑ 3", "3ο ΘΕΜΑ"
        if re.match(r'^(\d[οη]?\s*)?(ΘΕΜΑ|Θέμα|θέμα)\s+[Α-ΔA1-4]', line, re.IGNORECASE):
            sections.append({"type": "section_header", "content": line})
        # Sub-question markers: Greek letters "α.", "α)", "β.", "β)", "γ.", "γ)" etc.
        # Also handles "α )", "β ." with optional spaces
        elif re.match(r'^([α-ωΑ-Ω])\s*[\)\.]\s*(.*)', line):
            m = re.match(r'^([α-ωΑ-Ω])\s*[\)\.]\s*(.*)', line)
            sections.append({"type": "sub_question", "number": m.group(1) + ")", "content": m.group(2)})
        # Points line: "Μονάδες 25", "(Μονάδες 15)"
        elif re.match(r'\(?Μονάδες\s+(\d+)\)?', line, re.IGNORECASE):
            sections.append({"type": "points", "content": line})
        else:
            sections.append({"type": "text", "content": line})
    return sections

def build_question_html(sections):
    """Render sections to HTML for frontend display."""
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
    """Build answer HTML from raw answer text."""
    if not answer_text:
        return ""
    lines = answer_text.replace('\r\n','\n').replace('\r','\n').split('\n')
    html_parts = []
    for l in lines:
        l = l.strip()
        if not l:
            continue
        html_parts.append(f'<div class="sol-step"><div class="sol-step-text">{esc(l)}</div></div>')
    return "\n".join(html_parts)

def build_hint_scaffold(sub_questions):
    """Create empty hint scaffolding for each sub-question.
    
    Each sub-question gets 3 empty hint levels. The LLM enrichment
    script (build_llm_hints.py) will fill these in later.
    """
    if not sub_questions:
        # No sub-questions detected — create one generic hint group
        return [{
            "subq_idx": 0,
            "number": "?",
            "hints": [
                {"level": 1, "hint_text": ""},
                {"level": 2, "hint_text": ""},
                {"level": 3, "hint_text": ""},
            ]
        }]
    hints = []
    for i, sq in enumerate(sub_questions):
        hints.append({
            "subq_idx": i,
            "number": sq.get("number", "?"),
            "hints": [
                {"level": 1, "hint_text": ""},
                {"level": 2, "hint_text": ""},
                {"level": 3, "hint_text": ""},
            ]
        })
    return hints

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--slug", help="Subject slug to process")
    p.add_argument("--all", action="store_true", help="Process all non-protected subjects without existing v2")
    p.add_argument("--force", action="store_true", help="Overwrite existing questions_v2.json")
    a = p.parse_args()

    data_root = os.path.join(BASE_DIR, "data", "subjects")
    targets = []
    if a.all:
        for slug in sorted(os.listdir(data_root)):
            if slug in PROTECTED_SLUGS:
                continue
            ip = os.path.join(data_root, slug, "items_raw.json")
            vp = os.path.join(data_root, slug, "questions_v2.json")
            if os.path.exists(ip):
                if a.force or not os.path.exists(vp):
                    targets.append(slug)
        print(f"📚 {len(targets)} subjects to process")
    elif a.slug:
        ip = os.path.join(data_root, a.slug, "items_raw.json")
        if not os.path.exists(ip):
            print(f"❌ No items_raw.json found for {a.slug}")
            return
        targets = [a.slug]
    else:
        p.print_help()
        return

    if not targets:
        print("📚 No subjects to process. Use --force to overwrite existing files.")
        return

    total = 0
    for slug in targets:
        ip = os.path.join(data_root, slug, "items_raw.json")
        vp = os.path.join(data_root, slug, "questions_v2.json")

        if os.path.exists(vp) and not a.force:
            print(f"  ⏭️  {slug} — already exists (use --force to overwrite)")
            continue

        print(f"\n📝 {slug}...")
        with open(ip, encoding="utf-8") as f:
            items = json.load(f)

        parts = parse_parts(items)
        print(f"  Parts detected: {parts}")

        built = []
        empty_answers = 0
        empty_points = 0
        for item in items:
            qt = _safe_str(item.get("question", ""))
            at = _safe_str(item.get("answer", item.get("solution", "")))

            # Build sections from question text
            secs = build_sections(qt)

            # Extract sub-questions for hints
            subqs = [s for s in secs if s["type"] == "sub_question"]

            # Extract metadata
            part = detect_part_from_text(qt) or (parts[0] if parts else DEFAULT_PARTS[0])
            points = extract_points_from_text(qt)
            if points is None:
                # Fallback: try to detect from any answer text
                points = extract_points_from_text(at) or 0
                empty_points += 1
            tags = extract_conceptual_tags(item)

            answer_html = build_answer_html(at)
            if not answer_html:
                empty_answers += 1

            built.append({
                "id": item["id"],
                "year": item.get("date", "")[:4] if item.get("date") else "?",
                "part": part,
                "points": points,
                "type": classify_question(qt),
                "conceptual_tags": tags,
                "sections": secs,
                "question_html": build_question_html(secs),
                "answer_html": answer_html,
                "answer_text": at[:3000] if at else "",
                "hints": build_hint_scaffold(subqs),
            })

        with open(vp, "w", encoding="utf-8") as f:
            json.dump(built, f, ensure_ascii=False, indent=2)

        print(f"  ✅ {len(built)} questions built")
        if empty_answers:
            print(f"  ⚠️  {empty_answers}/{len(built)} questions have empty answers (needs LLM solution generation)")
        if empty_points:
            print(f"  ⚠️  {empty_points}/{len(built)} questions have uncertain points (review needed)")
        total += len(built)

        # Update subject config parts if they've changed
        cp = os.path.join(BASE_DIR, "subjects", f"{slug}.json")
        if os.path.exists(cp):
            with open(cp, encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["parts"] = parts
            with open(cp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)

    print(f"\n✅ {len(targets)} subjects processed, {total} total questions built")
    print(f"💡 Next: run build_llm_hints.py and build_llm_solutions.py for LLM enrichment")

if __name__ == "__main__":
    main()