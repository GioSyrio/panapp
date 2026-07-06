#!/usr/bin/env python3
"""
Targeted fix for question 34151 (math): inline formula placement + diagram extraction.
Parses DOCX at the run level to interleave text and formulas at correct positions.
Touches ONLY question 34151 in questions_v2.json — no batch data altered.
"""
import json, os, re
from docx import Document
import html as _html

BASE = os.path.dirname(os.path.abspath(__file__))
V2_FILE = os.path.join(BASE, "data", "subjects", "mathematics", "questions_v2.json")
OCR_FILE = os.path.join(BASE, "data", "subjects", "mathematics", "ocr_results.json")
DOC_DIR = os.path.join(BASE, "data", "subjects", "mathematics", "raw", "docx")
IMG_DIR = os.path.join(BASE, "static", "images", "math_diagrams")

QID = 34151

def esc(s):
    return _html.escape(s)

# Load OCR formulas: image filename → LaTeX
ocr = json.load(open(OCR_FILE, encoding="utf-8"))
formulas = {}
for k, v in ocr.items():
    parts = k.split("/")
    if len(parts) == 2 and parts[0] == str(QID):
        latex = v.get("latex", "").strip("$ ")
        latex = re.sub(r'^```\w*\n?|```$', '', latex).strip()
        if latex:
            formulas[parts[1]] = latex
print(f"Found {len(formulas)} OCR formulas for Q{QID}")

# Load v2
v2 = json.load(open(V2_FILE, encoding="utf-8"))
q = next((x for x in v2 if x["id"] == QID), None)
if not q:
    print(f"Question {QID} not found in v2")
    exit(1)

# Load DOCX
docx_path = os.path.join(DOC_DIR, f"{QID}-0.doc")
if not os.path.exists(docx_path):
    print(f"DOCX not found: {docx_path}")
    exit(1)
doc = Document(docx_path)

# Map relationship rId → clean filename
images = {}
for rid, rel in doc.part.rels.items():
    if "image" in str(rel.reltype).lower():
        target = rel.target_ref.split("/")[-1] if "/" in rel.target_ref else rel.target_ref
        clean = target.replace(".wmf", ".png").replace(".emf", ".png").replace("media/", "")
        images[rid] = clean

diagram_images = []
diagram_rids = set()  # rIds that are diagrams (large images with no OCR)

# First pass: identify which rIds have OCR formulas
ocr_rids = set()
for rid in images:
    fname = images[rid]
    if fname in formulas:
        ocr_rids.add(rid)

# Parse paragraphs at RUN level
html_parts = []
for p in doc.paragraphs:
    # Collect interleaved text runs and image runs
    runs_content = []
    try:
        for run in p.runs:
            # Check if this run contains an image
            rid_in_text = re.findall(r'r:id="(rId\d+)"', run.element.xml)
            if rid_in_text:
                for rid in rid_in_text:
                    if rid in images:
                        fname = images[rid]
                        if fname in formulas:
                            runs_content.append({"type": "formula", "value": formulas[fname]})
                        else:
                            if rid not in diagram_rids:
                                diagram_images.append(fname)
                                diagram_rids.add(rid)
                            runs_content.append({"type": "diagram", "value": fname})
            else:
                txt = run.text or ""
                runs_content.append({"type": "text", "value": txt})
    except Exception as ex:
        # Fallback: use paragraph text directly
        runs_content = [{"type": "text", "value": p.text or ""}]
        print(f"  ⚠️ Run parsing fallback for para: {p.text[:60]}")

    # Also try: check for inline shapes in paragraph XML
    xml = p._element.xml
    shapes = re.findall(r'<v:imagedata[^>]*r:id="(rId\d+)"', xml)
    shapes += re.findall(r'<v:imagedata[^>]*r:id="(rId\d+)"', xml, re.IGNORECASE)

    # If we got shape rIds but runs didn't capture them, reconstruct
    if shapes and not any(r["type"] in ("formula", "diagram") for r in runs_content):
        # Get plain text and insert formulas where shapes appear
        # For now, try alternate detection
        pass

    # Build paragraph content from interleaved runs
    content = ""
    for item in runs_content:
        if item["type"] == "text":
            content += esc(item["value"])
        elif item["type"] == "formula":
            content += f" ${item['value']}$ "
        elif item["type"] == "diagram":
            pass  # handled separately

    content = content.strip()
    if not content:
        continue

    # Structure detection
    if re.match(r'^ΘΕΜΑ\s+[Α-Δ]', content):
        html_parts.append(f'<div class="sec-header">{content}</div>')
    elif re.match(r'^[α-ωΑ-Ω]\)\s', content):
        m = re.match(r'^([α-ωΑ-Ω])\)\s*(.*)', content)
        html_parts.append(f'<div class="subq"><span class="subq-num">{m.group(1)})</span> <span class="subq-text">{m.group(2)}</span></div>')
    elif re.match(r'\(?Μονάδες\s+\d+\)?', content):
        m = re.match(r'\(?Μονάδες\s+(\d+)\)?', content)
        html_parts.append(f'<div class="points-chip">⭐ {m.group(1)} μονάδες</div>')
    else:
        html_parts.append(f'<p class="text-content">{content}</p>')

    if diagram_images:
        # Only flag paragraph 2 (empty text + images) as diagram container
        pass

print(f"Parsed {len(html_parts)} HTML parts from DOCX")
print(f"Diagram images found: {len(diagram_images)}")

# Extract and save diagram images
diagram_url = None
if diagram_images:
    os.makedirs(os.path.join(IMG_DIR, str(QID)), exist_ok=True)
    saved = []
    for fname in diagram_images:
        for rid in images:
            if images[rid] == fname:
                try:
                    blob = doc.part.rels[rid].target_part.blob
                    out_path = os.path.join(IMG_DIR, str(QID), fname)
                    with open(out_path, "wb") as f:
                        f.write(blob)
                    saved.append(f"static/images/math_diagrams/{QID}/{fname}")
                    print(f"  📸 Extracted diagram: {out_path}")
                except Exception as ex:
                    print(f"  ⚠️ Failed to extract {fname}: {ex}")
                break
    if saved:
        diagram_url = saved[0]
        html_parts.append(f'<div class="diagram-section"><div class="diagram-label">📊 Σχήμα / Διάγραμμα:</div><img src="/{diagram_url}" alt="Διάγραμμα Εξέτασης" class="question-diagram"></div>')

# Update ONLY question 34151
q["question_html"] = "\n".join(html_parts)
q["question_html_parts"] = html_parts
if diagram_url:
    q["diagram_url"] = diagram_url

# Show the fixed HTML
print("\n=== FIXED question_html ===")
print(q["question_html"][:600])
print("...")

# Save
with open(V2_FILE, "w", encoding="utf-8") as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)

print(f"\n✅ Fixed Q{QID}")
print(f"   HTML parts: {len(html_parts)}")
print(f"   Diagrams extracted: {len(diagram_images)}")
fcount = q["question_html"].count("$") // 2
print(f"   Inline formulas: {fcount}")