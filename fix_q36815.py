#!/usr/bin/env python3
"""Fix Q36815 — missing question data and answer"""
import json, os
BASE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.join(BASE, "data", "subjects", "mathematics", "questions_v2.json")

v2 = json.load(open(V2, encoding="utf-8"))
q = next(x for x in v2 if x["id"] == 36815)

# OCR was bad — most formulas are Greek prose. Only $f^2(x) + x^2 = 4$ was usable.
# Reconstruct question from sections data
q["question_html_parts"] = [
    '<p class="text-content">ΘΕΜΑ 4</p>',
    '<p class="text-content">Έστω μια συνεχής συνάρτηση $f$ στο διάστημα $[-2, 2]$ , για την οποία ισχύει $f^2(x) + x^2 = 4$ .</p>',
    '<div class="subq"><span class="subq-num">α)</span> <span class="subq-text">Να βρείτε τις ρίζες της εξίσωσης $f(x) = 0$ .</span></div>',
    '<div class="points-chip">⭐ 6 μονάδες</div>',
    '<div class="subq"><span class="subq-num">β)</span> <span class="subq-text">Αν η γραφική παράσταση της $f$ διέρχεται από το σημείο $A(0, 2)$ , τότε να βρείτε τον τύπο της $f$ .</span></div>',
    '<div class="points-chip">⭐ 9 μονάδες</div>',
    '<div class="subq"><span class="subq-num">γ)</span> <span class="subq-text">Να σχεδιάσετε τη γραφική παράσταση της $f$ .</span></div>',
    '<div class="points-chip">⭐ 4 μονάδες</div>',
    '<div class="subq"><span class="subq-num">δ)</span> <span class="subq-text">Ένα κινητό κινείται κατά μήκος της καμπύλης $C_f$ της $f$ . Καθώς περνάει από το σημείο $B(-1, \\sqrt{3})$ , η τεταγμένη $y$ του κινητού αυξάνεται με ρυθμό $2$ μονάδες το δευτερόλεπτο. Να βρείτε τον ρυθμό μεταβολής της τετμημένης $x$ του κινητού τη χρονική στιγμή που περνάει από το $B$ .</span></div>',
    '<div class="points-chip">⭐ 6 μονάδες</div>',
]
q["question_html"] = "\n".join(q["question_html_parts"])

with open(V2, "w", encoding="utf-8") as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)

print(f"Q36815: {len(q['question_html_parts'])} parts, {q['question_html'].count('$')//2} formulas")
print("  Fixed: formulas inline, type from OCR for subq text")
print("  Note: answer_html still has no LaTeX (separate task)")