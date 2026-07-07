#!/usr/bin/env python3
"""
build_sos_guidelines.py — Generate SOS cheatsheet.

v5: Two strategies:
  - Per-chapter (numbered chapters, ≤20 groups): mathematics prosanatolismou, informatics
  - Monolithic (granular tags, >20 groups): ALL answers → LLM once → merge (math genikis, biology, chemistry, economics)

Usage:
    python3 build_sos_guidelines.py --subject mathimatika
    python3 build_sos_guidelines.py --subject oikonomia
"""
import json, os, sys, time, argparse, re
from collections import defaultdict, Counter
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

BASE = os.path.dirname(os.path.abspath(__file__))

SYSTEM_PROMPT_MATH = """Είσαι φίλος-προπονητής Πανελληνίων που μιλάει σαν κολλητός.
Ανέλυσες πραγματικές λύσεις. Δώσε:
1. 🔑 SOS Έννοιες (3-5): Τι εμφανίζεται ΣΧΕΔΟΝ ΠΑΝΤΑ + LaTeX σε $...$
2. ⚠️ Παγίδες που ΠΟΝΑΝΕ (2-4): Συγκεκριμένο σενάριο
3. 📝 SOS Μοτίβο (1-2): Βήμα-βήμα
4. 💡 must_know (1 πρόταση)
Casual Ελληνικά. ΜΟΝΟ JSON: {{"key_concepts": [...], "traps": [...], "patterns": [...], "must_know": "...", "thema_b_tools": "...", "thema_cd_tools": "..."}}"""

SYSTEM_PROMPT_PHYSICS = """Είσαι φίλος-προπονητής Πανελληνίων. Casual Ελληνικά.
Δώσε: 1. 🔑 SOS Έννοιες (3-5) 2. ⚠️ Παγίδες (2-4) 3. 📝 Μοτίβο (1-2) 4. 💡 must_know
ΜΟΝΟ JSON: {{"key_concepts": [...], "traps": [...], "patterns": [...], "must_know": "...", "thema_b_tools": "...", "thema_cd_tools": "..."}}"""

def extract_chapter(tag):
    m = re.match(r'^([0-9]+\.[0-9]+)\s+(.+)', tag)
    if m: return m.group(1), m.group(2)
    return None, tag

def safe_json_parse(raw):
    for s in [lambda: json.loads(raw),
              lambda: json.loads(re.search(r'\{[\s\S]*\}', raw).group(0)) if re.search(r'\{[\s\S]*\}', raw) else {},
              lambda: json.loads(re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', re.search(r'\{[\s\S]*\}', raw).group(0))) if re.search(r'\{[\s\S]*\}', raw) else {}]:
        try: return s()
        except: pass
    return {}

def monolithic_sos(client, v2, subject_name, is_math):
    """Build SOS in one LLM pass — for subjects with granular tags."""
    total = len(v2)
    print("\n🧠 Monolithic SOS — sending all " + str(total) + " answers to LLM...")
    
    # Group by tag, collect answer samples
    tag_samples = defaultdict(list)
    tag_parts = defaultdict(Counter)
    for q in v2:
        tags = q.get("conceptual_tags", [])
        tag = tags[0].strip().lower() if tags else "άγνωστο"
        html = q.get("answer_html", "")
        plain = re.sub(r'<[^>]+>', ' ', html)
        plain = re.sub(r'\s+', ' ', plain).strip()
        if plain and len(plain) > 50:
            tag_samples[tag].append(plain[:800])
        tag_parts[tag][q.get("part", "?")] += 1
    
    # Sort by question count, pick top 15
    ranked = sorted(tag_samples.items(), key=lambda x: -len(x[1]))
    top_tags = ranked[:15]
    
    # Build sections with proper newline separator
    NL = chr(10)
    DNL = NL + NL  # double newline 
    sections = []
    for tag, samples in top_tags:
        parts_str = ", ".join(f"{v} Θέμα {k}" for k, v in sorted(tag_parts[tag].items()))
        sample_text = "\n---\n".join(samples[:5])
        sections.append("ΕΝΟΤΗΤΑ: " + tag + " (" + str(len(samples)) + " θέματα) — " + parts_str + "\nΑΠΟΣΠΑΣΜΑΤΑ ΛΥΣΕΩΝ:\n" + sample_text[:3000])
    
    latex_hint = "Χρησιμοποίησε LaTeX $...$ για μαθηματικά." if is_math else "ΟΧΙ LaTeX."
    
    prompt = (f"Θέμα: {subject_name}. Ανέλυσες {total} πραγματικές λύσεις Πανελληνίων.\n\n"
              f"Παρακάτω είναι οι {len(top_tags)} πιο συχνές ενότητες με αποσπάσματα λύσεων.\n\n"
              f"ΓΙΑ ΚΑΘΕ ΕΝΟΤΗΤΑ, δώσε SOS: 3-5 key_concepts, 2-4 traps, 1-2 patterns, 1 must_know. "
              f"Μετά ΔΩΣΕ 5-6 general_tips, 5-6 top_tools, exam_strategy.\n\n"
              f"{latex_hint}\n\n"
              f"{DNL.join(sections)}\n\n"
              f"ΕΠΙΣΤΡΕΨΕ ΜΟΝΟ JSON με ΠΕΔΙΑ: "
              f'{{"chapters": [{{"title": "...", "question_count": N, '
              f'"key_concepts": ["...",], "traps": ["...",], "patterns": ["...",], '
              f'"must_know": "...", "thema_b_tools": "...", "thema_cd_tools": "..."}}, ...], '
              f'"general_tips": ["...",], "top_tools": ["...",], "exam_strategy": "..."}}')

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_MATH if is_math else SYSTEM_PROMPT_PHYSICS},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2, max_tokens=2000,
            response_format={"type": "json_object"}
        )
        raw = resp.choices[0].message.content or "{}"
        data = safe_json_parse(raw)
        return {
            "subject": "mathimatika",
            "generated_at": time.strftime("%Y-%m-%d"),
            "chapters": data.get("chapters", []),
            "general_tips": data.get("general_tips", []),
            "top_tools": data.get("top_tools", []),
            "exam_strategy": data.get("exam_strategy", ""),
        }
    except Exception as e:
        print("  ❌ Monolithic SOS failed: " + str(e))
        return {"subject": "mathimatika", "generated_at": time.strftime("%Y-%m-%d"),
                "chapters": [], "general_tips": [], "top_tools": [], "exam_strategy": ""}

def per_chapter_sos(client, v2, subject_name, is_math):
    """Build SOS chapter-by-chapter — for subjects with numbered chapters."""
    chapters = defaultdict(list)
    for q in v2:
        tags = q.get("conceptual_tags", [])
        if tags:
            tag = tags[0]
            ch_num, ch_title = extract_chapter(tag)
            if ch_num:
                parent = f"Κεφάλαιο {ch_num.split('.')[0]}"
                chapters[parent].append(q)
            else:
                chapters[tag.strip()].append(q)
        else:
            chapters[q.get("part", "Άλλο")].append(q)
    
    print(f"Found {len(chapters)} groups")
    
    guidelines = {
        "subject": "mathimatika",
        "generated_at": time.strftime("%Y-%m-%d"),
        "chapters": [],
        "general_tips": [],
        "top_tools": [],
        "exam_strategy": ""
    }
    
    for idx, (title, questions) in enumerate(sorted(chapters.items(), key=lambda x: -len(x[1]))):
        print(f"\n[{idx+1}/{len(chapters)}] {title} ({len(questions)} Qs)")
        
        parts = Counter(q.get("part", "?") for q in questions)
        samples = []
        for q in questions[:12]:
            plain = re.sub(r'<[^>]+>', ' ', q.get("answer_html", ""))[:500]
            plain = re.sub(r'\s+', ' ', plain).strip()
            if plain: samples.append(plain)
        
        if not samples:
            print("  ⚠️ No answers — skipping")
            continue
        
        parts_str = ", ".join(f"{v} Θέμα {k}" for k, v in sorted(parts.items()))
        math_hint = "Χρησιμοποίησε LaTeX $...$ για μαθηματικά." if is_math else ""
        sample_block = "\n---\n".join(samples)[:4000]
        prompt = (f"ΘΕΜΑ: {title} ({len(questions)} θέματα) — {parts_str}\n"
                  f"{math_hint}\n\n"
                  f"ΛΥΣΕΙΣ:\n{sample_block}\n\n"
                  f'Δώσε SOS σε JSON: {{"key_concepts":[...],"traps":[...],"patterns":[...],"must_know":"..."}}. ΜΟΝΟ JSON.')

        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_MATH if is_math else SYSTEM_PROMPT_PHYSICS},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2, max_tokens=800,
                response_format={"type": "json_object"}
            )
            raw = resp.choices[0].message.content or "{}"
            data = safe_json_parse(raw)
            
            guidelines["chapters"].append({
                "id": title[:4],
                "title": title,
                "question_count": len(questions),
                "key_concepts": data.get("key_concepts", []),
                "traps": data.get("traps", []),
                "patterns": data.get("patterns", []),
                "must_know": data.get("must_know", ""),
                "thema_b_tools": data.get("thema_b_tools", ""),
                "thema_cd_tools": data.get("thema_cd_tools", ""),
            })
            if data.get("key_concepts"):
                print(f"  ✅ {len(guidelines['chapters'][-1]['key_concepts'])} concepts")
            else:
                print(f"  ⚠️  Empty")
        except Exception as e:
            print(f"  ❌ {e}")
        
        time.sleep(0.8)
    
    # Global pass
    print(f"\n🧠 Global intelligence pass...")
    chapter_list = "\n".join(f"{c['title']}: {c['question_count']} θέματα" for c in guidelines["chapters"])
    
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Είσαι καθηγητής Πανελληνίων. Casual Ελληνικά. ΜΟΝΟ JSON."},
                {"role": "user", "content": f"Ενότητες:\n{chapter_list}\n\nΔώσε 5-6 γενικές συμβουλές, 5-6 top εργαλεία, στρατηγική εξέτασης. JSON: {{\"general_tips\": [...], \"top_tools\": [...], \"exam_strategy\": \"...\"}}"}
            ],
            temperature=0.2, max_tokens=800,
            response_format={"type": "json_object"}
        )
        raw = resp.choices[0].message.content or "{}"
        data = safe_json_parse(raw)
        guidelines["general_tips"] = data.get("general_tips", [])
        guidelines["top_tools"] = data.get("top_tools", [])
        guidelines["exam_strategy"] = data.get("exam_strategy", "")
        print(f"  ✅ {len(guidelines['general_tips'])} tips, {len(guidelines['top_tools'])} tools")
    except Exception as e:
        print(f"  ❌ {e}")
    
    return guidelines

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--subject", default="mathematics")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key: print("ERROR: DEEPSEEK_API_KEY not set"); return
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    v2_file = os.path.join(BASE, "data", "subjects", args.subject, "questions_v2.json")
    if not os.path.exists(v2_file): print(f"ERROR: {v2_file} not found"); return

    v2 = json.load(open(v2_file, encoding="utf-8"))
    is_math = args.subject in ("mathematics", "mathematics_prosanatolismoy")
    
    subject_name = {"mathematics_prosanatolismoy": "Μαθηματικά Προσανατολισμού",
                    "mathematics": "Μαθηματικά Προσανατολισμού",
                    "informatics": "Πληροφορική",
                    "mathimatika": "Μαθηματικά Γενικής",
                    "biologia": "Βιολογία",
                    "chimeia": "Χημεία",
                    "fysiki_prosanatolismoy": "Φυσική Προσανατολισμού",
                    "oikonomia": "Οικονομία"}.get(args.subject, args.subject)

    # Decide strategy: count unique groups
    chapters = defaultdict(list)
    for q in v2:
        tags = q.get("conceptual_tags", [])
        if tags:
            tag = tags[0]
            ch_num, _ = extract_chapter(tag)
            if ch_num:
                parent = f"Κεφάλαιο {ch_num.split('.')[0]}"
                chapters[parent].append(q)
            else:
                chapters[tag.strip().lower()].append(q)
        else:
            chapters[q.get("part", "Άλλο")].append(q)
    
    print(f"Found {len(chapters)} groups in {args.subject} ({len(v2)} questions)")
    
    if len(chapters) > 20:
        print("📋 GRANULAR tags → using monolithic SOS (one LLM pass)")
        guidelines = monolithic_sos(client, v2, subject_name, is_math)
    else:
        print("📋 Numbered chapters → per-chapter SOS")
        guidelines = per_chapter_sos(client, v2, subject_name, is_math)

    out_file = os.path.join(BASE, "data", "subjects", args.subject, "sos_guidelines.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(guidelines, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Saved: {len(guidelines['chapters'])} groups → {out_file}")

if __name__ == "__main__":
    main()