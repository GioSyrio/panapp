#!/usr/bin/env python3
"""Final rebuild: merge DOCX text with OCR formulas at correct paragraph positions."""
import json, os, re
from docx import Document

def e(s):
    return (s.replace("&", "&").replace("<", "<")
            .replace(">", ">").replace('"', """))

BASE = os.path.dirname(os.path.abspath(__file__))
DOC_DIR = os.path.join(BASE, "data", "subjects", "mathematics", "raw", "docx")
OCR_FILE = os.path.join(BASE, "data", "subjects", "mathematics", "ocr_results.json")
V2_FILE = os.path.join(BASE, "data", "subjects", "mathematics", "questions_v2.json")

ocr = json.load(open(OCR_FILE))
v2 = json.load(open(V2_FILE))

rebuilt = 0
for q in v2:
    qid = q['id']
    path = os.path.join(DOC_DIR, f"{qid}-0.doc")
    if not os.path.exists(path): continue
    
    doc = Document(path)
    
    # Formula images for this question: filename → LaTeX
    formulas = {}
    for k, v in ocr.items():
        parts = k.split('/')
        if len(parts)==2 and parts[0]==str(qid):
            latex = v.get('latex','').strip('$ ')
            latex = re.sub(r'^```\w*\n?|```$','',latex).strip()
            if latex: formulas[parts[1]] = latex
    
    # Collect ALL image references from DOCX relationships
    images = {}  # rId → clean filename
    for rid, rel in doc.part.rels.items():
        if 'image' in str(rel.reltype).lower():
            target = rel.target_ref.split('/')[-1] if '/' in rel.target_ref else rel.target_ref
            clean = target.replace('.wmf','.png').replace('.emf','.png').replace('media/','')
            images[rid] = clean
    
    # Parse paragraphs
    html = []
    for p in doc.paragraphs:
        t = p.text.strip()
        xml = p._element.xml
        
        # Find image references (try multiple patterns)
        refs = set()
        refs.update(re.findall(r'r:embed="(rId\d+)"', xml))
        refs.update(re.findall(r'r:id="(rId\d+)"', xml))
        refs.update(re.findall(r'r:link="(rId\d+)"', xml))
        
        # Map rIds to OCR LaTeX
        para_formulas = []
        for rid in refs:
            if rid in images:
                fname = images[rid]
                if fname in formulas:
                    para_formulas.append(formulas[fname])
        
        if not t and not para_formulas:
            continue
        
        # Structure matching
        if re.match(r'^ΘΕΜΑ\s+[Α-Δ]', t):
            html.append(f'<div class="sec-header">{e(t)}</div>')
        elif re.match(r'^[α-ωΑ-Ω]\)\s', t):
            m = re.match(r'^([α-ωΑ-Ω])\)\s*(.*)', t)
            html.append(f'<div class="subq"><span class="subq-num">{m.group(1)})</span> <span class="subq-text">{e(m.group(2))}</span></div>')
        elif re.match(r'\(?Μονάδες\s+\d+\)?', t):
            m = re.match(r'\(?Μονάδες\s+(\d+)\)?', t)
            html.append(f'<div class="points-chip">⭐ {m.group(1)} μονάδες</div>')
        else:
            # Regular text — insert formulas from this paragraph
            content = e(t)
            for f in para_formulas:
                content += f' ${f}$ '
            if content.strip():
                html.append(f'<p class="text-content">{content}</p>')
    
    q['question_html'] = '\n'.join(html)
    rebuilt += 1

with open(V2_FILE, 'w', encoding='utf-8') as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)

print(f'✅ {rebuilt}/{len(v2)} questions rebuilt')

# Verify
for cid in [23937, 34151]:
    qq = next(q for q in v2 if q['id'] == cid)
    h = qq.get('question_html','')
    f = re.findall(r'\$([^$]+)\$', h)
    d = len(f) - len(set(f))
    i = h.count('<img')
    print(f'Q{cid}: {len(f)} formulas, {d} dups, {i} imgs')

print(f'Hints: {sum(1 for q in v2 if q.get("hints"))}/202')