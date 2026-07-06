#!/usr/bin/env python3
"""Retry empty SOS groups for informatics — fix JSON parsing and regenerate."""
import json, os, time, re
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI

BASE = os.path.dirname(os.path.abspath(__file__))
GUIDELINES_FILE = os.path.join(BASE, "data", "subjects", "informatics", "sos_guidelines.json")
V2_FILE = os.path.join(BASE, "data", "subjects", "informatics", "questions_v2.json")

SYSTEM_PROMPT = """Είσαι ένας καθηγητής Πληροφορικής που μιλάει σαν φίλος σε μαθητή Λυκείου.
ΟΧΙ επίσημη γλώσσα. Μίλα απλά, καθημερινά, σαν να στέλνεις μήνυμα.

Για το παρακάτω θέμα, δώσε:
1. 🔑 SOS Έννοιες (3-5): Τι πρέπει οπωσδήποτε να ξέρει, με μικρό παράδειγμα
2. ⚠️ Παγίδες (2-4): Πού χάνουν μονάδες οι μαθητές, με συγκεκριμένο σενάριο
3. 📝 SOS Μοτίβο (1-2): Το μοτίβο που λύνει τα περισσότερα θέματα
4. 💡 Takeaway: Μία πρόταση να θυμάται

ΣΗΜΑΝΤΙΚΟ: Επίστρεψε ΜΟΝΟ ένα έγκυρο JSON αντικείμενο. Όχι markdown, όχι fences ```.
Χρησιμοποίησε ΔΙΠΛΑ quotes (\") για όλα τα strings. Απόφυγε χαρακτήρες που σπάνε το JSON όπως μη-escaped backslashes.

{
  "key_concepts": ["έννοια 1", "έννοια 2", ...],
  "traps": ["παγίδα 1", ...],
  "patterns": ["μοτίβο 1", ...],
  "must_know": "το takeaway"
}"""

def build_prompt(title, questions, v2_data):
    sections_samples = []
    for q in questions[:10]:
        # Use sections for informatics (no answer_html usually)
        for s in q.get("sections", []):
            if s.get("type") == "sub_question":
                sections_samples.append(f"{s.get('number','')}: {s.get('content','')[:200]}")
    
    parts = {}
    for q in questions:
        p = q.get("part", "?")
        parts[p] = parts.get(p, 0) + 1
    parts_str = ", ".join(f"{v} {k}" for k, v in sorted(parts.items()))
    
    hints_samples = []
    for q in questions[:8]:
        for h in q.get("hints", []):
            for ht in h.get("hints", [])[:2]:
                hints_samples.append(ht.get("hint_text", "")[:200])
    
    return f"""ΘΕΜΑ: {title} ({len(questions)} ερωτήσεις, {parts_str})

Εκφωνήσεις υποερωτημάτων:
{chr(10).join(sections_samples[:20])}

Υποδείξεις (hints):
{chr(10).join(hints_samples[:15])}

Γράψε τον Οδηγό SOS. ΕΠΙΣΤΡΕΨΕ ΜΟΝΟ ΕΓΚΥΡΟ JSON (χωρίς markdown):"""

def safe_parse(raw):
    """Multiple strategies to extract valid JSON."""
    # Strategy 1: direct
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and ("key_concepts" in data or "traps" in data):
            return data
    except: pass
    
    # Strategy 2: extract from markdown code blocks
    m = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', raw)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict): return data
        except: pass
    
    # Strategy 3: find first { to last }
    m = re.search(r'\{[\s\S]*\}', raw)
    if m:
        candidate = m.group(0)
        # Fix common issues
        candidate = re.sub(r'([^\\])\\([^"\\/bfnrtu])', r'\1\\\\\2', candidate)
        try:
            data = json.loads(candidate)
            if isinstance(data, dict): return data
        except: pass
    
    # Strategy 4: try to fix unescaped newlines in strings
    if m:
        candidate = m.group(0)
        candidate = candidate.replace('\n', '\\n')
        try:
            data = json.loads(candidate)
            if isinstance(data, dict): return data
        except: pass
    
    return {}

def main():
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set"); return
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    
    g = json.load(open(GUIDELINES_FILE, encoding="utf-8"))
    v2 = json.load(open(V2_FILE, encoding="utf-8"))
    
    # Find empty groups
    empty_groups = []
    for c in g["chapters"]:
        if not c.get("key_concepts") and not c.get("traps"):
            empty_groups.append(c["title"])
    
    print(f"Empty groups to retry: {len(empty_groups)}")
    
    fixed = 0
    for title in empty_groups:
        # Find matching questions
        questions = []
        for q in v2:
            if title in q.get("conceptual_tags", []):
                questions.append(q)
        
        if not questions:
            print(f"  {title}: no matching questions, skipping")
            continue
        
        prompt = build_prompt(title, questions, v2)
        
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=600,
                response_format={"type": "json_object"}
            )
            raw = resp.choices[0].message.content or "{}"
            data = safe_parse(raw)
            
            # Update the chapter
            for c in g["chapters"]:
                if c["title"] == title:
                    c["key_concepts"] = data.get("key_concepts", [])
                    c["traps"] = data.get("traps", [])
                    c["patterns"] = data.get("patterns", [])
                    c["must_know"] = data.get("must_know", "")
                    fixed += 1
                    print(f"  ✅ {title}: {len(c['key_concepts'])} concepts, {len(c['traps'])} traps")
                    break
            else:
                print(f"  ⚠️ {title}: not found in guidelines")
                
        except Exception as e:
            print(f"  ❌ {title}: {e}")
        
        time.sleep(0.8)
    
    # Retry global pass
    print(f"\n🧠 Retrying global intelligence pass...")
    chapters_summary = "\n".join(f"{c['title']}: {c['question_count']} θέματα" for c in g["chapters"][:30])
    
    global_prompt = f"""Ανέλυσες {len(g['chapters'])} ενότητες Πληροφορικής Πανελλαδικών.

Ενότητες:
{chapters_summary}

Δώσε:
1. ⭐ Γενικές Συμβουλές (5-6) για τον μαθητή
2. 🛠 Top Εργαλεία/Τεχνικές (5-6) που χρησιμοποιούνται πιο συχνά
3. 📝 Στρατηγική Εξέτασης (1 παράγραφος)

ΕΠΙΣΤΡΕΨΕ ΜΟΝΟ ΕΓΚΥΡΟ JSON (χωρίς markdown):
{{"general_tips": [...], "top_tools": [...], "exam_strategy": "..."}}"""
    
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Είσαι καθηγητής Πληροφορικής. Δώσε συμβουλές σε casual Ελληνικά. Επίστρεψε ΜΟΝΟ JSON χωρίς markdown."},
                {"role": "user", "content": global_prompt}
            ],
            temperature=0.2, max_tokens=600,
            response_format={"type": "json_object"}
        )
        raw = resp.choices[0].message.content or "{}"
        data = safe_parse(raw)
        g["general_tips"] = data.get("general_tips", [])
        g["top_tools"] = data.get("top_tools", [])
        g["exam_strategy"] = data.get("exam_strategy", "")
        print(f"  ✅ {len(g['general_tips'])} tips, {len(g['top_tools'])} tools")
    except Exception as e:
        print(f"  ❌ Global pass: {e}")
    
    # Save
    with open(GUIDELINES_FILE, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=2)
    
    final_empty = sum(1 for c in g["chapters"] if not c.get("key_concepts") and not c.get("traps"))
    print(f"\n✅ Fixed: {fixed} groups. Remaining empty: {final_empty}/{len(g['chapters'])}")
    print(f"   Tips: {len(g.get('general_tips',[]))}, Tools: {len(g.get('top_tools',[]))}, Strategy: {bool(g.get('exam_strategy',''))}")

if __name__ == "__main__":
    main()