#!/usr/bin/env python3
"""
build_sos_guidelines.py — Generate SOS cheatsheet per subject from exam answers.
v4: LLM-based semantic chapter grouping for granular tag subjects (>20 chapters).

Handles multiple tag formats:
  - mathematics: "1.3 Μονότονες συναρτήσεις" (numbered chapters)
  - informatics: "Δομή Επανάληψης" (plain text tags)
  - physics/chemistry/biology/economics: granular tags → LLM auto-merged into parent topics

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

SYSTEM_PROMPT_MATH = """Είσαι ένας καθηγητής Πανελληνίων που μιλάει σαν φίλος/κολλητός σε μαθητή Λυκείου.
ΟΧΙ επίσημη γλώσσα, ΟΧΙ σαν πανεπιστημιακό σύγγραμμα. Χρησιμοποίησε καθημερινά Ελληνικά.

Για το παρακάτω θέμα/ενότητα, ανέλυσες πραγματικές λύσεις και δίνεις:

1. 🔑 SOS Έννοιες (3-5): Τι εμφανίζεται ΣΧΕΔΟΝ ΠΑΝΤΑ, με μικρό παράδειγμα σε παρένθεση
2. ⚠️ Παγίδες που ΠΟΝΑΝΕ (2-4): Τι σε κάνει να χάνεις μονάδες, με συγκεκριμένο σενάριο
3. 📝 SOS Μοτίβο (1-2): Το μοτίβο που λύνει τα ΠΕΡΙΣΣΟΤΕΡΑ θέματα
4. 💡 Το απόλυτο takeaway (1 πρόταση): Τι να θυμάται ο μαθητής πριν μπει στην αίθουσα

ΣΗΜΑΝΤΙΚΟ: Χρησιμοποίησε LaTeX μέσα σε $...$ για μαθηματικά (αν έχει). Κάθε σημείο 1-3 προτάσεις max.
Απόφυγε λέξεις όπως "απαιτείται", "επιβάλλεται", "συνιστάται" — πες "πρέπει", "θες", "χρειάζεσαι".

ΕΠΙΣΤΡΕΨΕ ΜΟΝΟ JSON:
{{"key_concepts": [...], "traps": [...], "patterns": [...], "must_know": "...", "thema_b_tools": "...", "thema_cd_tools": "..."}}"""

SYSTEM_PROMPT_PHYSICS = """Είσαι φίλος-προπονητής Φυσικής για μαθητές Λυκείου που προετοιμάζονται για Πανελλήνιες.
Μίλα σαν φίλος σε φίλο, με απλά καθημερινά λόγια. ΟΧΙ σαν σχολικό βιβλίο.
ΟΧΙ LaTeX — χρησιμοποίησε απλό κείμενο ή ASCII (π.χ. F=ma, p=mv, E=1/2*m*v^2).

Για το παρακάτω θέμα/ενότητα, ανέλυσες πραγματικές λύσεις και δίνεις:
1. 🔑 SOS Έννοιες (3-5): Τι εμφανίζεται ΣΧΕΔΟΝ ΠΑΝΤΑ + ΠΑΡΑΔΕΙΓΜΑ
2. ⚠️ Παγίδες που ΠΟΝΑΝΕ (2-4): Συγκεκριμένο σενάριο που χάνεις μονάδες
3. 📝 SOS Μοτίβο (1-2): Το βήμα-βήμα που λύνει τα περισσότερα
4. 💡 Το απόλυτο takeaway (1 πρόταση)

ΕΠΙΣΤΡΕΨΕ ΜΟΝΟ JSON:
{{"key_concepts": [...], "traps": [...], "patterns": [...], "must_know": "...", "thema_b_tools": "...", "thema_cd_tools": "..."}}"""

CHEMISTRY_GROUPS = [
    ("ηλεκτρονιακ|τροχιακ|κβαντικ|ατομικ|στιβάδ|περιοδικ|δόμηση|κατανομή ηλ", "Ατομική Δομή & Περιοδικός Πίνακας"),
    ("οξειδοαναγωγ|οξείδωση|αναγωγή|αριθμός οξείδωσης", "Οξειδοαναγωγή"),
    ("οξέ|βάσ|ιοντισμό|pH|δείκτ|ογκομέτρ|brönsted", "Οξέα — Βάσεις — pH"),
    ("διαμοριακ|δεσμό|δύναμη|υδρογόν|διπόλ|διασπορά|London", "Διαμοριακές Δυνάμεις & Δεσμοί"),
    ("χημική ισορροπ|σταθερά|Le Chatelier|παράγοντ", "Χημική Ισορροπία"),
    ("ταχύτητα αντίδραση|ενέργεια ενεργοπ|καταλύτ", "Χημική Κινητική"),
    ("ενθαλπ|θερμοχημ|εξώθερμ|ενδόθερμ", "Θερμοχημεία"),
    ("οργανικ|πολυμερισμ|αλκοόλ|αλδε|κετόν|καρβοξυλ", "Οργανική Χημεία"),
    ("ώσμω|ωσμωτ|διαλύμ|συγκέντρωσ", "Διαλύματα — Ώσμωση"),
    ("συντελεστ|στοιχειομετρ", "Στοιχειομετρία"),
]
BIOLOGY_GROUPS = [
    ("DNA|RNA|νουκλε|γονίδιο|γενετικ|μεταγραφή|μετάφραση|αντιγραφή|κώδικ|χρωμόσωμ|καρυό|πυρην|νουκλεό|τRNA|mRNA|ριβόσωμ|ριβοσωμ", "Γενετικό Υλικό — DNA/RNA"),
    ("κύτταρ|κυτταρ|μεμβράν|οργανίδ|μιτοχόνδ|χλωροπλ|ενδοπλασμ|πλασμίδ|κυτταροπλ|κάρυ", "Κύτταρο & Οργανίδια"),
    ("πρωτεΐν|αμινοξ|ένζυμ|σύνθεση|βιοσύνθεση|πεπτιδ|δεσμ|στερεοδιάτ|διαμόρφωση|μετουσίωσ|ολιγοπεπτ|αλβουμίνη", "Πρωτεΐνες & Ένζυμα"),
    ("μίτωση|μείωση|διαίρεση|κυτταρικ|μεσόφαση|γαμέτ|σπερματογ|ωογέν|αναπαραγωγ|επιχιασμ|ομόλογ", "Κυτταρική Διαίρεση — Μίτωση/Μείωση"),
    ("μεταβολισμ|αναπνοή|γλυκόλυση|Krebs|ATP|φωτοσύνθεση|χημειοσύνθεση|φωτεινή|Calvin|οξειδωτικ|γλυκονεογ|ζύμωσ|γαλακτικ|χοληστερ", "Μεταβολισμός — Αναπνοή & Φωτοσύνθεση"),
    ("οικολ|οικοσύστημ|τροφικ|πληθυσμ|βιοποικιλ|ρύπαν|διαχείρ|τροφ|οικογ|βιοκ|περιβαλλ", "Οικολογία & Οικοσυστήματα"),
    ("νευρικ|νευρών|σύναψη|ορμόνη|ενδοκριν|αδένα|υποθάλαμ|υπόφυσ|συνάψ|μεταβιβαστ|θυρεοειδ|ινσουλ|γλυκαγ", "Νευρικό & Ενδοκρινικό Σύστημα"),
    ("ανοσο|αντισώμ|λεμφοκύτ|ανοσία|εμβόλ|αντιγόν|μακροφάγ|ανοσοπ|αυτοάν|αλλεργ", "Ανοσοποιητικό Σύστημα"),
    ("βακτηριοφάγ|E.coli|coli|καλλιέργει|ιός|βακτήρ|μικροοργ|παθογόν|μόλυνσ|λοίμωξ|ανθεκτ|αντιβι|φάρμακ|μύκητ|πρωτόζ|griffith|πείραμ|στέλεχ|αμιγή", "Μικροοργανισμοί & Λοιμώξεις"),
    ("cDNA|βιβλιοθ|γονιδιακ|θεραπε|βιοτεχν|γενετικ μηχανικ|κλωνοπ|ανασυνδυασμ|PCR|ηλεκτροφόρ|διαγονιδ|αλυσιδ|φορέα|πλασμ|Taq", "Βιοτεχνολογία & Γενετική Μηχανική"),
    ("προγεννητ|διάγνωσ|καρκίν|αλτσχ|μελαγχρ|ξηροδερμ|θαλασσ|τρισωμ|ανευπλ|χρωμοσωμ ανωμ|αλφισμ|αχονδρ|γονιδιακ|έκφρασ|μεταλλάξ|οπερόν|λακτόζ|mendel|μεντ|griffith|δροσόφ|μονοϋβριδ|διυβριδ|κληρονομ|φαινότυπ|γονότυπ|επικρατ|υπολειπ|αυτοσωμ|φυλοσύνδ|γενεαλ|ομάδ|αίματ|φυλ|ασθέν|νόσημ|διασταύρ|άγρι|τύπ", "Κληρονομικότητα & Γενετικές Ασθένειες"),
    ("πέψη|πεπτικ|γαστρεν|στομάχι|έντερο|απορρόφ|πεπτ|στομαχ|γαστρ", "Πεπτικό Σύστημα"),
    ("εξέλικ|φυσικ επιλογ|Δαρβίν|προσαρμογ|ειδογέν|απολίθ|φυλογεν|ταξινομ|συνθετικ|εξελιξ", "Εξέλιξη"),
    ("κυκλοφορ|καρδι|αγγεί|αιμοσφαίρ|αιμοπετ|πλάσμ|αναπνευστ|πνεύμ|κυψελ|απέκκρι|νεφρ|νεφρώ|ομοιοστ", "Συστήματα Σώματος — Κυκλοφορικό, Αναπνευστικό, Απεκκριτικό"),
]
ECONOMICS_GROUPS = [
    ("προσφορά|ζήτηση|ελαστικ|αγορά|τιμή|ισορροπ", "Προσφορά — Ζήτηση — Τιμή"),
    ("κόστος|έσοδο|κέρδος|παραγωγ|οριακ|μέσο|συνολικ", "Κόστος Παραγωγής — Έσοδα — Κέρδη"),
    ("ΑΕΠ|πληθωρισμ|ανεργ|φορολ|δημόσιο|προϋπολογ|εισόδημ|κατανάλ|επένδ|χρέο", "Μακροοικονομία — ΑΕΠ, Πληθωρισμός, Ανεργία"),
    ("μονοπώλ|ολιγοπώλ|τέλει|ανταγων|μορφή αγορ|ανταγωνιστ", "Μορφές Αγοράς — Μονοπώλιο, Ολιγοπώλιο"),
    ("ευημερ|χρησιμότ|αδιάφορ|οικονομικ|άριστο|καταναλωτ|συμπεριφορ", "Θεωρία Καταναλωτή — Χρησιμότητα, Ευημερία"),
]

def merge_chapters(client, guidelines, group_keywords=None):
    """Post-process: merge many granular chapters into broader parent topics.
    Uses LLM-based semantic grouping — sends all chapter titles to the AI for classification.
    Falls back to regex keyword matching if group_keywords are provided.
    """
    chapters = guidelines["chapters"]
    if len(chapters) <= 20:
        return
    
    print(f"\n🔀 {len(chapters)} chapters → merging into broader topics...")
    
    chapter_list = [{"title": ch["title"], "count": ch["question_count"]} for ch in chapters]
    
    classify_prompt = f"""Έχουμε {len(chapters)} μικρές ενότητες που θέλουμε να ομαδοποιήσουμε σε ~10-15 ευρύτερες γονικές ενότητες.

ΟΜΑΔΟΠΟΙΗΣΕ τις παρακάτω ενότητες με βάση το νόημα (semantic similarity). Κάθε ενότητα μπαίνει σε ΜΙΑ ομάδα. Μην αφήσεις καμία αταξινόμητη.

Για κάθε ομάδα, διάλεξε ένα σύντομο, περιγραφικό όνομα.

ΕΝΟΤΗΤΕΣ:
{chr(10).join(f'- {c["title"]} ({c["count"]} θέματα)' for c in chapter_list)}

ΕΠΙΣΤΡΕΨΕ ΜΟΝΟ JSON — μια λίστα με τις ομάδες και τα ονόματα των ενοτήτων που ανήκουν σε κάθε μία:
{{
  "groups": [
    {{
      "group_name": "Όνομα Ομάδας",
      "members": ["τίτλος ενότητας 1", "τίτλος ενότητας 2", ...]
    }},
    ...
  ]
}}"""

    try:
        print("  🤖 LLM classifying chapters into groups...")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Είσαι βοηθός ομαδοποίησης εννοιών. Ομαδοποίησε με βάση το νόημα. ΜΟΝΟ JSON. Όλες οι ενότητες πρέπει να ανήκουν σε κάποια ομάδα."},
                {"role": "user", "content": classify_prompt}
            ],
            temperature=0.1, max_tokens=2000,
            response_format={"type": "json_object"}
        )
        raw = resp.choices[0].message.content or "{}"
        classification = safe_json_parse(raw)
        llm_groups = classification.get("groups", [])
        print(f"  ✅ LLM created {len(llm_groups)} groups")
    except Exception as e:
        print(f"  ❌ LLM classification failed: {e}")
        llm_groups = []
    
    title_to_chapter = {}
    for ch in chapters:
        title_to_chapter[ch["title"].strip()] = ch
    
    groups = defaultdict(list)
    classified_titles = set()
    
    for g in llm_groups:
        group_name = g.get("group_name", "Άλλο")
        members = g.get("members", [])
        for member_title in members:
            member_title = member_title.strip()
            if member_title in title_to_chapter and member_title not in classified_titles:
                groups[group_name].append(title_to_chapter[member_title])
                classified_titles.add(member_title)
    
    unclassified = [ch for ch in chapters if ch["title"].strip() not in classified_titles]
    if unclassified:
        if group_keywords:
            for ch in unclassified:
                title_lower = ch["title"].lower()
                assigned = False
                for pattern, group_name in group_keywords:
                    if re.search(pattern, title_lower):
                        groups[group_name].append(ch)
                        assigned = True
                        break
                if not assigned:
                    groups["Άλλα Θέματα"].append(ch)
        else:
            groups["Άλλα Θέματα"].extend(unclassified)
    
    if unclassified:
        print(f"  ⚠️  {len(unclassified)} unclassified chapters → Άλλα Θέματα")
    
    merged = []
    
    for group_name, group_chapters in sorted(groups.items()):
        if len(group_chapters) <= 1:
            merged.extend(group_chapters)
            continue
        
        total_qs = sum(c["question_count"] for c in group_chapters)
        print(f"  Merging: {group_name} ({len(group_chapters)} chapters → 1, {total_qs} Qs)")
        
        all_concepts = []
        all_traps = []
        all_patterns = []
        for ch in group_chapters:
            all_concepts.extend(ch.get("key_concepts", []))
            all_traps.extend(ch.get("traps", []))
            all_patterns.extend(ch.get("patterns", []))
        
        all_concepts = list(dict.fromkeys(all_concepts))[:15]
        all_traps = list(dict.fromkeys(all_traps))[:10]
        all_patterns = list(dict.fromkeys(all_patterns))[:6]
        
        merge_prompt = f"""ΕΝΟΤΗΤΑ: {group_name} ({total_qs} θέματα)

SOS έννοιες, παγίδες και μοτίβα από {len(group_chapters)} υποενότητες. 
Συνόψισέ τες σε μια ενιαία, συμπαγή παρουσίαση. 3-5 έννοιες, 2-4 παγίδες, 1-2 μοτίβα, 1 must_know.
Μίλα σαν φίλος, casual Ελληνικά. Σύντομες προτάσεις.

ΕΝΝΟΙΕΣ:
{chr(10).join(f'- {c}' for c in all_concepts[:10])}

ΠΑΓΙΔΕΣ:
{chr(10).join(f'- {t}' for t in all_traps[:8])}

ΜΟΤΙΒΑ:
{chr(10).join(f'- {p}' for p in all_patterns[:5])}

ΜΟΝΟ JSON: {{"key_concepts": [...], "traps": [...], "patterns": [...], "must_know": "...", "thema_b_tools": "...", "thema_cd_tools": "..."}}"""
        
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "Είσαι φίλος-προπονητής Πανελληνίων. Casual Ελληνικά, σύντομες προτάσεις. ΜΟΝΟ JSON."},
                    {"role": "user", "content": merge_prompt}
                ],
                temperature=0.2, max_tokens=600,
                response_format={"type": "json_object"}
            )
            raw = resp.choices[0].message.content or "{}"
            data = safe_json_parse(raw)
            
            merged.append({
                "id": group_name[:4],
                "title": group_name,
                "question_count": total_qs,
                "key_concepts": data.get("key_concepts", all_concepts[:5]),
                "traps": data.get("traps", all_traps[:4]),
                "patterns": data.get("patterns", all_patterns[:2]),
                "must_know": data.get("must_know", ""),
                "thema_b_tools": data.get("thema_b_tools", ""),
                "thema_cd_tools": data.get("thema_cd_tools", ""),
            })
            print(f"    ✅ {len(merged[-1]['key_concepts'])} concepts, {len(merged[-1]['traps'])} traps")
        except Exception as e:
            print(f"    ❌ Merge failed: {e}")
            merged.extend(group_chapters)
        
        time.sleep(0.8)
    
    merged.sort(key=lambda x: -x["question_count"])
    print(f"  ✅ {len(chapters)} → {len(merged)} chapters")
    guidelines["chapters"] = merged

def build_prompt(chapter_title, answers_sample, part_distribution, question_count, is_math):
    parts_str = ", ".join(f"{v} Θέμα {k}" for k, v in sorted(part_distribution.items()))
    if is_math:
        system = SYSTEM_PROMPT_MATH
        math_hint = "\nΧρησιμοποίησε LaTeX $...$ για μαθηματικά."
    else:
        system = SYSTEM_PROMPT_PHYSICS
        math_hint = ""
    return system, f"""ΘΕΜΑ/ΕΝΟΤΗΤΑ: {chapter_title} ({question_count} θέματα)
Κατανομή: {parts_str}
{math_hint}

Παρακάτω είναι αποσπάσματα από ΠΡΑΓΜΑΤΙΚΕΣ λύσεις. Ανέλυσέ τες και βρες τα SOS μοτίβα. Μίλα σαν φίλος.

ΛΥΣΕΙΣ:
{answers_sample[:4000]}

Γράψε τον Οδηγό SOS σε JSON:"""

def build_global_prompt(all_chapter_data, subject_name):
    chapters_summary = []
    for c in all_chapter_data:
        chapters_summary.append(f"{c['title']}: {c['question_count']} θέματα")
    chapter_list = "\n".join(chapters_summary)
    
    return f"""Ανέλυσες {len(all_chapter_data)} ενότητες του μαθήματος {subject_name} με συνολικά θέματα Πανελλαδικών.

Ενότητες:
{chapter_list}

Τώρα δώσε ΓΕΝΙΚΕΣ συμβουλές SOS με casual γλώσσα (σαν φίλος σε φίλο):

1. ⭐ Γενικές Συμβουλές (5-6): Τι να θυμάται ο μαθητής
2. 🛠 Top Εργαλεία: Ποια είναι τα 5-6 πιο συχνά εργαλεία/τεχνικές που χρησιμοποιούνται;
3. 📝 Στρατηγική Εξέτασης: μια παράγραφος για το πώς να προσεγγίσει το γραπτό

Γράψε στα Ελληνικά, casual ύφος. Κάθε συμβουλή 1-3 προτάσεις.

ΕΠΙΣΤΡΕΨΕ ΜΟΝΟ JSON:
{{
  "general_tips": ["tip 1", "tip 2", ...],
  "top_tools": ["εργαλείο 1", ...],
  "exam_strategy": "στρατηγική εξέτασης"
}}"""

def extract_chapter(tag):
    m = re.match(r'^([0-9]+\.[0-9]+)\s+(.+)', tag)
    if m:
        return m.group(1), m.group(2)
    return None, tag

def safe_json_parse(raw):
    for strategy in [
        lambda: json.loads(raw),
        lambda: json.loads(re.search(r'\{[\s\S]*\}', raw).group(0)) if re.search(r'\{[\s\S]*\}', raw) else {},
        lambda: json.loads(re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', re.search(r'\{[\s\S]*\}', raw).group(0))) if re.search(r'\{[\s\S]*\}', raw) else {}
    ]:
        try: return strategy()
        except: pass
    return {}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--subject", default="mathematics")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--no-merge", action="store_true", help="Skip chapter merging")
    args = p.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set"); return
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    v2_file = os.path.join(BASE, "data", "subjects", args.subject, "questions_v2.json")
    if not os.path.exists(v2_file):
        print(f"ERROR: {v2_file} not found"); return

    v2 = json.load(open(v2_file, encoding="utf-8"))
    cfg = json.load(open(os.path.join(BASE, "subjects", f"{args.subject}.json"), encoding="utf-8"))
    is_math = args.subject in ("mathematics", "mathematics_prosanatolismoy")

    chapters = defaultdict(list)
    
    for q in v2:
        tags = q.get("conceptual_tags", [])
        if tags:
            tag = tags[0]
            ch_num, ch_title = extract_chapter(tag)
            if ch_num:
                chapters[(ch_num, ch_title)].append(q)
            else:
                chapters[("", tag.strip().lower())].append(q)
        else:
            part = q.get("part", "Άλλο")
            chapters[("", part)].append(q)

    merged = defaultdict(list)
    for (num, title), questions in chapters.items():
        merged[title].extend(questions)

    print(f"Found {len(merged)} groups in {args.subject} ({len(v2)} questions)")

    subject_name = {"mathematics_prosanatolismoy": "Μαθηματικά Προσανατολισμού",
                    "mathematics": "Μαθηματικά Προσανατολισμού",
                    "informatics": "Πληροφορική",
                    "fysiki_prosanatolismoy": "Φυσική Προσανατολισμού",
                    "chimeia": "Χημεία",
                    "biologia": "Βιολογία",
                    "oikonomia": "Οικονομία"}.get(args.subject, args.subject)

    guidelines = {
        "subject": args.subject,
        "generated_at": time.strftime("%Y-%m-%d"),
        "chapters": [],
        "general_tips": [],
        "top_tools": [],
        "exam_strategy": ""
    }

    group_items = sorted(merged.items(), key=lambda x: -len(x[1]))
    if args.limit > 0:
        group_items = group_items[:args.limit]

    for idx, (title, questions) in enumerate(group_items):
        print(f"\n[{idx+1}/{len(group_items)}] {title} ({len(questions)} questions)")

        parts = Counter(q.get("part", "?") for q in questions)
        
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

        system_prompt, user_prompt = build_prompt(title, "\n---\n".join(samples), parts, len(questions), is_math)

        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=800,
                response_format={"type": "json_object"}
            )
            raw = resp.choices[0].message.content or "{}"
            data = safe_json_parse(raw)
            
            chapter_data = {
                "id": title[:4] if title[0].isdigit() else "",
                "title": title,
                "question_count": len(questions),
                "key_concepts": data.get("key_concepts", []),
                "traps": data.get("traps", []),
                "patterns": data.get("patterns", []),
                "must_know": data.get("must_know", ""),
                "thema_b_tools": data.get("thema_b_tools", ""),
                "thema_cd_tools": data.get("thema_cd_tools", ""),
            }
            guidelines["chapters"].append(chapter_data)
            if data.get("key_concepts"):
                print(f"  ✅ {len(chapter_data['key_concepts'])} concepts, {len(chapter_data['traps'])} traps")
            else:
                print(f"  ⚠️  Empty — saved placeholder")

        except Exception as e:
            print(f"  ❌ Error: {e}")

        time.sleep(1)

    if not args.no_merge:
        groups_map = {
            "chimeia": CHEMISTRY_GROUPS,
            "biologia": BIOLOGY_GROUPS,
            "oikonomia": ECONOMICS_GROUPS,
        }
        if args.subject in groups_map:
            merge_chapters(client, guidelines, groups_map[args.subject])
        elif len(guidelines["chapters"]) > 20:
            merge_chapters(client, guidelines)

    print(f"\n🧠 Global intelligence pass...")
    
    global_prompt = build_global_prompt(guidelines["chapters"], subject_name)
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Είσαι καθηγητής Πανελληνίων. Μίλα σαν φίλος, casual Ελληνικά, με ουσία. Δώσε μόνο JSON."},
                {"role": "user", "content": global_prompt}
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
        print(f"  ❌ Global pass error: {e}")

    out_file = os.path.join(BASE, "data", "subjects", args.subject, "sos_guidelines.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(guidelines, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Saved: {len(guidelines['chapters'])} groups → {out_file}")

if __name__ == "__main__":
    main()