#!/usr/bin/env python3
"""
rebuild_questions.py — Rebuild math questions_v2.json with:
1. Formulas placed inline at their correct paragraph position
2. No duplication — each formula appears once
3. Original OCR results + hints preserved

Approach: Parse each paragraph, insert formula placeholder at image position,
then map OCR results to the correct formula image.
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

def rebuild_question_html(qid, ocr_results):
    """Rebuild question HTML from DOCX, keeping formulas at correct paragraph positions."""
    docx_path = os.path.join(DOC_DIR, f"{qid}-0.doc")
    if not os.path.exists(docx_path):
        return None
    
    doc = Document(docx_path)
    
    # First pass: collect OCR LaTeX for images in this question
    image_latex = {}
    for key, val in ocr_results.items():
        parts = key.split('/')
        if len(parts) == 2 and parts[0] == str(qid):
            latex = val.get('latex', '').strip()
            if latex:
                # Clean up
                latex = latex.strip('$ ')
                latex = re.sub(r'^```\w*\n?', '', latex)
                latex = re.sub(r'```$', '', latex)
                latex = latex.strip()
                if latex:
                    image_latex[parts[1]] = latex
    
    # Second pass: build HTML sections from paragraphs
    html_parts = []
    current_subq = None
    current_text = ""
    image_counter = 0
    used_images = set()  # Track which formula images we've already placed
    
    for i, p in enumerate(doc.paragraphs):
        text = p.text.strip()
        xml = p._element.xml
        has_image = '<wp:inline' in xml or '<w:drawing' in xml or '<v:imagedata' in xml
        
        if not text and not has_image:
            continue
        
        # Section header (ΘΕΜΑ)
        m = re.match(r'^ΘΕΜΑ\s+([Α-Δ])', text)
        if m:
            if current_text:
                html_parts.append(f'<p class="text-content">{e(current_text)}</p>')
                current_text = ""
            html_parts.append(f'<div class="sec-header">{e(text)}</div>')
            continue
        
        # Sub-question marker
        m = re.match(r'^([α-ωΑ-Ω])\)\s*(.*)', text)
        if m:
            if current_text:
                html_parts.append(f'<p class="text-content">{e(current_text)}</p>')
                current_text = ""
            subq_num = m.group(1) + ")"
            subq_content = m.group(2)
            html_parts.append(f'<div class="subq"><span class="subq-num">{e(subq_num)}</span> <span class="subq-text">{e(subq_content)}</span></div>')
            continue
        
        # Points
        m = re.match(r'Μονάδες\s+(\d+)', text)
        if m:
            if current_text:
                html_parts.append(f'<p class="text-content">{e(current_text)}</p>')
                current_text = ""
            html_parts.append(f'<div class="points-chip">⭐ {m.group(1)} μονάδες</div>')
            continue
        
        # Handle paragraph with images and text
        if has_image:
            # Check if this paragraph has an image that matches one of our OCR'd formulas
            # DOCX images are numbered incrementally within the question
            # We need to map the image file to this paragraph position
            
            # Build text with formula placeholders
            # The paragraph text is the visible text; the image is embedded alongside it
            paragraph_text = text
            
            # Try to find a matching OCR image that hasn't been used yet
            # Images in DOCX are ordered; we assign them sequentially
            if image_counter < len(doc.inline_shapes):
                # Get available images sorted numerically
                available = sorted([k for k in image_latex if k not in used_images], 
                                  key=lambda x: int(re.search(r'(\d+)', x).group(1)) if re.search(r'(\d+)', x) else 999)
                if available:
                    # Assign the next unused image
                    img_key = available[0]
                    latex = image_latex[img_key]
                    used_images.add(img_key)
                    
                    # Insert the formula into the text
                    # The image appears between text segments in the original
                    if paragraph_text:
                        current_text += f" {paragraph_text} ${latex}$ "
                    else:
                        current_text += f" ${latex}$ "
                else:
                    current_text += f" {paragraph_text} "
            else:
                current_text += f" {paragraph_text} "
        else:
            # Regular text paragraph — just append
            if current_text:
                current_text += " " + text
            else:
                current_text = text
    
    # Add remaining text
    if current_text:
        html_parts.append(f'<p class="text-content">{e(current_text)}</p>')
    
    return '\n'.join(html_parts)

def main():
    ocr_results = json.load(open(OCR_FILE, encoding='utf-8'))
    v2 = json.load(open(V2_FILE, encoding='utf-8'))
    
    rebuilt = 0
    errors = 0
    
    for q in v2:
        qid = q['id']
        new_html = rebuild_question_html(qid, ocr_results)
        
        if new_html:
            # Preserve existing data
            q['question_html'] = new_html
            rebuilt += 1
        else:
            errors += 1
    
    # Save
    with open(V2_FILE, 'w', encoding='utf-8') as f:
        json.dump(v2, f, ensure_ascii=False, indent=2)
    
    print(f'✅ Rebuilt {rebuilt} questions, {errors} errors')
    print(f'✅ Hints preserved: {sum(1 for q in v2 if q.get("hints"))}/{len(v2)}')

if __name__ == '__main__':
    main()