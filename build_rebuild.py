#!/usr/bin/env python3
"""
Final definitive rebuild: merges DOCX text with OCR formulas at
the correct paragraph position by reading image references per paragraph.
"""
import json, os, re
from docx import Document

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOC_DIR = os.path.join(BASE_DIR, "data", "subjects", "mathematics", "raw", "docx")
OCR_FILE = os.path.join(BASE_DIR, "data", "subjects", "mathematics", "ocr_results.json")
V2_FILE = os.path.join(BASE_DIR, "data", "subjects", "mathematics", "questions_v2.json")

def e(s):
    return (s.replace("&", "&").replace("<", "<")
            .replace(">", ">").replace('"', """))

def build_html(qid, doc, ocr_map):
    """Build question HTML with formulas injected at the correct paragraph positions."""
    
    # Map DOCX relationship rIds to OCR filenames
    rid_to_ocr = {}
    for rid, rel in doc.part.rels.items():
        if 'image' in str(rel.reltype).lower():
            target = rel.target_ref.split('/')[-1] if '/' in rel.target_ref else rel.target_ref
            clean = target.replace('.wmf', '.png').replace('.emf', '.png').replace('media/', '')
            if clean in ocr_map:
                rid_to_ocr[rid] = ocr_map[clean]
    
    html_parts = []
    current_text = ""
    
    for p in doc.paragraphs:
        text = p.text.strip()
        xml = p._element.xml
        
        # Find all image references in this paragraph
        refs = set()
        refs.update(re.findall(r'r:embed="(rId\d+)"', xml))
        refs.update(re.findall(r'r:id="(rId\d+)"', xml))
        
        # Get OCR formulas for this paragraph's images
        para_formulas = []
        for rid in refs:
            if rid in rid_to_ocr:
                para_formulas.append(rid_to_ocr[rid])
        
        if not text and not para_formulas:
            continue
        
        # Section header: ΘΕΜΑ Α, ΘΕΜΑ Β, etc.
        m = re.match(r'^ΘΕΜΑ\s+([Α-Δ])', text)
        if m:
            if current_text:
                html_parts.append(f'<p class="text-content">{e(current_text)}</p>')
                current_text = ""
            html_parts.append(f'<div class="sec-header">{e(text)}</div>')
            continue
        
        # Sub-question: α) β) γ) δ)  
        m = re.match(r'^([α-ωΑ-Ω])\)\s*(.*)', text)
        if m:
            if current_text:
                html_parts.append(f'<p class="text-content">{e(current_text)}</p>')
                current_text = ""
            html_parts.append(f'<div class="subq"><span class="subq-num">{m.group(1)})</span> '
                             f'<span class="subq-text">{e(m.group(2))}</span></div>')
            continue
        
        # Points: Μονάδες 7 or (Μονάδες 7)
        m = re.match(r'\(?Μονάδες\s+(\d+)\)?', text)
        if m:
            if current_text:
                html_parts.append(f'<p class="text-content">{e(current_text)}</p>')
                current_text = ""
            html_parts.append(f'<div class="points-chip">⭐ {m.group(1)} μονάδες</div>')
            continue
        
        # Regular text paragraph — inject its formulas inline
        line = e(text)
        if para_formulas:
            for f in para_formulas:
                line += f' ${f}$ '
        
        if current_text:
            current_text += ' ' + line
        else:
            current_text = line
    
    if current_text:
        html_parts.append(f'<p class="text-content">{e(current_text)}</p>')
    
    return '\n'.join(html_parts)

# Main
ocr = json.load(open(OCR_FILE))
v2 = json.load(open(V2_FILE))

rebuilt = 0
for q in v2:
    qid = q['id']
    docx_path = os.path.join(DOC_DIR, f"{qid}-0.doc")
    if not os.path.exists(docx_path):
        continue
    
    doc = Document(docx_path)
    
    # Build OCR map for this question
    ocr_map = {}
    for k, v in ocr.items():
        parts = k.split('/')
        if len(parts) == 2 and parts[0] == str(qid):
            latex = v.get('latex', '').strip('$ ')
            latex = re.sub(r'^```\w*\n?|```$', '', latex).strip()
            if latex:
                ocr_map[parts[1]] = latex
    
    q['question_html'] = build_html(qid, doc, ocr_map)
    rebuilt += 1

with open(V2_FILE, 'w', encoding='utf-8') as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)

print(f'✅ {rebuilt}/{len(v2)} questions rebuilt')
print(f'✅ Hints: {sum(1 for q in v2 if q.get("hints"))}/202')

# Verify key questions
for cid in [23937, 34151, 34024]:
    qq = next((q for q in v2 if q['id'] == cid), None)
    if qq:
        h = qq['question_html']
        f = re.findall(r'\$([^$]+)\$', h)
        u = len(set(f))
        d = len(f) - u
        img = h.count('<img')
        print(f'Q{cid}: {len(f)} formulas, {d} duplicates, {img} imgs, {u} unique')