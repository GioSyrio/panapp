#!/usr/bin/env python3
"""
Final definitive rebuild: raw DOCX XML parsing with VML image detection.
Maps each paragraph's VML images → OCR LaTeX → injects formulas at correct positions.
"""
import json, os, re, zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOC_DIR = os.path.join(BASE_DIR, "data", "subjects", "mathematics", "raw", "docx")
OCR_FILE = os.path.join(BASE_DIR, "data", "subjects", "mathematics", "ocr_results.json")
V2_FILE = os.path.join(BASE_DIR, "data", "subjects", "mathematics", "questions_v2.json")

def e(s):
    return (s.replace("&", "&").replace("<", "<")
            .replace(">", ">").replace('"', """))

def build_rId_to_filename(rels_xml):
    """Extract rId → clean image filename from relationship XML."""
    rid_map = {}
    for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels_xml):
        rid, target = m.group(1), m.group(2)
        if 'image' in target.lower() or 'media' in target.lower():
            fname = target.rsplit('/', 1)[-1] if '/' in target else target
            clean = fname.replace('.wmf', '.png').replace('.emf', '.png')
            rid_map[rid] = clean
    return rid_map

def parse_paragraphs(doc_xml, rid_map, ocr_latex):
    """Parse DOCX paragraphs and inject OCR formulas at VML image positions."""
    html = []
    paragraphs = re.findall(r'<w:p[ >](.*?)</w:p>', doc_xml, re.DOTALL)
    
    for p_xml in paragraphs:
        # Extract text
        texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', p_xml)
        text = ''.join(texts).strip()
        
        # Find VML/DrawingML image rIds
        rids = set()
        rids.update(re.findall(r'r:id="(rId\d+)"', p_xml))      # VML
        rids.update(re.findall(r'r:embed="(rId\d+)"', p_xml))    # DrawingML
        
        # Get OCR formulas for this paragraph's images
        formulas = []
        for rid in rids:
            if rid in rid_map:
                fname = rid_map[rid]
                latex = ocr_latex.get(fname, '')
                if latex:
                    formulas.append(latex)
        
        if not text and not formulas:
            continue
        
        # Structure matching
        if re.match(r'^ΘΕΜΑ\s+[Α-Δ]', text):
            html.append(f'<div class="sec-header">{e(text)}</div>')
        elif re.match(r'^[α-ωΑ-Ω]\)\s', text):
            m = re.match(r'^([α-ωΑ-Ω])\)\s*(.*)', text)
            html.append(f'<div class="subq"><span class="subq-num">{m.group(1)})</span> '
                       f'<span class="subq-text">{e(m.group(2))}</span></div>')
        elif re.match(r'\(?Μονάδες\s+\d+\)?', text):
            m = re.match(r'\(?Μονάδες\s+(\d+)\)?', text)
            html.append(f'<div class="points-chip">⭐ {m.group(1)} μονάδες</div>')
        else:
            # Regular text paragraph — inject its formulas inline
            content = e(text)
            for f in formulas:
                content += f' ${f}$ '
            if content.strip():
                html.append(f'<p class="text-content">{content}</p>')
    
    return '\n'.join(html)

# ── Main ──
ocr_all = json.load(open(OCR_FILE, encoding='utf-8'))
v2 = json.load(open(V2_FILE, encoding='utf-8'))

rebuilt = 0
errors = 0

for q in v2:
    qid = q['id']
    docx_path = os.path.join(DOC_DIR, f"{qid}-0.doc")
    if not os.path.exists(docx_path):
        errors += 1
        continue
    
    try:
        with zipfile.ZipFile(docx_path) as zf:
            doc_xml = zf.read('word/document.xml').decode('utf-8')
            rels_xml = zf.read('word/_rels/document.xml.rels').decode('utf-8')
    except Exception:
        errors += 1
        continue
    
    # Build rId → filename map
    rid_map = build_rId_to_filename(rels_xml)
    
    # Build OCR LaTeX map for this question
    ocr_latex = {}
    for key, val in ocr_all.items():
        parts = key.split('/')
        if len(parts) == 2 and parts[0] == str(qid):
            latex = val.get('latex', '').strip('$ ')
            latex = re.sub(r'^```\w*\n?|```$', '', latex).strip()
            if latex:
                ocr_latex[parts[1]] = latex
    
    # Build HTML
    q['question_html'] = parse_paragraphs(doc_xml, rid_map, ocr_latex)
    rebuilt += 1

# Save
with open(V2_FILE, 'w', encoding='utf-8') as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)

print(f'✅ {rebuilt} questions rebuilt ({errors} errors)')
print(f'✅ Hints: {sum(1 for q in v2 if q.get("hints"))}/202')

# Verify
for cid in [23937, 34151, 34024]:
    qq = next((q for q in v2 if q['id'] == cid), None)
    if qq:
        h = qq.get('question_html', '')
        latex_count = h.count('$') // 2
        img_count = h.count('<img')
        print(f'Q{cid}: {latex_count} LaTeX, {img_count} imgs')