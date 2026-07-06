#!/usr/bin/env python3
"""
Process 62 math questions with no OCR results.
Renders each DOCX to PNG via LibreOffice, extracts formulas via GLM-OCR.
Resumable — reads existing ocr_results.json, skips completed.

Usage: python3 ocr_missing_questions.py
"""
import json, os, base64, urllib.request, re, time, subprocess, shutil

SOFFICE = "/opt/homebrew/bin/soffice"
OLLAMA = "http://localhost:11434/api/generate"

v2 = json.load(open("data/subjects/mathematics/questions_v2.json"))
ocr = json.load(open("data/subjects/mathematics/ocr_results.json"))

missing = []
for q in v2:
    qid = str(q["id"])
    if sum(1 for k in ocr if k.startswith(qid)) == 0:
        missing.append(qid)

print(f"Found {len(missing)} questions with no OCR results\n")

done = 0
for qid in missing:
    docx = f"data/subjects/mathematics/raw/docx/{qid}-0.doc"
    if not os.path.exists(docx):
        continue

    png = f"/tmp/q{qid}.png"
    if not os.path.exists(png) or os.path.getsize(png) < 100:
        print(f"  Q{qid}: rendering...", end=" ")
        subprocess.run([SOFFICE, "--headless", "--convert-to", "png", "--outdir", "/tmp", docx],
                       capture_output=True, timeout=30)
        lo = f"/tmp/{qid}-0.png"
        if os.path.exists(lo):
            shutil.move(lo, png)
            print("ok")
        else:
            print("FAIL")
            continue
    else:
        print(f"  Q{qid}: cached")

    with open(png, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    qd = next((q for q in v2 if str(q["id"]) == qid), {})
    qt = re.sub(r"<[^>]+>", " ", qd.get("question_html", ""))[:300]

    payload = {
        "model": "glm-ocr:latest",
        "prompt": f"Question: {qt}\n\nList ALL mathematical formulas visible. Output each in LaTeX with $ delimiters.",
        "images": [b64],
        "stream": False,
        "options": {"temperature": 0, "num_predict": 400}
    }

    try:
        req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        raw = json.loads(urllib.request.urlopen(req, timeout=120).read()).get("response", "")
        
        # Extract ALL $...$ LaTeX formulas
        count = 0
        seen = set()
        for m in re.finditer(r'\$(.+?)\$', raw):
            latex = m.group(1).strip()
            # Only keep math formulas (must contain backslash or math symbol)
            if latex and len(latex) > 2 and ('\\' in latex or any(c in latex for c in '∫∑√∂∞→←⇒⇔∀∃∈∉⊂⊆∪∩≤≥≠≈')):
                latex = re.sub(r'^```\w*\n?|```$', '', latex).strip()
                if latex and latex not in seen:
                    seen.add(latex)
                    key = f"{qid}/image{count+1}.png"
                    ocr[key] = {"latex": latex, "type": "formula", "width": 0, "height": 0}
                    count += 1
        
        done += 1
        print(f"    -> {count} formulas")
        
    except Exception as e:
        print(f"    -> ERROR: {e}")

    time.sleep(0.3)

    if done % 5 == 0:
        with open("data/subjects/mathematics/ocr_results.json", "w") as f:
            json.dump(ocr, f, ensure_ascii=False, indent=2)

with open("data/subjects/mathematics/ocr_results.json", "w") as f:
    json.dump(ocr, f, ensure_ascii=False, indent=2)

ok = sum(1 for v in ocr.values() if v.get("latex", "").strip())
print(f"\nDONE: {ok} total formulas")
print("Next: python3 build_final_vml.py  ← rebuild questions with new formulas")