#!/usr/bin/env python3
"""
fill_math_gaps.py — Fill missing formulas in sub-questions using DOCX gap detection

Reads DOCX files from raw.zip and inserts OCR formulas at double-space gap
positions in sub-question text.

Touches ONLY question_html_parts (text-content + subq-text spans).
All hints, answers, sections preserved.

Usage:
    python3 fill_math_gaps.py
    python3 fill_math_gaps.py --limit 5
    python3 fill_math_gaps.py --id 23209
"""

import json, os, re, argparse, html as _html, io, zipfile
from docx import Document

BASE = os.path.dirname(os.path.abspath(__file__))
SLUG = "mathimatika_prosanatolismoy"
V2 = os.path.join(BASE, "data", "subjects", SLUG, "questions_v2.json")
OCR = os.path.join(BASE, "data", "subjects", "mathematics", "ocr_results.json")
ZIP_PATH = os.path.join(BASE, "data", "subjects", "mathematics", "raw.zip")

GREEK_PROSE_RE = re.compile(
    r'συν[άα]ρτηση|είναι|αποδείξετε|αντιστρ[έε]φεται|'
    r'προσδιορίσετε|γνησίως|συνεχής|παραγωγίσιμη|[α-ω]{4,}', re.IGNORECASE)

def is_valid_ocr(latex):
    if not latex or len(latex) < 2: return False
    if GREEK_PROSE_RE.search(latex): return False
    return True

def read_docx_from_zip(qid):
    """Read question DOCX from ZIP. Returns paragraph text lines or None."""
    if not os.path.exists(ZIP_PATH):
        return None
    fname = f"docx/{qid}-0.doc"
    try:
        with zipfile.ZipFile(ZIP_PATH) as zf:
            if fname not in zf.namelist():
                return None
            with zf.open(fname) as f:
                doc = Document(io.BytesIO(f.read()))
                return [p.text.strip() for p in doc.paragraphs
                        if p.text.strip() and not re.match(r'\(?Μονάδες\s+', p.text.strip())]
    except:
        return None

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--id", type=int, default=0)
    a = p.parse_args()

    v2 = json.load(open(V2, encoding="utf-8"))
    ocr = json.load(open(OCR, encoding="utf-8"))

    if a.id:
        targets = [q for q in v2 if q["id"] == a.id]
    else:
        targets = v2[:a.limit] if a.limit else v2

    fixed = 0
    formulas_added = 0

    for q in targets:
        qid = q["id"]
        formulas = {}
        for k, v in ocr.items():
            if k.startswith(f"{qid}/"):
                latex = v.get("latex", "").strip("$ ")
                latex = re.sub(r'^```\w*\n?|```$', '', latex).strip()
                if is_valid_ocr(latex):
                    formulas[k.split("/")[1]] = latex

        if not formulas:
            continue

        parts = q.get("question_html_parts", [])
        new_parts = list(parts)
        changed = False
        doc_paras = read_docx_from_zip(qid)
        if not doc_paras:
            continue

        for i, part in enumerate(new_parts):
            if 'class="subq"' not in part:
                continue
            m = re.search(r'class="subq-text">([^<]*)</span>', part)
            if not m:
                continue
            text = m.group(1).strip()
            gaps = list(re.finditer(r'\s{2,}', text))
            if len(gaps) < 2:
                continue

            # Match DOCX paragraph by stripping subq prefix
            for dp in doc_paras:
                dp_clean = re.sub(r'^[α-ωΑ-Ω]\)\s*', '', dp).strip()
                if dp_clean[:20] != text[:20]:
                    continue

                formula_list = list(formulas.values())
                new_text = ""
                last_end = 0
                for gi, gap in enumerate(gaps):
                    if gi < len(formula_list):
                        new_text += text[last_end:gap.start()].strip() + " "
                        new_text += f"${formula_list[gi]}$ "
                        last_end = gap.end()
                new_text += text[last_end:].strip()
                new_parts[i] = part.replace(text, new_text)
                formulas_added += min(len(gaps), len(formula_list))
                changed = True
                break

        if changed:
            q["question_html_parts"] = new_parts
            q["question_html"] = "\n".join(new_parts)
            fixed += 1
            old_f = "\n".join(parts).count("$")
            new_f = "\n".join(new_parts).count("$")
            print(f"  Q{qid}: {old_f//2} → {new_f//2} formulas (+{(new_f-old_f)//2})")

    if fixed:
        with open(V2, "w", encoding="utf-8") as f:
            json.dump(v2, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Fixed {fixed} questions, added {formulas_added} formulas")

if __name__ == "__main__":
    main()