#!/usr/bin/env python3
"""
build_sos_guidelines.py — Generate SOS cheatsheet per subject from exam answers.
v2: Refined prompts with casual language, concrete examples, part-specific strategies,
    and extra intelligence (theorems, graph tips, top tools).

Usage:
    python3 build_sos_guidelines.py --subject mathematics
    python3 build_sos_guidelines.py --subject mathematics --limit 3
"""
import json, os, sys, time, argparse, re
from collections import defaultdict, Counter
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

BASE = os.path.dirname(os.path.abspath(__file__))

SYSTEM_PROMPT = """Είσαι ένας καθηγητής Μαθηματικών που μιλάει σαν φίλος/κολλητός σε μαθητή Λυκείου.
ΟΧΙ επίσημη γλώσσα, ΟΧΙ σαν πανεπιστημιακό σύγγραμμα. Χρησιμοποίησε καθημερινά Ελληνικά,
σαν να στέλνεις μήνυμα σε φίλο που προετοιμάζεται για Πανελλαδικές.

Για το παρακάτω κεφάλαιο, ανέλυσες πραγματικές λύσεις θεμάτων και δίνεις:

1. 🔑 SOS Έννοιες (3-5): Τι εμφανίζεται ΣΧΕΔΟΝ ΠΑΝΤΑ, με μικρό παράδειγμα σε παρένθεση
   ΟΧΙ: "Η μονοτονία αποδεικνύεται με την παράγωγο"
   ΝΑΙ: "Όταν θες να δείξεις ότι η f ανεβαίνει, βρες f'(x). Aν βγει >0, τελείωσες! ✅ (π.χ. f(x)=x^3+x → f'(x)=3x^2+1>0)"

2. ⚠️ Παγίδες που ΠΟΝΑΝΕ (2-4): Τι σε κάνει να χάνεις μονάδες, με συγκεκριμένο σενάριο
   ΟΧΙ: "Παράλειψη ελέγχου πεδίου ορισμού"
   ΝΑΙ: "Αν έχεις f(x)=√(x-2) ή f(x)=1/(x-1), ΠΡΕΠΕΙ να πεις x≥2 ή x≠1. Το ξεχνάς στην αρχή; -3 μονάδες. 😭"

3. 📝 SOS Μοτίβο (1-2): Το μοτίβο που λύνει τα ΠΕΡΙΣΣΟΤΕΡΑ θέματα αυτού του κεφαλαίου
   Δώσε το σαν βήματα: "Βήμα 1: ... → Βήμα 2: ... → Βήμα 3: ..."

4. 💡 Το απόλυτο takeaway (1 πρόταση): Τι να θυμάται ο μαθητής πριν μπει στην αίθουσα

Με βάση τα δεδομένα, πες επίσης:
- Για Θέμα Β: ποια εργαλεία κυριαρχούν (π.χ. "στο 80% των Θέμα Β, το μόνο που χρειάζεται είναι παραγώγιση + μονοτονία")
- Για Θέμα Γ/Δ: ποια εργαλεία κυριαρχούν (π.χ. "στα Θέμα Γ/Δ θέλει ολοκληρωμένη μελέτη + θεώρημα")

ΣΗΜΑΝΤΙΚΟ: Χρησιμοποίησε LaTeX μέσα σε $...$ για μαθηματικά. Κάθε σημείο 1-3 προτάσεις max.
Απόφυγε λέξεις όπως "απαιτείται", "επιβάλλεται", "συνιστάται" — πες "πρέπει", "θες", "χρειάζεσαι".

ΕΠΙΣΤΡΕΨΕ ΜΟΝΟ JSON:
{
  "key_concepts": ["πρόταση 1 με παράδειγμα", ...],
  "traps": ["παγίδα 1 με σενάριο", ...],
  "patterns": ["μοτίβο 1 με βήματα", ...],
  "must_know": "η μία πρόταση",
  "thema_b_tools": "εργαλεία για Θέμα Β",
  "thema_cd_tools": "εργαλεία για Θέμα Γ/Δ"
}"""

def build_prompt(chapter_title, answers_sample, part_distribution, question_count):
    """Build the user prompt with answer samples and part statistics."""
    parts_str = ", ".join(f"{v} Θέμα {k}" for k, v in sorted(part_distribution.items()))
    return f"""ΚΕΦΑΛΑΙΟ: {chapter_title} ({question_count} θέματα)
Κατανομή: {parts_str}

Παρακάτω είναι αποσπάσματα από ΠΡΑΓΜΑΤΙΚΕΣ λύσεις θεμάτων Πανελλαδικών.
Ανέλυσέ τες και βρες τα SOS μοτίβα. Μίλα σαν φίλος, ουσιαστικά, με παραδείγματα.

ΛΥΣΕΙΣ:
{answers_sample[:4000]}

Γράψε τον Οδηγό SOS σε JSON:"""

def build_global_prompt(all_chapter_data):
    """Prompt for global intelligence pass."""
    chapters_summary = []
    for c in all_chapter_data:
        chapters_summary.append(f"{c['id']} {c['title']}: {c['question_count']} θέματα")
    chapter_list = "\n".join(chapters_summary)
    
    return f"""Ανέλυσες {len(all_chapter_data)} κεφάλαια Μαθηματικών Προσανατολισμού με συνολικά ~200 θέματα Πανελλαδικών.

Κεφάλαια:
{chapter_list}

Τώρα δώσε ΓΕΝΙΚΕΣ συμβουλές SOS με casual γλώσσα (σαν φίλος σε φίλο):

1. ⭐ Γενικές Συμβουλές (5-6): Τι να θυμάται ο μαθητής, με συγκεκριμένα tips
2. 📐 Σχέση f'/f'' με γραφική παράσταση: 3-4 σημεία για το πώς το πρόσημο της f' δείχνει μονοτονία και το πρόσημο της f'' δείχνει κυρτότητα, με μικρά παραδείγματα
3. 📖 Θεωρήματα SOS: Top 4-5 θεωρήματα που εμφανίζονται πιο συχνά στις αποδείξεις, με το ΠΟΤΕ χρησιμοποιείται το καθένα (π.χ. "Bolzano: όταν θες να δείξεις ότι υπάρχει ρίζα σε διάστημα [α,β]")
4. 🛠 Top Εργαλεία: Ποια είναι τα 5-6 πιο συχνά εργαλεία/τεχνικές που χρησιμοποιούνται στο 80% των λύσεων;

Γράψε στα Ελληνικά, casual ύφος, LaTeX σε $...$. Κάθε συμβουλή 1-3 προτάσεις.

ΕΠΙΣΤΡΕΨΕ ΜΟΝΟ JSON:
{{
  "general_tips": ["tip 1", "tip 2", ...],
  "graph_tips": ["f'/f'' tip 1", ...],
  "key_theorems": ["θεώρημα 1: πότε χρησιμοποιείται", ...],
  "top_tools": ["εργαλείο 1", ...],
  "exam_strategy": "μια παράγραφος για το πώς να προσεγγίσεις το γραπτό"
}}"""

def extract_chapter(tag):
    m = re.match(r'^([0-9]+\.[0-9]+)\s+(.+)', tag)
    if m:
        return m.group(1), m.group(2)
    return None, tag

def safe_json_parse(raw):
    """Try multiple strategies to parse LLM JSON response."""
    # Strategy 1: direct parse
    try:
        return json.loads(raw)
    except:
        pass
    # Strategy 2: extract {...}
    m = re.search(r'\{[\s\S]*\}', raw)
    if m:
        try:
            return json.loads(m.group(0))
        except:
            pass
    # Strategy 3: fix common LaTeX escaping issues
    if m:
        fixed = m.group(0)
        # Fix unescaped backslashes in JSON strings
        fixed = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', fixed)
        try:
            return json.loads(fixed)
        except:
            pass
    return {}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--subject", default="mathematics")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set"); return
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    v2_file = os.path.join(BASE, "data", "subjects", args.subject, "questions_v2.json")
    if not os.path.exists(v2_file):
        print(f"ERROR: {v2_file} not found"); return

    v2 = json.load(open(v2_file, encoding="utf-8"))

    # Group by chapter
    chapters = defaultdict(list)
    for q in v2:
        for tag in q.get("conceptual_tags", []):
            ch_num, ch_title = extract_chapter(tag)
            if ch_num:
                chapters[(ch_num, ch_title)].append(q)

    print(f"Found {len(chapters)} chapters in {args.subject} ({len(v2)} questions)")

    guidelines = {
        "subject": args.subject,
        "generated_at": time.strftime("%Y-%m-%d"),
        "chapters": [],
        "general_tips": [],
        "graph_tips": [],
        "key_theorems": [],
        "top_tools": [],
        "exam_strategy": ""
    }

    chapter_items = sorted(chapters.items())
    if args.limit > 0:
        chapter_items = chapter_items[:args.limit]

    for idx, ((ch_num, ch_title), questions) in enumerate(chapter_items):
        print(f"\n[{idx+1}/{len(chapter_items)}] {ch_num} {ch_title} ({len(questions)} questions)")

        # Get part distribution
        parts = Counter(q.get("part", "?") for q in questions)
        
        # Collect answer samples
        samples = []
        for q in questions[:12]:
            html = q.get("answer_html", "")
            plain = re.sub(r'<[^>]+>', ' ', html)[:500]
            plain = re.sub(r'\s+', ' ', plain).strip()
            if plain:
                samples.append(plain)

        if not samples:
            print("  ⚠️ No answer samples, skipping")
            continue

        prompt = build_prompt(f"{ch_num} — {ch_title}", "\n---\n".join(samples), parts, len(questions))

        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            raw = resp.choices[0].message.content or "{}"
            data = safe_json_parse(raw)

            chapter_data = {
                "id": ch_num,
                "title": ch_title,
                "question_count": len(questions),
                "key_concepts": data.get("key_concepts", []),
                "traps": data.get("traps", []),
                "patterns": data.get("patterns", []),
                "must_know": data.get("must_know", ""),
                "thema_b_tools": data.get("thema_b_tools", ""),
                "thema_cd_tools": data.get("thema_cd_tools", ""),
            }
            guidelines["chapters"].append(chapter_data)
            print(f"  ✅ {len(chapter_data['key_concepts'])} concepts, {len(chapter_data['traps'])} traps, B-tools: {bool(chapter_data['thema_b_tools'])}")

        except Exception as e:
            print(f"  ❌ Error: {e}")

        time.sleep(1)

    # ── Global intelligence pass ──────────────────────────────────────────
    print(f"\n🧠 Global intelligence pass...")
    
    global_prompt = build_global_prompt(guidelines["chapters"])
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Είσαι καθηγητής Πανελληνίων. Μίλα σαν φίλος, casual Ελληνικά, με ουσία και παραδείγματα. Δώσε μόνο JSON."},
                {"role": "user", "content": global_prompt}
            ],
            temperature=0.2, max_tokens=1200,
            response_format={"type": "json_object"}
        )
        raw = resp.choices[0].message.content or "{}"
        data = safe_json_parse(raw)
        guidelines["general_tips"] = data.get("general_tips", [])
        guidelines["graph_tips"] = data.get("graph_tips", [])
        guidelines["key_theorems"] = data.get("key_theorems", [])
        guidelines["top_tools"] = data.get("top_tools", [])
        guidelines["exam_strategy"] = data.get("exam_strategy", "")
        print(f"  ✅ {len(guidelines['general_tips'])} tips, {len(guidelines['key_theorems'])} theorems, {len(guidelines['top_tools'])} tools")
    except Exception as e:
        print(f"  ❌ Global pass error: {e}")

    # Save
    out_file = os.path.join(BASE, "data", "subjects", args.subject, "sos_guidelines.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(guidelines, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Saved: {len(guidelines['chapters'])} chapters, {len(guidelines['general_tips'])} tips → {out_file}")

if __name__ == "__main__":
    main()