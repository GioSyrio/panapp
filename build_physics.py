#!/usr/bin/env python3
"""Build questions_v2.json for Physics from DOCX files — preserves hints"""
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
        
        if re.match(r'^ΘΕΜΑ\s+[Α-Δ]', t):
            html.append(f'<div class="sec-header">{esc(t)}</div>')
        elif re.match(r'^Μονάδες\s+\d+', t):
            m = re.search(r'Μονάδες\s+(\d+)', t)
            html.append(f'<div class="points-chip">⭐ {m.group(1)} μονάδες</div>')
        elif re.match(r'^(\d+\.\d+|[α-ωΑ-Ω])[\s\)\.]', t):
            m = re.match(r'^((\d+\.\d+|[α-ωΑ-Ω]))[\s\)\.]*\s*(.*)', t)
            if m:
                num = m.group(1)
                text = m.group(3)
                html.append(f'<div class="subq"><span class="subq-num">{esc(num)})</span> <span class="subq-text">{esc(text)}</span></div>')
        else:
            html.append(f'<p class="text-content">{esc(t)}</p>')
    
    q["question_html"] = "\n".join(html)
    q["question_html_parts"] = html
    
    # Ensure required fields exist
    if not q.get("question_text"):
        text = re.sub(r'<[^>]+>', ' ', q["question_html"])
        q["question_text"] = re.sub(r'\s+', ' ', text).strip()[:3000]
    try: q["year"] = int(q.get("year", 0))
    except: q["year"] = 2022
    if not q.get("points"):
        pts = re.findall(r'⭐ (\d+) μονάδες', q["question_html"])
        q["points"] = sum(int(p) for p in pts) if pts else 25
    
    rebuilt += 1

with open(V2_FILE, "w", encoding="utf-8") as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)

q0 = v2[0]
classes = set(re.findall(r'class="([^"]+)"', q0.get("question_html","")))
print(f"Rebuilt {rebuilt}/{len(v2)}, hints intact: {bool(q0.get('hints'))}, classes: {classes}")
