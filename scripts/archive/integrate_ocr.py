#!/usr/bin/env python3
"""Integrate GLM-OCR results into questions_v2.json — replace img with LaTeX"""
import json, re, os

results_file = 'data/subjects/mathematics/ocr_results.json'
v2_file = 'data/subjects/mathematics/questions_v2.json'

results = json.load(open(results_file))
v2 = json.load(open(v2_file))

# Build OCR lookup per question
ocr = {}
for key, val in results.items():
    parts = key.split('/')
    if len(parts) == 2:
        qid, fname = parts
        ocr.setdefault(qid, {})[fname] = val.get('latex', '').strip()

replaced_formulas = 0
replaced_graphs = 0

for q in v2:
    qid = str(q['id'])
    html = q.get('question_html', '')
    if not html:
        continue
    
    for fname, latex_raw in ocr.get(qid, {}).items():
        if not latex_raw:
            continue
        
        # Clean LaTeX
        latex = latex_raw.strip('$ \n')
        latex = re.sub(r'^```\w*\n?', '', latex)
        latex = re.sub(r'\n?```$', '', latex)
        latex = re.sub(r'\n+', ' ', latex).strip()
        if not latex:
            continue
        
        # The img tag in the HTML
        img_path = f'images/math_formulas/{qid}/{fname}'
        old_tag = f'<img src="{img_path}" class="formula-img" alt="formula" style="max-width:100%;margin:8px 0;">'
        
        if old_tag not in html:
            continue
        
        result_type = results.get(f'{qid}/{fname}', {}).get('type', 'formula')
        
        if result_type == 'formula':
            # Replace img with inline KaTeX
            html = html.replace(old_tag, f' ${latex}$ ')
            replaced_formulas += 1
        elif result_type == 'graph':
            # Keep img but add Desmos expression
            clean_desmos = latex.replace('"', "'")[:300]
            new_tag = f'<img src="{img_path}" class="formula-img-large" alt="graph" data-desmos="{clean_desmos}">'
            html = html.replace(old_tag, new_tag)
            replaced_graphs += 1
    
    q['question_html'] = html

# Save
with open(v2_file, 'w', encoding='utf-8') as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)

print(f'✅ Formulas: {replaced_formulas} img → LaTeX')
print(f'✅ Graphs:   {replaced_graphs} img → Desmos')
print(f'✅ Hints preserved: {sum(1 for q in v2 if q.get("hints"))}/202 questions')

# Verify sample
q0 = v2[0]
html0 = q0.get('question_html', '')
if '$' in html0:
    match = re.search(r'\$(.+?)\$', html0)
    if match:
        print(f'   Sample: ${match.group(1)[:80]}$')
    else:
        print(f'   Has $ but no clean match')
else:
    print(f'   No LaTeX in Q{q0["id"]}')