#!/usr/bin/env python3
"""
Build structured questions JSON from trapeza data and extracted PDFs.
Outputs the format: [{year, part, points, conceptual_tags, question_text, ...}, ...]
"""

import json
import os
import re
import pypdfium2
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "trapeza_data_1_3_218")
PDF_DIR = os.path.join(DATA_DIR, "attachments", "extracted")

# Question number → part name (as shown on the page)
QUESTION_TO_PART = {
    2: "Θέμα 2",
    4: "Θέμα 4",
}

# Standard points per question type (total)
PART_POINTS = {
    "Θέμα Γ": 15,
    "Θέμα Δ": 20,
}

def extract_pdf_text(filename):
    """Extract text from a PDF file using pypdfium2 (handles Greek fonts)."""
    path = os.path.join(PDF_DIR, filename)
    if not os.path.exists(path):
        return ""
    try:
        pdf = pypdfium2.PdfDocument(path)
        text = ""
        for page in pdf:
            textpage = page.get_textpage()
            text += textpage.get_text_range() + "\n"
        pdf.close()
        return text.strip()
    except Exception as e:
        print(f"  WARNING: Could not read {filename}: {e}")
        return ""

def extract_sub_questions(text):
    """Split PDF text into sub-questions (e.g., 2.1, 2.2, 4.1, 4.2...)."""
    # Pattern: "2.1." or "4.1." at start of sub-question
    parts = re.split(r'\n(?=\d+\.\d+\.\s)', text)
    if len(parts) < 2:
        # Try alternative: "Γ1." or "Δ1."
        parts = re.split(r'\n(?=[ΓΔ]\d+\.)', text)
    return parts

def extract_points(text):
    """Extract total points from the text."""
    points = re.findall(r'Μονάδες\s*(\d+)', text)
    return sum(int(p) for p in points)

def derive_conceptual_tags(materials):
    """Derive conceptual tags from the material/module names."""
    tags = set()
    for m in materials:
        name = m.get("name", "")
        # Remove numbering prefix like "2.4.1 " or "7.5 "
        cleaned = re.sub(r'^\d+\.\d+(\.\d+)?\s*', '', name).strip()
        if cleaned and cleaned != "ΑΕΠΠ:":
            tags.add(cleaned)
    return sorted(tags)

def extract_year(date_str):
    """Extract year from date string like '2022-10-11'."""
    if date_str:
        return int(date_str[:4])
    return None

def fix_greek_encoding(text):
    """
    Fix common Greek font encoding issues from PDFs with custom fonts.
    Some PDFs map Greek glyphs to wrong Unicode codepoints.
    """

    # ── Character-level fixes ──────────────────────────────────────────
    char_fixes = {
        '\uf021': '←',
        '\uf0df': '•',
        '\uf0b7': '•',
        '\u2018': "'",
        '\u2019': "'",
        '\u201c': '"',
        '\u201d': '"',
        '\u00a0': ' ',
        '\u00ad': '',
        '\u200b': '',
    }
    for bad, good in char_fixes.items():
        text = text.replace(bad, good)

    # Fix final sigma (ς) used mid-word → medial sigma (σ)
    result = []
    for i, c in enumerate(text):
        if c == '\u03c2':  # ς
            next_char = text[i+1] if i+1 < len(text) else ''
            if next_char and (0x0370 <= ord(next_char) <= 0x03FF or
                             0x1F00 <= ord(next_char) <= 0x1FFF):
                result.append('\u03c3')  # σ
            else:
                result.append(c)
        else:
            result.append(c)
    text = ''.join(result)

    # Remove remaining Private Use Area characters
    cleaned = []
    for c in text:
        if 0xE000 <= ord(c) <= 0xF8FF:
            cleaned.append(' ')
        else:
            cleaned.append(c)
    text = ''.join(cleaned)

    # ── Word-level fixes for PDF font encoding corruption ──────────────
    # 26 of 155 PDFs have custom font glyph-to-Unicode mappings that render
    # incorrect Greek characters. We use extensive word-level fixes.
    word_fixes = {
        # Sigma fixes (ς→σ mid-word already done above)
        ' κάκε ': ' κάθε ', ' κάκα ': ' κάθε ', '\nκάκε ': '\nκάθε ',
        ' Δφο ': ' Δύο ',
        ' ςτοιχείο ': ' στοιχείο ', ' ςτοιχεία ': ' στοιχεία ',
        'αντιςτοιχίςετε': 'αντιστοιχίσετε', 'αντιςτοιχίζει': 'αντιστοιχίζει',
        ' περιςςεφουν ': ' περισσεύουν ',
        ' γλϊςςα ': ' γλώσσα ',
        ' εκτελζςιμο ': ' εκτελέσιμο ', ' εκτελζςθ ': ' εκτελέση ',
        ' εκτελζσ ': ' εκτελέσ ', ' εκτελζσει ': ' εκτελέσει ',
        ' αμζςωσ ': ' αμέσως ', ' αμζςθ ': ' αμέση ',
        ' ιςοδφναμθ ': ' ισοδύναμη ',
        ' ιςοδυναμο ': ' ισοδύναμο ',
        ' τθ δομι ': ' τη δομή ', ' τθσ δομισ ': ' της δομής ',
    }
    for bad, good in word_fixes.items():
        text = text.replace(bad, good)

    return text


def clean_text(text):
    """Clean up extracted text."""
    # Fix Greek PDF encoding issues
    text = fix_greek_encoding(text)

    # Normalize whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    text = text.strip()
    return text

def main():
    print("=" * 60)
    print("Building structured questions JSON")
    print("=" * 60)

    # Load data
    with open(os.path.join(DATA_DIR, "data.json"), encoding="utf-8") as f:
        data = json.load(f)

    # Load raw items for cross-referencing
    with open(os.path.join(DATA_DIR, "items_raw.json"), encoding="utf-8") as f:
        raw_data = json.load(f)

    # Build item ID → raw item lookup
    raw_items = {item["id"]: item for item in raw_data["items"]}

    questions = []
    not_found = []

    for item in data["items"]:
        item_id = item["id"]
        q_num = item["question"]  # 2 or 4
        part = QUESTION_TO_PART.get(q_num, f"Θέμα {q_num}")

        # Find the PDF file for this item
        pdf_filename = f"{item_id}.pdf"
        pdf_text = extract_pdf_text(pdf_filename)

        if not pdf_text:
            not_found.append(item_id)
            continue

        # Extract answer text from solution PDF
        solution_filename = f"{item_id}_SOLUTION.pdf"
        answer_text = extract_pdf_text(solution_filename)
        if not answer_text:
            # Try alternative naming
            solution_filename = f"{item_id}_SOLUTION.pdf"
            answer_text = extract_pdf_text(solution_filename)

        # Extract year from date
        year = extract_year(item.get("date"))

        # Extract points from PDF text
        total_points = extract_points(pdf_text)

        # If no points found in text, use standard values
        if total_points == 0:
            total_points = PART_POINTS.get(part, 0)

        # Derive conceptual tags from API material data
        raw_item = raw_items.get(item_id, {})
        materials = raw_item.get("material", [])
        conceptual_tags = derive_conceptual_tags(materials)

        # Clean the question text
        question_text = clean_text(pdf_text)

        # Clean the answer text
        if answer_text:
            answer_text = clean_text(answer_text)

        # Build the entry
        entry = {
            "id": item_id,
            "year": year,
            "part": part,
            "points": total_points,
            "conceptual_tags": conceptual_tags,
            "question_text": question_text,
            "answer_text": answer_text or "",
            "materials": [m.get("name", "") for m in materials],
            "date": item.get("date"),
            "resources": item.get("resources", []),
        }
        questions.append(entry)

    # Sort by year (newest first), then by part, then by id
    questions.sort(key=lambda q: (
        -(q["year"] or 0),
        q["part"],
        q["id"]
    ))

    # Calculate stats
    years = sorted(set(q["year"] for q in questions if q["year"]))
    parts_count = {}
    for q in questions:
        parts_count[q["part"]] = parts_count.get(q["part"], 0) + 1

    print(f"\n  Extracted {len(questions)} questions from PDFs")
    if not_found:
        print(f"  Missing PDFs for {len(not_found)} items: {not_found[:5]}...")
    print(f"  Years: {years}")
    print(f"  Parts: {dict(parts_count)}")

    # Sample first 2 entries
    for q in questions[:2]:
        print(f"\n  Sample: {q['part']} ({q['year']}) - {q['points']} pts")
        print(f"  Tags: {q['conceptual_tags'][:5]}...")
        print(f"  Text preview: {q['question_text'][:200]}...")

    # Save output
    output_path = os.path.join(DATA_DIR, "questions.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    print(f"\n  Saved {len(questions)} questions to {output_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()