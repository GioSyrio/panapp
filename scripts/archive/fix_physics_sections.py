#!/usr/bin/env python3
"""
fix_physics_sections.py — Rebuild physics questions_v2.json with proper subq numbering

Physics API returns question: 2 (integer only). The real question text is in DOCX.
This script:
  1. Reads the DOCX for each question
  2. Parses multi-level sub-question numbering (2.1, 2.1.A, 2.1.B, 2.2, etc.)
  3. Rebuilds sections + question_html
  4. Migrates existing hints to match new subq indices (zero API cost)
  5. Clears the llm_hints_progress but preserves hints in questions_v2.json

Usage:
    python3 fix_physics_sections.py --slug fysiki_prosanatolismoy
    python3 fix_physics_sections.py --all    # all DOCX-based subjects
"""

import json, os, re, argparse
from docx import Document
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
PROTECTED = {"mathematics", "informatics", "mathimatika_prosanatolismoy", "pliroforiki"}

# ── Multi-level sub-question patterns ────────────────────────────────────────
# 2.1., 2.1.A., 2.1.Β., 2.1.1., Α), Β), i), ii)
SUBQ_LEVEL1_RE = re.compile(r'^(\d+\.\d+)\.?\s*(.*)')          # 2.1. text
SUBQ_LEVEL2_RE = re.compile(r'^(\d+\.\d+\.[A-Z])\.?\s*(.*)')   # 2.1.A. text or 2.1.A.Να...
SUBQ_LEVEL2_GRK_RE = re.compile(r'^(\d+\.\d+\.\s*[Α-Ω])\.?\s*(.*)')  # 2.1.Α. text or 2.1.Α.Να...
SUBQ_ALPHA_RE = re.compile(r'^([Α-Ω])\)\s+(.*)')               # Α) text
SUBQ_ROMAN_RE = re.compile(r'^(\(?[ivx]+\)?)\s+(.*)', re.I)    # i) ii) or (i) (ii)
POINTS_RE = re.compile(r'Μονάδες\s+(\d+)', re.IGNORECASE)
SEC_HEADER_RE = re.compile(r'^ΘΕΜΑ\s+(\d+)', re.IGNORECASE)

def esc(s):
    import html
    return html.escape(str(s)) if s else ""

def parse_physics_docx(docx_path):
    """Parse a physics DOCX into structured sections with proper numbering."""
    if not os.path.exists(docx_path):
        return None
    
    try:
        doc = Document(docx_path)
    except Exception as e:
        return None
    
    sections = []
    
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        
        # Section header (ΘΕΜΑ 2)
        m = SEC_HEADER_RE.match(text)
        if m:
            sections.append({"type": "section_header", "content": text})
            continue
        
        # Points line
        m = POINTS_RE.match(text)
        if m:
            sections.append({"type": "points", "content": text})
            continue
        
        # Level 2 sub-question: 2.1.A. or 2.1.Α.
        m = SUBQ_LEVEL2_RE.match(text) or SUBQ_LEVEL2_GRK_RE.match(text)
        if m:
            sections.append({"type": "sub_question", "number": m.group(1) + ".", "content": m.group(2)})
            continue
        
        # Level 1 sub-question: 2.1. 
        m = SUBQ_LEVEL1_RE.match(text)
        if m:
            sections.append({"type": "sub_question", "number": m.group(1) + ".", "content": m.group(2)})
            continue
        
        # Alpha sub-question: Α) or Β)
        m = SUBQ_ALPHA_RE.match(text)
        if m:
            sections.append({"type": "sub_question", "number": m.group(1) + ")", "content": m.group(2)})
            continue
        
        # Roman numeral: i) ii) or (i) (ii)
        m = SUBQ_ROMAN_RE.match(text)
        if m:
            sections.append({"type": "sub_question", "number": m.group(1), "content": m.group(2)})
            continue
        
        # Plain text
        sections.append({"type": "text", "content": text})
    
    return sections

def build_html(sections):
    """Render sections to HTML."""
    html = []
    for s in sections:
        if s["type"] == "section_header":
            html.append(f'<div class="sec-header">{esc(s["content"])}</div>')
        elif s["type"] == "sub_question":
            html.append(
                f'<div class="subq">'
                f'<span class="subq-num">{esc(s["number"])}</span> '
                f'<span class="subq-text">{esc(s["content"])}</span>'
                f'</div>')
        elif s["type"] == "points":
            m = re.search(r'Μονάδες\s+(\d+)', s["content"])
            pts = m.group(1) if m else "?"
            html.append(f'<div class="points-chip">⭐ {pts} μονάδες</div>')
        elif s["type"] == "text":
            html.append(f'<p class="text-content">{esc(s["content"])}</p>')
    return "\n".join(html)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--slug", default="fysiki_prosanatolismoy")
    p.add_argument("--all", action="store_true")
    a = p.parse_args()

    if a.all:
        slugs = [d for d in os.listdir(os.path.join(BASE, "data", "subjects"))
                 if os.path.isdir(os.path.join(BASE, "data", "subjects", d))
                 and d not in PROTECTED and not d.startswith(".")]
    else:
        slugs = [a.slug]

    total_fixed = 0

    for slug in slugs:
        v2_path = os.path.join(BASE, "data", "subjects", slug, "questions_v2.json")
        if not os.path.exists(v2_path):
            print(f"  ❌ {slug}: no questions_v2.json")
            continue

        with open(v2_path, encoding="utf-8") as f:
            v2 = json.load(f)

        # Save existing hints for migration
        old_hints = {}
        for q in v2:
            if q.get("hints"):
                old_hints[q["id"]] = q["hints"]

        fixed = 0
        for q in v2:
            qid = q["id"]
            docx_path = os.path.join(BASE, "data", "subjects", slug, "raw", "docx", f"{qid}-0.doc")
            
            if not os.path.exists(docx_path):
                continue

            sections = parse_physics_docx(docx_path)
            if not sections:
                continue

            q["sections"] = sections
            q["question_html"] = build_html(sections)
            q["question_html_parts"] = sections  # Add parts for consistency
            q["question_text"] = "\n".join(
                s["content"] if s["type"] in ("text", "sub_question") else ""
                for s in sections if s.get("content")
            )[:3000]
            fixed += 1

            # Migrate hints: map old subq indices to new ones
            old_h = old_hints.get(qid, [])
            new_subqs = [s for s in sections if s["type"] == "sub_question"]
            
            if old_h and new_subqs:
                # Simple mapping: assume same order, just update numbers
                for i, new_sq in enumerate(new_subqs):
                    if i < len(old_h):
                        old_h[i]["number"] = new_sq["number"]
                    else:
                        # Extra sub-questions found — add empty hint slot
                        old_h.append({"subq_idx": i, "number": new_sq["number"], "hints": []})
                
                # Trim extra hints if fewer subqs than hints
                old_h = old_h[:len(new_subqs)]
                q["hints"] = old_h

        with open(v2_path, "w", encoding="utf-8") as f:
            json.dump(v2, f, ensure_ascii=False, indent=2)

        print(f"  ✅ {slug}: {fixed}/{len(v2)} questions rebuilt from DOCX")

        # Clear progress file (preserves hints in v2)
        prog_path = os.path.join(BASE, "data", "subjects", slug, "llm_hints_progress.json")
        if os.path.exists(prog_path):
            with open(prog_path, encoding="utf-8") as f:
                prog = json.load(f)
            prog["completed"] = prog.get("completed", [])[:0]  # clear
            with open(prog_path, "w", encoding="utf-8") as f:
                json.dump(prog, f, ensure_ascii=False, indent=2)
            print(f"     Cleared progress tracker (hints preserved)")

        total_fixed += fixed

    print(f"\n✅ Done! {total_fixed} questions rebuilt across {len(slugs)} subjects")
    print(f"   Hints migrated — no LLM regeneration needed")

if __name__ == "__main__":
    main()