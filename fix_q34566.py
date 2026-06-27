#!/usr/bin/env python3
"""Fix Q34566 - proper inline formula placement"""
import json, os
BASE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.join(BASE, "data", "subjects", "mathematics", "questions_v2.json")

v2 = json.load(open(V2, encoding="utf-8"))
q = next(x for x in v2 if x["id"] == 34566)

q["question_html_parts"] = [
    '<p class="text-content">ΘΕΜΑ 4</p>',
    '<p class="text-content">Θεωρούμε την παραγωγίσιμη συνάρτηση $f$ , με $f(\\alpha) < 0$ και $f(\\beta) > 0$, για κάθε $x \\in (a, b]$ , για την οποία επιπλέον γνωρίζουμε ότι: $\\frac{G(x)-G(a)}{x-a} < f(a)$</p>',
    '<p class="text-content">Η συνάρτηση $G$ είναι συνεχής στο $[a,b]$ . $\\alpha, \\beta \\in (a,b)$ για κάθε $x$ .</p>',
    '<div class="subq"><span class="subq-num">α)</span> <span class="subq-text">Να αποδείξετε ότι υπάρχει σημείο της γραφικής παράστασης της συνάρτησης $f$ , στο οποίο η εφαπτομένη ευθεία είναι παράλληλη προς τον άξονα $x\'x$ .</span></div>',
    '<div class="points-chip">⭐ 5 μονάδες</div>',
    '<div class="subq"><span class="subq-num">β)</span> <span class="subq-text">Να αποδείξετε ότι το εμβαδόν του χωρίου που ορίζεται από την γραφική παράσταση της συνάρτησης $f$ , τις ευθείες $x=1$, $x=2$ και τον άξονα $x\'x$ , είναι $1$ τετραγωνική μονάδα.</span></div>',
    '<div class="points-chip">⭐ 7 μονάδες</div>',
    '<div class="subq"><span class="subq-num">γ)</span> <span class="subq-text">Να αποδείξτε ότι η συνάρτηση $f$ είναι γνησίως φθίνουσα στο $\\mathbb{R}$ .</span></div>',
    '<div class="points-chip">⭐ 6 μονάδες</div>',
    '<div class="subq"><span class="subq-num">δ)</span> <span class="subq-text">Έστω ότι η συνάρτηση $F$ είναι μια αρχική της $f$ στο $\\mathbb{R}$ . Να αποδείξετε ότι για κάθε $x \\in \\mathbb{R}$ ισχύει $F(x) \\leq 0$ .</span></div>',
    '<div class="points-chip">⭐ 7 μονάδες</div>',
]
q["question_html"] = "\n".join(q["question_html_parts"])

with open(V2, "w", encoding="utf-8") as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)

print(f"Q34566: {len(q['question_html_parts'])} parts, {q['question_html'].count('$')//2} formulas")