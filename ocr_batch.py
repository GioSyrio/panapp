#!/usr/bin/env python3
"""
ocr_batch.py — GLM-OCR formula/graph extraction pipeline
Converts math formula images to LaTeX and graph images to Desmos-ready JSON.
Resumable — reads existing ocr_results.json and skips completed images.

Usage:
    python3 ocr_batch.py
    # Ctrl+C to stop, re-run to resume from saved progress
"""
import base64
import json
import os
import re
import time
import urllib.request

from PIL import Image

BASE_DIR = "static/images/math_formulas"
QUESTIONS_FILE = "data/subjects/mathematics/questions_v2.json"
RESULTS_FILE = "data/subjects/mathematics/ocr_results.json"
OLLAMA_URL = "http://localhost:11434/api/generate"

# Load question context for better OCR prompts
print("Loading questions...", flush=True)
with open(QUESTIONS_FILE, encoding="utf-8") as f:
    v2_data = json.load(f)
QUESTIONS = {str(q["id"]): q for q in v2_data}

# Load existing results (resume support)
results = {}
if os.path.exists(RESULTS_FILE):
    with open(RESULTS_FILE, encoding="utf-8") as f:
        results = json.load(f)
    print(f"Loaded {len(results)} existing results", flush=True)

# Find images to process
files_to_process = []
for qdir in sorted(os.listdir(BASE_DIR)):
    full_dir = os.path.join(BASE_DIR, qdir)
    if not os.path.isdir(full_dir):
        continue
    for fname in sorted(os.listdir(full_dir)):
        if not fname.endswith(".png"):
            continue
        key = f"{qdir}/{fname}"
        if key not in results:
            files_to_process.append((qdir, fname, os.path.join(full_dir, fname)))

print(f"Found {len(files_to_process)} images to process", flush=True)
if not files_to_process:
    print("All done!", flush=True)
    exit()

# Process images
for i, (qdir, fname, filepath) in enumerate(files_to_process):
    key = f"{qdir}/{fname}"

    # Get question context
    question = QUESTIONS.get(qdir, {})
    question_html = question.get("question_html", "")
    # Strip HTML tags for text context
    question_text = re.sub(r"<[^>]+>", " ", question_html)[:400]
    if not question_text.strip():
        question_text = "No question context available."

    try:
        # Determine if this is a graph or formula
        img = Image.open(filepath)
        width, height = img.size
        is_graph = width > 400 or height > 400

        # Read and encode image
        with open(filepath, "rb") as fp:
            img_b64 = base64.b64encode(fp.read()).decode()

        # Build prompt based on image type
        if is_graph:
            prompt = (
                f"Question context: {question_text[:300]}\n\n"
                "This image is a graph from a math exam. "
                "Identify the function(s) plotted, domain, and range. "
                "Return JSON with keys: functions (list of latex objects), "
                "domain [min, max], range [min, max]."
            )
            num_predict = 150
        else:
            prompt = (
                f"Question context: {question_text[:300]}\n\n"
                "Extract ONLY the LaTeX formula from this math image. "
                "Single line, no explanation, no markdown formatting."
            )
            num_predict = 60

        # Call Ollama
        payload = {
            "model": "glm-ocr:latest",
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": num_predict,
            },
        }

        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            response_data = json.loads(resp.read())
            raw_output = response_data.get("response", "")

        # Clean up output
        clean = raw_output.split("\n")[0].strip()
        clean = re.sub(r"^```\w*\n?", "", clean)
        clean = re.sub(r"\n?```$", "", clean)

        results[key] = {
            "latex": clean,
            "type": "graph" if is_graph else "formula",
            "width": width,
            "height": height,
        }

        # Progress report and save every 20 images
        if (i + 1) % 20 == 0:
            with open(RESULTS_FILE, "w", encoding="utf-8") as fw:
                json.dump(results, fw, ensure_ascii=False, indent=2)
            pct = (i + 1) / len(files_to_process) * 100
            print(f"  [{pct:.0f}%] {i+1}/{len(files_to_process)} saved", flush=True)

    except Exception as e:
        error_msg = str(e)[:100]
        results[key] = {"error": error_msg}
        print(f"  ❌ {key}: {error_msg}", flush=True)

    # Rate limit
    time.sleep(0.5)

# Final save
with open(RESULTS_FILE, "w", encoding="utf-8") as fw:
    json.dump(results, fw, ensure_ascii=False, indent=2)

ok = sum(1 for v in results.values() if "error" not in v)
errors = len(results) - ok
print(f"\n✅ Complete: {ok} success, {errors} errors, {len(results)} total", flush=True)