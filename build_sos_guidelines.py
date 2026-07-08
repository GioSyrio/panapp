#!/usr/bin/env python3
"""
build_sos_guidelines.py — Generate SOS cheatsheet.
v6: Always per-chapter. Auto-merges with LLM if >20 chapters.

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

SYSTEM_PROMPT = """Είσαι φίλος-προπονητής Πανελληνίων που μιλάει σαν κολλητός.
Ανέλυσες πραγματικές λύσεις. Δώσε:
1. 🔑 SOS Έννοιες (3-5): Τι εμφανίζεται ΣΧΕΔΟΝ ΠΑΝΤΑ
2. ⚠️ Παγίδες που ΠΟΝΑΝΕ (2-4): Συγκεκριμένο σενάριο
3. 📝 SOS Μοτίβο (1-2): Βήμα-βήμα
4. 💡 must_know (1 πρόταση)
Casual Ελληνικά. ΜΟΝΟ JSON: {{"key_concepts": [...], "traps": [...], "patterns": [...], "must_know": "...", "thema_b_tools": "...", "thema_cd_tools": "..."}}"""

def extract_chapter(tag):
    m = re.match(r'^([0-9]+\.[0-9]+)\s+(.+)', tag)
    if m: return m.group(1), m.group(2)
    return None, tag

def safe_json_parse(raw):
    for s in [lambda: json.loads(raw),
              lambda: json.loads(re.search(r'\{[\s\S]*\}', raw).group(0)) if re.search(r'\{[\s\S]*\}', raw) else {}]:
        try: return s()
        except: pass
    return {}

def llm_merge(client, chapters, subject_name):
    """Use LLM to group many chapters into ~10-15 parent topics."""
    if len(chapters) <= 20:
        return chapters
    
    print("\n🔀 " + str(len(chapters)) + " chapters → LLM merge into ~15 parent topics...")
    
    chapter_list = [{"title": ch["title"], "count": ch["question_count"]} for ch in chapters]
    
    prompt = ("Έχουμε " + str(len(chapters)) + " μικρές ενότητες που θέλουμε να ομαδοποιήσουμε "
              "σε ~12-15 ευρύτερες γονικές ενότητες.\n\n"
              "ΟΜΑΔΟΠΟΙΗΣΕ τις παρακάτω ενότητες με βάση το νόημα. Κάθε ενότητα σε ΜΙΑ ομάδα. "
              "Μην αφήσεις καμία αταξινόμητη. Διάλεξε σύντομο περιγραφικό όνομα για κάθε ομάδα.\n\n"
              "ΕΝΟΤΗΤΕΣ:\n" + "\n".join(f'- {c["title"]} ({c["count"]} θέματα)' for c in chapter_list) + "\n\n"
              'ΕΠΙΣΤΡΕΨΕ ΜΟΝΟ JSON: {{"groups": [{{"group_name": "Όνομα", "members": ["τίτλος1", "τίτλος2", ...]}}, ...]}}')
    
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Ομαδοποίησε έννοιες με βάση το νόημα. ΜΟΝΟ JSON. Όλες οι ενότητες σε κάποια ομάδα."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1, max_tokens=2000,
            response_format={"type": "json_object"}
        )
        raw = resp.choices[0].message.content or "{}"
        data = safe_json_parse(raw)
        llm_groups = data.get("groups", [])
        print("  ✅ LLM created " + str(len(llm_groups)) + " groups")
    except Exception as e:
        print("  ❌ LLM classification failed: " + str(e))
        return chapters
    
    # Build lookup
    title_to_ch = {}
    for ch in chapters:
        title_to_ch[ch["title"].strip()] = ch
    
    groups = defaultdict(list)
    classified = set()
    
    for g in llm_groups:
        for member in g.get("members", []):
            member = member.strip()
            # Strip "(NN θέματα)" suffix if present
            member_clean = re.sub(r'\s*\(\d+\s*θέματα\)\s*$', '', member).strip()
            if member in title_to_ch and member not in classified:
                groups[g.get("group_name", "Άλλο")].append(title_to_ch[member])
                classified.add(member)
            elif member_clean in title_to_ch and member_clean not in classified:
                groups[g.get("group_name", "Άλλο")].append(title_to_ch[member_clean])
                classified.add(member_clean)
    
    unclassified = [ch for ch in chapters if ch["title"].strip() not in classified]
    if unclassified:
        groups["Άλλα Θέματα"].extend(unclassified)
        print("  ⚠️  " + str(len(unclassified)) + " unclassified → Άλλα Θέματα")
    
    # Merge each group into one chapter
    merged = []
    for group_name, group_chs in sorted(groups.items()):
        if len(group_chs) <= 1:
            merged.extend(group_chs)
            continue
        
        total_qs = sum(c["question_count"] for c in group_chs)
        print("  Merging: " + group_name + " (" + str(len(group_chs)) + " → 1, " + str(total_qs) + " Qs)")
        
        all_concepts = list(dict.fromkeys(c for ch in group_chs for c in ch.get("key_concepts", [])))[:10]
        all_traps = list(dict.fromkeys(t for ch in group_chs for t in ch.get("traps", [])))[:8]
        
        merge_prompt = ("ΕΝΟΤΗΤΑ: " + group_name + " (" + str(total_qs) + " θέματα)\n\n"
                         "SOS από " + str(len(group_chs)) + " υποενότητες. Συνόψισε: 3-5 έννοιες, 2-4 παγίδες, 1-2 μοτίβα, 1 must_know. "
                         "Casual Ελληνικά. Σύντομα.\n\n"
                         "ΕΝΝΟΙΕΣ:\n" + "\n".join(f'- {c}' for c in all_concepts[:10]) + "\n\n"
                         "ΠΑΓΙΔΕΣ:\n" + "\n".join(f'- {t}' for t in all_traps[:8]) + "\n\n"
                         'ΜΟΝΟ JSON: {{"key_concepts": [...], "traps": [...], "patterns": [...], "must_know": "...", "thema_b_tools": "...", "thema_cd_tools": "..."}}')
        
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "Είσαι φίλος-προπονητής Πανελληνίων. Casual Ελληνικά. ΜΟΝΟ JSON."},
                    {"role": "user", "content": merge_prompt}
                ],
                temperature=0.2, max_tokens=500,
                response_format={"type": "json_object"}
            )
            raw = resp.choices[0].message.content or "{}"
            data = safe_json_parse(raw)
            merged.append({
                "title": group_name,
                "question_count": total_qs,
                "key_concepts": data.get("key_concepts", all_concepts[:5]),
                "traps": data.get("traps", all_traps[:4]),
                "patterns": data.get("patterns", []),
                "must_know": data.get("must_know", ""),
                "thema_b_tools": data.get("thema_b_tools", ""),
                "thema_cd_tools": data.get("thema_cd_tools", ""),
            })
            print("    ✅ " + str(len(merged[-1]["key_concepts"])) + " concepts, " + str(len(merged[-1]["traps"])) + " traps")
        except Exception as e:
            print("    ❌ Merge failed: " + str(e))
            merged.extend(group_chs)
        
        time.sleep(0.4)
    
    merged.sort(key=lambda x: -x["question_count"])
    print("  ✅ " + str(len(chapters)) + " → " + str(len(merged)) + " chapters")
    return merged

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--subject", default="mathematics")
    p.add_argument("--no-merge", action="store_true")
    p.add_argument("--merge-only", action="store_true", help="Only run LLM merge on existing SOS file")
    args = p.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key: print("ERROR: DEEPSEEK_API_KEY not set"); return
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # ── Merge-only mode: read existing SOS, merge, save ──
    if args.merge_only:
        sos_file = os.path.join(BASE, "data", "subjects", args.subject, "sos_guidelines.json")
        if not os.path.exists(sos_file):
            print("ERROR: " + sos_file + " not found. Run without --merge-only first.")
            return
        with open(sos_file, encoding="utf-8") as f:
            guidelines = json.load(f)
        chapters = guidelines.get("chapters", [])
        print("Loaded " + str(len(chapters)) + " chapters from existing SOS")
        if len(chapters) <= 20:
            print("Only " + str(len(chapters)) + " chapters — no merge needed. Use --no-merge to skip.")
            return
        guidelines["chapters"] = llm_merge(client, chapters, "Μαθηματικά Γενικής")
        with open(sos_file, "w", encoding="utf-8") as f:
            json.dump(guidelines, f, ensure_ascii=False, indent=2)
        print("✅ Merged → " + str(len(guidelines["chapters"])) + " groups saved")
        return

    v2_file = os.path.join(BASE, "data", "subjects", args.subject, "questions_v2.json")
    if not os.path.exists(v2_file): print("ERROR: " + v2_file + " not found"); return

    v2 = json.load(open(v2_file, encoding="utf-8"))
    is_math = args.subject in ("mathematics", "mathematics_prosanatolismoy", "mathimatika")
    
    subject_name = {"mathematics_prosanatolismoy": "Μαθηματικά Προσανατολισμού",
                    "mathematics": "Μαθηματικά Προσανατολισμού",
                    "informatics": "Πληροφορική",
                    "mathimatika": "Μαθηματικά Γενικής",
                    "biologia": "Βιολογία",
                    "chimeia": "Χημεία",
                    "fysiki_prosanatolismoy": "Φυσική Προσανατολισμού",
                    "oikonomia": "Οικονομία",
                    "istoria": "Ιστορία Γενικής",
                    "istoria_prosanatolismoy": "Ιστορία Προσανατολισμού",
                    "neoelliniki_glossa_kai_logotechnia": "Νεοελληνική Γλώσσα και Λογοτεχνία",
                    "latinika": "Λατινικά",
                    "archaia_elliniki_glossa_kai_grammateia___archaia_ellinika": "Αρχαία Ελληνικά",
                    }.get(args.subject, args.subject)

    # Group by tag
    chapters = defaultdict(list)
    for q in v2:
        tags = q.get("conceptual_tags", [])
        if tags:
            tag = tags[0]
            ch_num, ch_title = extract_chapter(tag)
            if ch_num:
                parent = "Κεφάλαιο " + ch_num.split('.')[0]
                chapters[parent].append(q)
            else:
                chapters[tag.strip().lower()].append(q)
        else:
            chapters[q.get("part", "Άλλο")].append(q)
    
    print("Found " + str(len(chapters)) + " groups in " + args.subject + " (" + str(len(v2)) + " questions)")

    guidelines = {
        "subject": args.subject,
        "generated_at": time.strftime("%Y-%m-%d"),
        "chapters": [],
        "general_tips": [],
        "top_tools": [],
        "exam_strategy": ""
    }

    # ── Per-chapter SOS ──
    group_items = sorted(chapters.items(), key=lambda x: -len(x[1]))
    
    for idx, (title, questions) in enumerate(group_items):
        print("\n[" + str(idx+1) + "/" + str(len(group_items)) + "] " + title + " (" + str(len(questions)) + " Qs)")
        
        samples = []
        for q in questions[:12]:
            # Try llm_solution_html first (just generated), then answer_html, then answer_text
            raw = q.get("llm_solution_html", "") or q.get("answer_html", "") or q.get("answer_text", "")
            if raw:
                plain = re.sub(r'<[^>]+>', ' ', raw)[:500]
                plain = re.sub(r'\s+', ' ', plain).strip()
                if plain:
                    samples.append(plain)
        
        if not samples:
            print("  ⚠️ No answers — skipping")
            continue
        
        parts = Counter(q.get("part", "?") for q in questions)
        parts_str = ", ".join(f"{v} Θέμα {k}" for k, v in sorted(parts.items()))
        latex_hint = "\nΧρησιμοποίησε LaTeX $...$ για μαθηματικά." if is_math else ""
        
        subject_context = ""
        if args.subject == "oikonomia":
            subject_context = "\nΠΡΟΣΟΧΗ: Είσαι καθηγητής ΟΙΚΟΝΟΜΙΑΣ Πανελληνίων. Όλες οι έννοιες είναι ΟΙΚΟΝΟΜΙΚΕΣ (όχι φυσική, όχι χημεία, όχι άλλο μάθημα). \"Ισορροπία\" εννοείται η ισορροπία αγοράς, \"δύναμη\" η αγοραστική δύναμη, κλπ."
        elif args.subject == "biologia":
            subject_context = "\nΠΡΟΣΟΧΗ: Είσαι καθηγητής ΒΙΟΛΟΓΙΑΣ Πανελληνίων. Όλες οι έννοιες είναι ΒΙΟΛΟΓΙΚΕΣ."
        elif args.subject == "chimeia":
            subject_context = "\nΠΡΟΣΟΧΗ: Είσαι καθηγήτρια ΧΗΜΕΙΑΣ Πανελληνίων. Όλες οι έννοιες είναι ΧΗΜΙΚΕΣ."
        
        prompt = ("ΘΕΜΑ: " + title + " (" + str(len(questions)) + " θέματα) — " + parts_str + "\n"
                  + latex_hint + subject_context + "\n\n"
                  + "ΛΥΣΕΙΣ:\n" + "\n---\n".join(samples)[:4000] + "\n\n"
                  + 'Δώσε SOS σε JSON: {{"key_concepts":[...],"traps":[...],"patterns":[...],"must_know":"..."}}. ΜΟΝΟ JSON.')

        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2, max_tokens=800,
                response_format={"type": "json_object"}
            )
            raw = resp.choices[0].message.content or "{}"
            data = safe_json_parse(raw)
            
            guidelines["chapters"].append({
                "id": title[:4] if title[0].isdigit() else "",
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
                print("  ✅ " + str(len(guidelines["chapters"][-1]["key_concepts"])) + " concepts")
            else:
                print("  ⚠️  Empty")
        except Exception as e:
            print("  ❌ " + str(e))
        
        time.sleep(0.8)

    # ── LLM merge if too many chapters ──
    if not args.no_merge and len(guidelines["chapters"]) > 20:
        guidelines["chapters"] = llm_merge(client, guidelines["chapters"], subject_name)

    # ── Global tips ──
    if guidelines["chapters"]:
        print("\n🧠 Global pass...")
        ch_list = "\n".join(f'{c["title"]}: {c["question_count"]} θέματα' for c in guidelines["chapters"])
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "Casual Ελληνικά. ΜΟΝΟ JSON."},
                    {"role": "user", "content": "Ενότητες:\n" + ch_list + '\n\nΔώσε 5-6 general_tips, 5-6 top_tools, exam_strategy. JSON: {{"general_tips":[...],"top_tools":[...],"exam_strategy":"..."}}'}
                ],
                temperature=0.2, max_tokens=800,
                response_format={"type": "json_object"}
            )
            raw = resp.choices[0].message.content or "{}"
            data = safe_json_parse(raw)
            guidelines["general_tips"] = data.get("general_tips", [])
            guidelines["top_tools"] = data.get("top_tools", [])
            guidelines["exam_strategy"] = data.get("exam_strategy", "")
            print("  ✅ " + str(len(guidelines["general_tips"])) + " tips, " + str(len(guidelines["top_tools"])) + " tools")
        except Exception as e:
            print("  ❌ " + str(e))

    out_file = os.path.join(BASE, "data", "subjects", args.subject, "sos_guidelines.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(guidelines, f, ensure_ascii=False, indent=2)
    print("\n✅ Saved: " + str(len(guidelines["chapters"])) + " groups → " + out_file)

if __name__ == "__main__":
    main()