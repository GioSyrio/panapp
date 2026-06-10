#!/usr/bin/env python3
"""
extract_pdf_diagrams.py — Extracts vector diagrams and flowcharts from PDFs

Reads the official ministry PDFs and renders diagram pages as PNG screenshots.
Only processes questions where a diagram (διάγραμμα/διαγράμματος) is actually
PRINTED as part of the question (not where the student is asked to draw one).

Extraction strategies:
  1. Full-page screenshots for every non-empty page
  2. Embedded raster images (page.images) extracted as standalone diagram files
  3. Vector rect clusters cropped as sub-region diagram crops

Output: PNG files in static/images/exams/{question_id}/
         A mapping file static/images/exams/diagram_map.json

Usage:
    python3 extract_pdf_diagrams.py                  # process only diagram questions
    python3 extract_pdf_diagrams.py --all            # process all PDFs (legacy)
    python3 extract_pdf_diagrams.py --limit 10       # process only first 10
    python3 extract_pdf_diagrams.py --id 25938       # process single question by ID
"""

import json
import os
import sys
import argparse
import hashlib
import re
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber not installed. Run: pip3 install pdfplumber")
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "trapeza_data_1_3_218")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions_classified.json")
PDF_DIR = os.path.join(DATA_DIR, "attachments", "extracted")
IMAGES_DIR = os.path.join(BASE_DIR, "static", "images", "exams")
MAP_FILE = os.path.join(IMAGES_DIR, "diagram_map.json")

# ── Helpers ────────────────────────────────────────────────────────────────

def sanitize_filename(s):
    """Replace problematic chars for cross-platform filenames."""
    return s.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")


def hash_pdf_content(pdf_path):
    """Generate a short content hash to detect changes."""
    with open(pdf_path, "rb") as f:
        return hashlib.md5(f.read(16384)).hexdigest()[:8]


# ── Diagram-in-question detection ──────────────────────────────────────────

# Regex patterns that indicate a diagram IS PRINTED as data in the question
# (as opposed to being something the student is asked to create/draw)
GIVEN_DIAGRAM_PATTERNS = [
    # "Δίνεται το παρακάτω διάγραμμα ροής"
    r'Δίνεται\s+(ο\s+παρακάτω|το\s+παρακάτω).{0,40}(διάγραμμα|διαγράμματος)',
    # "το παρακάτω/παραπάνω/ακόλουθο διάγραμμα"
    r'(παρακάτω|παραπάνω|ακόλουθο|διπλανό).{0,30}διάγραμμα',
    # "διάγραμμα ... που ακολουθεί"
    r'διάγραμμα.{0,30}(παρακάτω|παραπάνω|ακόλουθο|που\s+ακολουθεί)',
    # "Να μετατρέψετε το παραπάνω διάγραμμα" (diagram given, just asking to convert)
    r'μετατρέψετε\s+το\s+παραπάνω\s+διάγραμμα',
    # "να μετατραπεί ... το ... διάγραμμα"
    r'(μετατραπεί|να\s+μετατραπεί).{0,40}διάγραμμα',
    # "αλγόριθμος σε μορφή διαγράμματος ροής" (the diagram IS the algorithm)
    r'αλγόριθμος\s+σε\s+μορφή\s+διαγράμματος',
    # "φαίνεται στο παρακάτω διάγραμμα"
    r'φαίνεται\s+στο\s+παρακάτω\s+διάγραμμα',
    # "ακόλουθο τμήμα διαγράμματος ροής να μετατραπεί" (given, asking to convert)
    r'ακόλουθο\s+τμήμα\s+διαγράμματος',
]

SKIP_DIAGRAM_PATTERNS = [
    # "Να κατασκευάσετε το ισοδύναμο διάγραμμα ροής" (ask to create)
    r'(κατασκευάσετε|σχεδιάσετε|σχεδιάζοντας|σχεδιάστε|να\s+κάνετε\s+το\s+διάγραμμα).{0,80}διάγραμμα',
    # "Να αποδώσετε με διάγραμμα ροής"
    r'αποδώσετε\s+με\s+διάγραμμα',
    # "ισοδύναμο διάγραμμα ροής" at end of subsection (ask to create)
    r'ισοδύναμο\s+διάγραμμα\s+ροής\s*$',
]


def question_has_given_diagram(qid):
    """
    Check if a question has a diagram that is actually PRINTED (given) in the PDF,
    not just mentioned as something the student should create.

    Scans the question text for patterns like:
      - "Δίνεται το παρακάτω διάγραμμα ροής"
      - "Να μετατρέψετε το παραπάνω διάγραμμα"
      - "αλγόριθμος σε μορφή διαγράμματος"
      - "φαίνεται στο παρακάτω διάγραμμα"

    Excludes patterns where the student is asked to CREATE one:
      - "Να κατασκευάσετε το ισοδύναμο διάγραμμα ροής"
      - "Να σχεδιάσετε το διάγραμμα"
    """
    if not os.path.exists(QUESTIONS_FILE):
        return False

    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        questions = json.load(f)

    for q in questions:
        if str(q["id"]) != str(qid):
            continue

        text = q.get("question_text", "")
        if not text:
            return False

        # Find all mentions of διάγραμμα/διαγράμματος/διάγραμμα ροής
        for m in re.finditer(r'διάγραμμα|διαγράμματος|διάγραμμα\s+ροής', text, re.IGNORECASE):
            pos = m.start()
            start = max(0, pos - 200)
            end = min(len(text), pos + 300)
            ctx = text[start:end]

            # First check if this is a "student must create" mention — skip those
            is_create = any(re.search(p, ctx, re.IGNORECASE) for p in SKIP_DIAGRAM_PATTERNS)
            if is_create:
                # But don't skip if ALSO matches a given pattern (e.g. "Δίνεται το παραπάνω διάγραμμα.
                # Να κατασκευάσετε..." — here the diagram IS given AND they ask to create another)
                is_given = any(re.search(p, ctx, re.IGNORECASE) for p in GIVEN_DIAGRAM_PATTERNS)
                if not is_given:
                    continue  # pure create ask, no diagram printed

            # Check if the diagram is given/printed
            is_given = any(re.search(p, ctx, re.IGNORECASE) for p in GIVEN_DIAGRAM_PATTERNS)
            if is_given:
                return True

        return False

    return False


def get_diagram_question_ids():
    """Return set of question IDs whose text mentions a given diagram."""
    ids = set()
    if not os.path.exists(QUESTIONS_FILE):
        return ids
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        questions = json.load(f)
    for q in questions:
        qid = str(q["id"])
        if question_has_given_diagram(qid):
            ids.add(qid)
    return ids


# ── Main extraction ────────────────────────────────────────────────────────

def extract_diagrams_from_pdf(pdf_path, output_dir, question_id):
    """
    Render each page of a PDF as a full PNG screenshot.
    Extract embedded raster images as standalone diagram files.
    If vector rects indicate diagram regions, crop and save them too.
    Returns list of dicts: [{filename, page, width, height, is_subregion, is_embedded}]
    """
    results = []
    os.makedirs(output_dir, exist_ok=True)

    safe_qid = sanitize_filename(str(question_id))

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Skip empty pages
                if len(page.chars) == 0 and len(page.rects) == 0 and len(page.images) == 0:
                    continue

                # ── Full-page screenshot ───────────────────────────────
                page_img_name = f"{safe_qid}_p{page_num + 1}.png"
                page_img_path = os.path.join(output_dir, page_img_name)

                try:
                    img = page.to_image(resolution=150)
                    img.save(page_img_path)
                    w = img.original.width
                    h = img.original.height
                    results.append({
                        "filename": page_img_name,
                        "page": page_num + 1,
                        "width": w,
                        "height": h,
                        "path": f"static/images/exams/{safe_qid}/{page_img_name}",
                    })
                    print(f"  📸 Page {page_num + 1} → {page_img_name} ({w}x{h})")
                except Exception as e:
                    print(f"  ⚠️  Page {page_num + 1} render failed: {e}")

                # ── Embedded raster images ───────────────────────────
                # Extract images embedded in the PDF (e.g. flowchart drawings)
                embedded_images = page.images
                if embedded_images:
                    for ei, emb in enumerate(embedded_images):
                        emb_name = f"{safe_qid}_p{page_num + 1}_emb{ei + 1}.png"
                        emb_path = os.path.join(output_dir, emb_name)
                        if not os.path.exists(emb_path):
                            try:
                                # Crop to image bounding box, then render
                                x0 = emb.get("x0", 0)
                                top = emb.get("top", 0)
                                x1 = emb.get("x1", emb.get("width", 0))
                                bottom = emb.get("bottom", emb.get("height", 0))
                                # Ensure nonzero area
                                if x1 - x0 > 10 and bottom - top > 10:
                                    cropped = page.within_bbox((x0, top, x1, bottom)).to_image(resolution=150)
                                    cropped.save(emb_path)
                                    cw = cropped.original.width
                                    ch = cropped.original.height
                                    results.append({
                                        "filename": emb_name,
                                        "page": page_num + 1,
                                        "width": cw,
                                        "height": ch,
                                        "is_embedded": True,
                                        "path": f"static/images/exams/{safe_qid}/{emb_name}",
                                    })
                                    print(f"  🖼️  Embedded image → {emb_name} ({cw}x{ch})")
                            except Exception as e:
                                print(f"  ⚠️  Embedded image {emb_name} failed: {e}")

                # ── Vector rect-based diagram sub-regions ────────────
                rects = page.rects
                if rects and len(rects) >= 3:
                    diagrams = _cluster_rects(rects)
                    for di, (x0, y0, x1, y1) in enumerate(diagrams):
                        diag_name = f"{safe_qid}_p{page_num + 1}_diag{di + 1}.png"
                        diag_path = os.path.join(output_dir, diag_name)
                        if not os.path.exists(diag_path):
                            try:
                                cropped = page.within_bbox((x0, y0, x1, y1)).to_image(resolution=150)
                                cropped.save(diag_path)
                                cw = cropped.original.width
                                ch = cropped.original.height
                                results.append({
                                    "filename": diag_name,
                                    "page": page_num + 1,
                                    "width": cw,
                                    "height": ch,
                                    "is_subregion": True,
                                    "path": f"static/images/exams/{safe_qid}/{diag_name}",
                                })
                                print(f"  🔍 Diagram sub-region → {diag_name} ({cw}x{ch})")
                            except Exception as e:
                                print(f"  ⚠️  Sub-region {diag_name} failed: {e}")

    except Exception as e:
        print(f"  ❌ Failed to open {os.path.basename(pdf_path)}: {e}")

    return results


def _cluster_rects(rects, gap_threshold=15):
    """
    Group nearby rectangles into diagram clusters.
    Returns list of (x0, y0, x1, y1) bounding boxes.
    """
    if not rects:
        return []

    # Sort by y position
    rects_sorted = sorted(rects, key=lambda r: (r["top"], r["x0"]))

    clusters = []
    current = None

    for r in rects_sorted:
        if not current:
            current = [r["x0"], r["top"], r["x1"], r["bottom"]]
            continue

        dist_y = abs(r["top"] - current[3])
        dist_x_overlap = max(0, max(r["x0"], current[0]) - min(r["x1"], current[1]))

        if dist_y < gap_threshold * 3 and dist_x_overlap < 200:
            # Extend current cluster
            current[0] = min(current[0], r["x0"])
            current[1] = min(current[1], r["top"])
            current[2] = max(current[2], r["x1"])
            current[3] = max(current[3], r["bottom"])
        else:
            # Finish current, start new
            w = current[2] - current[0]
            h = current[3] - current[1]
            if w > 40 and h > 40:  # Minimum size filter
                clusters.append(tuple(current))
            current = [r["x0"], r["top"], r["x1"], r["bottom"]]

    # Finish last cluster
    if current:
        w = current[2] - current[0]
        h = current[3] - current[1]
        if w > 40 and h > 40:
            clusters.append(tuple(current))

    return clusters


def build_pdf_to_question_map():
    """Map PDF filenames (like 24415.pdf) to question IDs."""
    pdf_to_qid = {}
    if os.path.exists(QUESTIONS_FILE):
        with open(QUESTIONS_FILE, encoding="utf-8") as f:
            questions = json.load(f)
        for q in questions:
            qid = str(q["id"])
            # Question PDFs are named {id}.pdf
            pdf_to_qid[f"{qid}.pdf"] = qid
    return pdf_to_qid


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Extract diagrams from ministry PDFs")
    parser.add_argument("--limit", type=int, default=0, help="Process only N PDFs")
    parser.add_argument("--id", type=int, default=0, help="Process single question by ID")
    parser.add_argument("--all", action="store_true", help="Process ALL PDFs (not just diagram questions)")
    args = parser.parse_args()

    print("🔍 PDF Diagram Extractor")
    print(f"   PDF source:  {PDF_DIR}")
    print(f"   Image output: {IMAGES_DIR}")
    print()

    os.makedirs(IMAGES_DIR, exist_ok=True)

    # Build question → PDF mapping
    pdf_to_qid = build_pdf_to_question_map()
    print(f"   Mapped {len(pdf_to_qid)} question IDs to PDF filenames.")

    # Find all PDFs
    all_pdfs = sorted(
        f for f in os.listdir(PDF_DIR)
        if f.endswith(".pdf") and not f.endswith("_SOLUTION.pdf")
    )

    # Filter by --id
    if args.id:
        target = f"{args.id}.pdf"
        if target in all_pdfs:
            all_pdfs = [target]
        else:
            print(f"  ❌ PDF for question {args.id} not found.")
            sys.exit(1)

    # Filter to diagram-only questions (unless --all or --id specified)
    if not args.all and not args.id:
        diagram_ids = get_diagram_question_ids()
        print(f"   Questions with given diagrams: {len(diagram_ids)} → {sorted(diagram_ids, key=int)}")
        all_pdfs = [f"{qid}.pdf" for qid in sorted(diagram_ids, key=int) if f"{qid}.pdf" in set(all_pdfs)]
        print(f"   Will process {len(all_pdfs)} diagram PDFs.")
    elif args.all:
        print(f"   --all mode: processing all {len(all_pdfs)} PDFs.")

    if args.limit > 0:
        all_pdfs = all_pdfs[:args.limit]

    print(f"   Processing {len(all_pdfs)} PDFs...\n")

    # Load or initialize diagram map
    diagram_map = {}
    if os.path.exists(MAP_FILE):
        with open(MAP_FILE, encoding="utf-8") as f:
            diagram_map = json.load(f)

    total_pages = 0
    total_diagrams = 0
    processed = 0

    for pdf_name in all_pdfs:
        pdf_path = os.path.join(PDF_DIR, pdf_name)
        qid = pdf_to_qid.get(pdf_name, os.path.splitext(pdf_name)[0])
        output_dir = os.path.join(IMAGES_DIR, str(qid))

        # Skip if already processed and unchanged
        pdf_hash = hash_pdf_content(pdf_path)
        if qid in diagram_map and diagram_map[qid].get("content_hash") == pdf_hash:
            processed += 1
            continue

        print(f"📄 {pdf_name} (ID: {qid})")
        results = extract_diagrams_from_pdf(pdf_path, output_dir, qid)

        if results:
            diagram_map[qid] = {
                "question_id": qid,
                "pdf": pdf_name,
                "content_hash": pdf_hash,
                "diagrams": results,
            }
            total_pages += len(set(r["page"] for r in results))
            total_diagrams += len(results)
        else:
            diagram_map.pop(qid, None)

        processed += 1

    # Save mapping
    with open(MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(diagram_map, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done! {processed} PDFs processed.")
    print(f"   Pages rendered: {total_pages}")
    print(f"   Diagram images: {total_diagrams}")
    print(f"   Map file: {MAP_FILE}")


if __name__ == "__main__":
    main()