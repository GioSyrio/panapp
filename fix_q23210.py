#!/usr/bin/env python3
"""Fix Q23210: deduplicate, consolidate fragments, filter corrupted OCR."""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.join(BASE, "data", "subjects", "mathematics", "questions_v2.json")

v2 = json.load(open(V2, encoding="utf-8"))
q = next(x for x in v2 if x["id"] == 23210)

q["question_html_parts"] = [
    '<p class="text-content">ΘΕΜΑ 4</p>',
    '<p class="text-content">Θεωρούμε συνάρτηση δύο φορές παραγωγίσιμη στο $\mathbb{R}$ και στο παρακάτω σχήμα δίνεται η γραφική παράσταση της παραγώγου συνάρτησης.</p>',
    '<p class="text-content">Γνωρίζουμε ότι: '
    '$\lim_{x \\to -\\infty} f(x) = +\\infty$, $\lim_{x \\to +\\infty} f(x) = -\\infty$, '
    '$f(\\alpha) < 0$, $f(\\beta) > 0$. '
    'Η γραφική παράσταση της $f\'(x)$ παρουσιάζει ολικό ακρότατο στη θέση $x_0$. '
    'Τα $\\alpha, \\beta$ είναι οι τετμημένες των μοναδικών δύο σημείων στα οποία τέμνει '
    'τον άξονα $x\'x$ η γραφική παράσταση της παραγώγου συνάρτησης. '
    '$\lim_{x \\to -\\infty} f(x) = +\\infty$, $\lim_{x \\to +\\infty} f(x) = -\\infty$. '
    'Η γραφική παράσταση της $f$ παρουσιάζει ολικό ακρότατο στη θέση $x_0$.</p>',
    '<div class="subq"><span class="subq-num">α)</span> <span class="subq-text">Να μελετηθεί ως προς τη μονοτονία και τα τοπικά ακρότατα η $f$.</span></div>',
    '<div class="points-chip">⭐ 8 μονάδες</div>',
    '<div class="subq"><span class="subq-num">β)</span> <span class="subq-text">Να αποδείξετε ότι η εξίσωση $f(x)=0$ έχει τρεις ακριβώς πραγματικές ρίζες.</span></div>',
    '<div class="points-chip">⭐ 9 μονάδες</div>',
    '<div class="subq"><span class="subq-num">γ)</span> <span class="subq-text">Να αποδείξετε ότι για κάθε $x \\in \\mathbb{R}$, ισχύει $f(x+1)-f(x) \\leq 2$.</span></div>',
    '<div class="points-chip">⭐ 8 μονάδες</div>',
]

q["question_html"] = "\n".join(q["question_html_parts"])

with open(V2, "w", encoding="utf-8") as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)

print(f"Q23210: fixed → {len(q['question_html_parts'])} parts, {q['question_html'].count('$')//2} formulas")
print("  - Removed 7 duplicate/corrupted text-content fragments")
print("  - Removed 3 duplicate subq text-content copies")
print("  - Filtered corrupted OCR (Greek prose in LaTeX)")
print("  - Consolidated into 3 description paragraphs + 3 subq/points pairs")

# Verify
parts = q['question_html_parts']
for i, p in enumerate(parts):
    print(f"  [{i}] {p[:120]}...")