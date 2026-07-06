#!/usr/bin/env python3
"""
fix_formulas.py — Fix formula clustering in question_html_parts (subject-aware)

For mathematics questions, formulas from DOCX embedded images are appended at
paragraph end instead of being interleaved inline. This script re-parses the
original DOCX at the run level and rewrites ONLY question_html and
question_html_parts fields — no batch data (hints, OCR, answers) is touched.

Handles:
  - text-content AND subq parts with inline formulas at the run level
  - VML-embedded images (v:imagedata r:id=...) in addition to run-level r:id
  - OCR quality filter: rejects LaTeX that contains Greek body text

Usage:
    python3 fix_formulas.py                              # fix ALL math questions
    python3 fix_formulas.py --subject mathematics --limit 5  # dry-run first 5
    python3 fix_formulas.py --subject mathematics --id 34151 # single question
"""

import json, os, re, sys, argparse, html as _html
from docx import Document

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── OCR Quality Filter ─────────────────────────────────────────────────────
# Reject OCR "latex" that is actually Greek prose text mis-classified as math
GREEK_PROSE_RE = re.compile(
    r'[α-ωΑ-Ω]{4,}|συν[άα]ρτηση|είναι|αποδείξετε|αντιστρ[έε]φεται|'
    r'για\s|και\s|στο\s|με\s|την\s|του\s|της\s|το\s|τα\s|'
    r'[α-ωΑ-Ω][άέήίόύώ]{1,3}[α-ωΑ-Ω]',  # accented Greek words
    re.IGNORECASE
)

def is_valid_formula(latex):
    """Return True if the OCR result is a real math formula, not garbled Greek text."""
    if not latex or len(latex) < 2:
        return False
    # Must contain at least one math operator or symbol
    has_math = bool(re.search(r'[\\{}^_=<>+\-*/∫∑∏√∞≈≠≤≥]|\$|frac|lim|int|sum|prod|sqrt|alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|sigma|omega|phi|psi|xi|eta|rho|tau|chi|infty|partial|nabla|mathbb|mathbf|mathrm|left|right|cdot|times|div|pm|mp|rightarrow|leftarrow|Rightarrow|Leftarrow|longrightarrow|longleftarrow|mapsto|to|in|notin|subset|subseteq|cup|cap|setminus|emptyset|forall|exists|neg|wedge|vee|oplus|ominus|otimes|circ|bullet|ldots|cdots|vdots|ddots|sim|simeq|cong|equiv|propto|perp|parallel|angle|triangle|square|diamond|bigcirc|bigtriangleup|bigtriangledown|ominus|oslash|odot|bigodot|otimes|bigotimes|oplus|bigoplus|uplus|biguplus|sqcap|sqcup|bigsqcup|wedge|bigwedge|vee|bigvee|coprod|bigcoprod|prod|bigotimes|bigoplus|biguplus|bigsqcap', latex))
    if not has_math:
        return False
    # Reject if it looks like Greek prose (more than 4 consecutive Greek letters)
    if GREEK_PROSE_RE.search(latex):
        return False
    return True

def esc(s):
    return _html.escape(s)

def load_subject_config(subject_id):
    with open(os.path.join(BASE_DIR, "subjects", f"{subject_id}.json"), encoding="utf-8") as f:
        return json.load(f)

def build_content_from_runs(para_runs_list):
    """Build HTML-safe inline content from a list of {type, value} runs."""
    content = ""
    for r in para_runs_list:
        if r["type"] == "text":
            content += esc(r["value"])
        elif r["type"] == "formula":
            content += f" ${r['value']}$ "
    return content.strip()

def extract_para_runs(doc, formula_map):
    """
    Build a map: DOCX paragraph index (counting only content paragraphs) →
    list of {type, value} runs (text or formula).
    Handles both run-level r:id and VML v:imagedata r:id.
    """
    # Map rId → clean filename
    images = {}
    for rid, rel in doc.part.rels.items():
        if "image" in str(rel.reltype).lower():
            target = rel.target_ref.split("/")[-1] if "/" in rel.target_ref else rel.target_ref
            clean = target.replace(".wmf", ".png").replace(".emf", ".png").replace("media/", "")
            images[rid] = clean

    para_runs = {}  # content_paragraph_index → [{type, value}, ...]
    content_idx = 0
    for p in doc.paragraphs:
        runs = []
        seen_rids = set()  # avoid duplicates between run-level and VML matches

        # ── 1) Scan paragraph XML for VML-embedded images ──────────────
        vml_rids = re.findall(r'<v:imagedata[^>]*r:id="(rId\d+)"', p._element.xml, re.IGNORECASE)
        for rid in vml_rids:
            if rid in seen_rids:
                continue
            seen_rids.add(rid)
            if rid in images:
                fname = images[rid]
                if fname in formula_map:
                    runs.append({"type": "formula", "value": formula_map[fname]})
                # Note: non-formula VML images = diagrams (not handled here)

        # ── 2) Scan run-level r:id ────────────────────────────────────
        for run in p.runs:
            rid_matches = re.findall(r'r:id="(rId\d+)"', run.element.xml)
            if rid_matches:
                for rid in rid_matches:
                    if rid in seen_rids:
                        continue
                    seen_rids.add(rid)
                    if rid in images:
                        fname = images[rid]
                        if fname in formula_map:
                            runs.append({"type": "formula", "value": formula_map[fname]})
            else:
                txt = run.text or ""
                runs.append({"type": "text", "value": txt})

        # ── 3) Insert VML formulas at correct text positions ──────────
        # VML images come from the paragraph XML, not runs — we need to
        # interleave them where the text has gaps (double spaces).
        # Strategy: if we have VML formulas but no run-level formula positions,
        # insert them at double-space gaps in the accumulated text.
        vml_formulas = [r for r in runs if r["type"] == "formula"]
        text_runs = [r for r in runs if r["type"] == "text"]
        if vml_formulas and not any(rid_matches for run in p.runs
                                     for rid_matches in [re.findall(r'r:id="(rId\d+)"', run.element.xml)]
                                     if rid_matches):
            # Rebuild with VML formulas inserted at text gaps
            full_text = "".join(r["value"] for r in text_runs)
            # Find double-space gaps (positions where formulas were in DOCX)
            gaps = list(re.finditer(r'\s{2,}', full_text))
            if gaps and len(gaps) >= len(vml_formulas):
                rebuilt = []
                last_end = 0
                for i, formula in enumerate(vml_formulas):
                    if i < len(gaps):
                        gap = gaps[i]
                        rebuilt.append({"type": "text", "value": full_text[last_end:gap.start()].strip() + " "})
                        rebuilt.append(formula)
                        last_end = gap.end()
                rebuilt.append({"type": "text", "value": full_text[last_end:].strip()})
                runs = rebuilt

        # ── Skip points-only and blank paragraphs ─────────────────────
        text_content = "".join(r["value"] for r in runs if r["type"] == "text").strip()
        if re.match(r'^\(?Μονάδες\s+\d+\)?', text_content):
            continue
        has_text = any(r["type"] == "text" and r["value"].strip() for r in runs)
        has_formula = any(r["type"] == "formula" for r in runs)
        if not has_text and not has_formula:
            continue
        para_runs[content_idx] = runs
        content_idx += 1

    return para_runs

def main():
    parser = argparse.ArgumentParser(description="Fix formula clustering in question_html_parts")
    parser.add_argument("--subject", default="mathematics", help="Subject ID")
    parser.add_argument("--limit", type=int, default=0, help="Process only N questions")
    parser.add_argument("--id", type=int, default=0, help="Process single question")
    parser.add_argument("--quiet", action="store_true", help="Only print summary")
    args = parser.parse_args()

    cfg = load_subject_config(args.subject)
    data_dir = os.path.join(BASE_DIR, cfg.get("data", {}).get("data_dir",
                            f"data/subjects/{args.subject}"))
    doc_dir = os.path.join(data_dir, "raw", "docx")
    v2_file = os.path.join(data_dir, "questions_v2.json")
    ocr_file = os.path.join(data_dir, "ocr_results.json")

    if not args.quiet:
        print(f"Subject: {args.subject} ({cfg['name']})")

    v2 = json.load(open(v2_file, encoding="utf-8"))
    ocr = json.load(open(ocr_file, encoding="utf-8"))

    if args.id:
        targets = [args.id]
    else:
        targets = [q["id"] for q in v2]
        if args.limit > 0:
            targets = targets[:args.limit]

    fixed_count = 0
    formula_count = 0
    total_changes = 0
    skipped = 0
    filtered_formulas = 0

    for qid in targets:
        q = next((x for x in v2 if x["id"] == qid), None)
        if not q:
            if not args.quiet: print(f"  Q{qid}: NOT FOUND")
            continue

        docx_path = os.path.join(doc_dir, f"{qid}-0.doc")
        if not os.path.exists(docx_path):
            skipped += 1
            continue

        # Load OCR formulas for this question WITH quality filter
        formula_map = {}
        for k, v in ocr.items():
            parts = k.split("/")
            if len(parts) == 2 and parts[0] == str(qid):
                latex = v.get("latex", "").strip("$ ")
                latex = re.sub(r'^```\w*\n?|```$', '', latex).strip()
                if latex and is_valid_formula(latex):
                    formula_map[parts[1]] = latex
                elif latex:
                    filtered_formulas += 1
                    if not args.quiet:
                        print(f"  Q{qid}: filtered bad OCR → '{latex[:80]}'")

        doc = Document(docx_path)
        para_runs = extract_para_runs(doc, formula_map)

        # Rewrite html_parts — content_idx tracks DOCX content paragraphs
        new_parts = []
        content_idx = 0
        old_fcount = q.get("question_html", "").count("$") // 2

        for part in q.get("question_html_parts", []):
            if 'class="text-content"' in part:
                if content_idx in para_runs:
                    content = build_content_from_runs(para_runs[content_idx])
                    if content:
                        new_parts.append(f'<p class="text-content">{content}</p>')
                else:
                    new_parts.append(part)
                content_idx += 1

            elif 'class="subq"' in part and 'subq-text' in part:
                num_m = re.search(r'<span class="subq-num">([^<]+)</span>', part)
                if num_m and content_idx in para_runs:
                    num = num_m.group(1)
                    text = build_content_from_runs(para_runs[content_idx])
                    prefix = num.rstrip(')') + ')'
                    if text.startswith(prefix):
                        text = text[len(prefix):].strip()
                    new_parts.append(
                        f'<div class="subq"><span class="subq-num">{num}</span> '
                        f'<span class="subq-text">{text}</span></div>')
                else:
                    new_parts.append(part)
                content_idx += 1

            elif 'class="sec-header"' in part:
                new_parts.append(part)
                content_idx += 1

            elif 'class="points-chip"' in part:
                new_parts.append(part)
                # Points paragraphs are separate DOCX paragraphs
                # — they don't count as content paragraphs

            else:
                new_parts.append(part)

        new_html = "\n".join(new_parts)
        new_fcount = new_html.count("$") // 2

        q["question_html"] = new_html
        q["question_html_parts"] = new_parts
        fixed_count += 1
        formula_count += new_fcount

        if new_fcount != old_fcount and not args.quiet:
            print(f"  Q{qid}: {old_fcount} → {new_fcount} formulas (reordered)")
            total_changes += 1

        doc._part._blob = None

    # Save
    with open(v2_file, "w", encoding="utf-8") as f:
        json.dump(v2, f, ensure_ascii=False, indent=2)

    if filtered_formulas:
        print(f"\n  ⚠️  Filtered {filtered_formulas} bad OCR entries (Greek prose as LaTeX)")

    print(f"\nDone. Fixed: {fixed_count}, Skipped: {skipped}, "
          f"Changes: {total_changes}, Total formulas: {formula_count}")

if __name__ == "__main__":
    main()