#!/usr/bin/env python3
"""Build questions_v2.json for Physics from DOCX files"""
import json, os, re, html as _html
from docx import Document

BASE = os.path.dirname(os.path.abspath(__file__))
DOC_DIR = os.path.join(BASE, "data/subjects/fysiki_prosanatolismoy/raw/docx")
V2_FILE = os.path.join(BASE, "data/subjects/fysiki_prosanatolismoy/questions_v2.json")

def esc(s):
    return _html.escape(s) if s else ""

v2 = json.load(open(V2_FILE, encoding="utf-8"))
rebuilt = 0

for q in v2:
    qid = q["id"]
    path = os.path.join(DOC_DIR, f"{qid}-0.doc")
    if not os.path.exists(path): continue
    
    doc = Document(path)
    html = []
    
    for p in doc.paragraphs:
        t = p.text.strip()
        if not t: continue
        
        # Section header
        if re.match(r'^ΘΕΜΑ\s+[Α-Δ]', t):
            html.append(f'<div class="sec-header">{esc(t)}</div>')
        # Points
        elif re.match(r'^Μονάδες\s+\d+', t):
            m = re.search(r'Μονάδες\s+(\d+)', t)
            html.append(f'<div class="points-chip">⭐ {m.group(1)} μονάδες</div>')
        # Sub-question (4.1, 4.2, β), etc)
        elif re.match(r'^(\d+\.\d+|[α-ωΑ-Ω])\)', t):
            m = re.match(r'^((\d+\.\d+|[α-ωΑ-Ω]))\)\s*(.*)', t)
            if m:
                num = m.group(1)
                text = m.group(3)
                html.append(f'<div class="subq"><span class="subq-num">{esc(num)})</span> <span class="subq-text">{esc(text)}</span></div>')
            else:
                html.append(f'<p class="text-content">{esc(t)}</p>')
        # Description text
        else:
            html.append(f'<p class="text-content">{esc(t)}</p>')
    
    q["question_html"] = "\n".join(html)
    q["question_html_parts"] = html
    rebuilt += 1

with open(V2_FILE, "w", encoding="utf-8") as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)

print(f"Rebuilt {rebuilt}/{len(v2)} questions")
# Verify
q0 = v2[0]
print(q0.get("question_html","")[:400])
