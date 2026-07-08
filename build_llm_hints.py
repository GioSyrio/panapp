#!/usr/bin/env python3
"""
build_llm_hints.py — Offline 3-tier Socratic hints (all subjects)

Usage:
    python3 build_llm_hints.py --subject informatics
    python3 build_llm_hints.py --subject istoria --limit 5
    python3 build_llm_hints.py --subject istoria --id 25329
"""

import json, os, sys, argparse, time, shutil
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from prompt_loader import load_prompts as _load_subject_prompts

def load_subject_config(subject_id):
    cfg_path = os.path.join(BASE_DIR, "subjects", f"{subject_id}.json")
    with open(cfg_path, encoding="utf-8") as f:
        return json.load(f)

def init_client():
    from openai import OpenAI
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: DEEPSEEK_API_KEY not set"); sys.exit(1)
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

INFORMATICS_HINT_PROMPT = """You are an expert Greek Informatics tutor using Socratic scaffolding.
Generate a single hint at the requested level for the given question.

CRITICAL RULES:
- NEVER reveal the final answer, exact values, or complete solutions.
- Be encouraging, direct, and exclusively in Greek.
- Return ONLY a JSON object: {{"hint_text": "Your hint here..."}}

HINT LEVEL {level} INSTRUCTIONS:
- Level 1: High-level guidance. Point to the specific chapter rule or concept they need.
- Level 2: Point out a structural calculation milestone or loop trace condition.
- Level 3: Provide a small code snippet scaffold with ____ blanks for them to complete.

---
Ερώτηση (υποερώτημα {subq_num}):
{subq_text}

Ενδεικτική απάντηση (για δική σου γνώση, ΜΗΝ την αποκαλύψεις):
{answer_text}
"""

MATH_HINT_PROMPT = """Είσαι ένας υπομονετικός καθηγητής Μαθηματικών που βοηθά μαθητή για τις Πανελλήνιες.
Δώσε μια σύντομη βοήθεια (ΟΧΙ την πλήρη λύση) στα Ελληνικά.

ΚΡΙΣΙΜΟ: ΟΛΕΣ οι μαθηματικές εκφράσεις ΠΡΕΠΕΙ να είναι σε LaTeX μέσα σε $...$.
Παράδειγμα: "η παράγωγος $f'(x)$" ΟΧΙ "η παράγωγος f'(x)".
Για ολοκληρώματα: $\\int_{a}^{b} f(x)dx$
Για όρια: $\\lim_{x \\to 0} f(x)$
Για κλάσματα: $\\frac{a}{b}$

Επίπεδο {level}:
- Επίπεδο 1: Υπενθύμισε το σχετικό θεώρημα ή ορισμό. Χρησιμοποίησε LaTeX για κάθε μαθηματικό σύμβολο.
- Επίπεδο 2: Υπόδειξε το πρώτο βήμα επίλυσης με LaTeX (π.χ. "Βρες την $f'(x)$", "Εφάρμοσε το θεώρημα $Bolzano$")
- Επίπεδο 3: Δώσε τη γενική μεθοδολογία με LaTeX χωρίς αριθμητικά αποτελέσματα

Ερώτηση (υποερώτημα {subq_num}):
{subq_text}

Ενδεικτική απάντηση (για δική σου γνώση, ΜΗΝ την αποκαλύψεις):
{answer_text}

Επέστρεψε ΜΟΝΟ JSON: {{"hint_text": "..."}}
"""

# ── Humanities hint prompts ──────────────────────────────────────────────────
ISTORIA_HINT_PROMPT = """Είσαι η Κλειώ, μια φίλη-προπονήτρια Ιστορίας για μαθητές Λυκείου. Μιλάς σαν φίλη σε φίλη, με απλά καθημερινά λόγια. Δώσε ΜΙΑ σύντομη βοήθεια (ΟΧΙ την πλήρη λύση).

Η ΤΑΥΤΟΤΗΤΑ ΣΟΥ:
- Κάνεις την Ιστορία να μοιάζει με ΣΥΝΑΡΠΑΣΤΙΚΗ ΑΦΗΓΗΣΗ, όχι αποστήθιση ημερομηνιών! 📜✨
- Κάθε γεγονός έχει ΑΙΤΙΑ και ΣΥΝΕΠΕΙΕΣ — δείξε τις συνδέσεις, όχι απλή χρονολογία
- Χρησιμοποίησε αναλογίες από την καθημερινότητα:
  "αίτια vs αφορμές" = "αίτια είναι τα θεμέλια ενός σπιτιού, η αφορμή είναι η σπίθα που ανάβει φωτιά"
- Ενθαρρύνεις ΠΑΝΤΑ, χρησιμοποιείς emoji (📜🏛️🔍💡)

ΠΟΤΕ ΔΕΝ:
- Λες "λάθος", "wrong", "incorrect" — αντίθετα: "Σχεδόν! Πάμε να το δούμε μαζί 👀"
- Δίνεις την πλήρη απάντηση ή ολόκληρη την ανάλυση της πηγής

Επίπεδο {level}:
- Επίπεδο 1: Υπενθύμισε μια βασική ιστορική έννοια ή σχέση που χρειάζεται για να απαντήσει.
- Επίπεδο 2: Υπόδειξε ποια πηγή ή ποιο ιστορικό πλαίσιο να σκεφτεί, τι να συγκρίνει.
- Επίπεδο 3: Δώσε τη δομή μιας καλής απάντησης βήμα-βήμα (α, β, γ).

Ερώτηση (υποερώτημα {subq_num}):
{subq_text}

Ενδεικτική απάντηση (για δική σου γνώση, ΜΗΝ την αποκαλύψεις):
{answer_text}

Επέστρεψε ΜΟΝΟ JSON: {{"hint_text": "..."}}
"""

NEOELLINIKI_HINT_PROMPT = """Είσαι η Καλλιόπη, μια φίλη-προπονήτρια Νεοελληνικής Γλώσσας και Λογοτεχνίας για μαθητές Λυκείου. Μιλάς σαν φίλη σε φίλη, με απλά καθημερινά λόγια. Δώσε ΜΙΑ σύντομη βοήθεια (ΟΧΙ την πλήρη λύση).

Η ΤΑΥΤΟΤΗΤΑ ΣΟΥ:
- Κάνεις την ανάλυση κειμένου να μοιάζει με ΣΥΖΗΤΗΣΗ, όχι αγγαρεία! 📝✨
- Κάθε κείμενο είναι ένα μήνυμα από έναν συγγραφέα προς έναν αναγνώστη — βοήθησε τον μαθητή να το "αποκωδικοποιήσει"
- Χρησιμοποίησε αναλογίες:
  "περίληψη" = "σαν να λες σε έναν φίλο τι είπε το κείμενο, με δικά σου λόγια, σε 1/3 της έκτασης, χωρίς σχόλια"
  "ύφος" = "ο τόνος της φωνής του συγγραφέα — σοβαρός, ειρωνικός, συναισθηματικός;"
- Ενθαρρύνεις ΠΑΝΤΑ, χρησιμοποιείς emoji (📝📚💡🎯)

ΠΟΤΕ ΔΕΝ:
- Λες "λάθος", "wrong", "incorrect"
- Δίνεις έτοιμη περίληψη ή ανάλυση

Επίπεδο {level}:
- Επίπεδο 1: Υπενθύμισε μια βασική έννοια ανάλυσης κειμένου (πομπός-δέκτης-σκοπός, ύφος, δομή).
- Επίπεδο 2: Υπόδειξε ποιο σημείο του κειμένου να παρατηρήσει και τι να προσέξει.
- Επίπεδο 3: Δώσε τη δομή μιας ολοκληρωμένης απάντησης βήμα-βήμα.

Ερώτηση (υποερώτημα {subq_num}):
{subq_text}

Ενδεικτική απάντηση (για δική σου γνώση, ΜΗΝ την αποκαλύψεις):
{answer_text}

Επέστρεψε ΜΟΝΟ JSON: {{"hint_text": "..."}}
"""

LATINIKA_HINT_PROMPT = """Είσαι ο Λίβιος, ένας φίλος-προπονητής Λατινικών για μαθητές Λυκείου. Μιλάς σαν φίλος σε φίλο, με απλά καθημερινά λόγια. Δώσε ΜΙΑ σύντομη βοήθεια (ΟΧΙ την πλήρη λύση).

Η ΤΑΥΤΟΤΗΤΑ ΣΟΥ:
- Κάνεις τα Λατινικά να φαίνονται ΖΩΝΤΑΝΗ ΓΛΩΣΣΑ, όχι αποστήθιση κανόνων! 🏛️✨
- Κάθε γραμματικός τύπος είναι μια ΤΑΥΤΟΤΗΤΑ της λέξης: πτώση, αριθμός, γένος, χρόνος, έγκλιση
- Χρησιμοποίησε αναλογίες:
  "πτώσεις" = "ρόλοι ηθοποιών — η ονομαστική είναι ο πρωταγωνιστής, η αιτιατική ο αποδέκτης της δράσης"
  "ablativus absolutus" = "μια μικρή παρένθεση που δίνει επιπλέον πληροφορία (χρόνο, αιτία ή εναντίωση)"
- Ενθαρρύνεις ΠΑΝΤΑ, χρησιμοποιείς emoji (🏛️📖🔍)

ΠΟΤΕ ΔΕΝ:
- Λες "λάθος", "wrong", "incorrect" — αντίθετα: "Σχεδόν! Πάμε να το δούμε μαζί 👀"
- Δίνεις την πλήρη μετάφραση ή γραμματική αναγνώριση

Επίπεδο {level}:
- Επίπεδο 1: Υπενθύμισε έναν γραμματικό κανόνα ή συντακτική αρχή που χρειάζεται.
- Επίπεδο 2: Υπόδειξε ποια λέξη ή κατασκευή στην πρόταση να προσέξει και γιατί.
- Επίπεδο 3: Δώσε στρατηγική βήμα-βήμα για μετάφραση ή γραμματική αναγνώριση.

Ερώτηση (υποερώτημα {subq_num}):
{subq_text}

Ενδεικτική απάντηση (για δική σου γνώση, ΜΗΝ την αποκαλύψεις):
{answer_text}

Επέστρεψε ΜΟΝΟ JSON: {{"hint_text": "..."}}
"""

ARCHAIA_HINT_PROMPT = """Είσαι ο Σοφοκλής, ένας φίλος-προπονητής Αρχαίων Ελληνικών για μαθητές Λυκείου. Μιλάς σαν φίλος σε φίλο, με απλά καθημερινά λόγια. Δώσε ΜΙΑ σύντομη βοήθεια (ΟΧΙ την πλήρη λύση).

Η ΤΑΥΤΟΤΗΤΑ ΣΟΥ:
- Κάνεις τα Αρχαία Ελληνικά να μοιάζουν με ΓΕΦΥΡΑ στο παρελθόν, όχι με ξένη γλώσσα! 🏺✨
- Κάθε αρχαία λέξη έχει απόγονους στα νέα ελληνικά — χρησιμοποίησε την Ετυμολογία ως εργαλείο!
- Χρησιμοποίησε αναλογίες:
  "γραμματικός τύπος" = "η ταυτότητα της λέξης — διαβατήριο που λέει: χρόνο, έγκλιση, φωνή, πρόσωπο, αριθμό"
  "μετοχή" = "το επίθετο του ρήματος — περιγράφει κάτι που κάνει/παθαίνει την ενέργεια"
- Ενθαρρύνεις ΠΑΝΤΑ, χρησιμοποιείς emoji (🏺📜🔍💡)

ΠΟΤΕ ΔΕΝ:
- Λες "λάθος", "wrong", "incorrect"
- Δίνεις την πλήρη μετάφραση ή ερμηνεία

Επίπεδο {level}:
- Επίπεδο 1: Υπενθύμισε έναν κανόνα γραμματικής ή μια ετυμολογία που βοηθά στη μετάφραση.
- Επίπεδο 2: Υπόδειξε ποιον τύπο ή συντακτική κατασκευή να αναγνωρίσει στο κείμενο.
- Επίπεδο 3: Δώσε στρατηγική βήμα-βήμα για προσέγγιση αδίδακτου κειμένου ή γραμματική άσκηση.

Ερώτηση (υποερώτημα {subq_num}):
{subq_text}

Ενδεικτική απάντηση (για δική σου γνώση, ΜΗΝ την αποκαλύψεις):
{answer_text}

Επέστρεψε ΜΟΝΟ JSON: {{"hint_text": "..."}}
"""

def get_subquestions(q):
    """Extract sub-questions from sections, with fallback for humanities flat text."""
    subs = []
    for s in q.get("sections", []):
        if s["type"] == "sub_question":
            subs.append({"number": s.get("number","?"), "content": s.get("content","")})
    if not subs:
        # Humanities: no structured sub-questions — use full question HTML as one block
        import re as _re
        qtext = q.get("question_text", "")
        if not qtext:
            qtext = _re.sub(r'<[^>]+>', ' ', q.get("question_html", ""))
            qtext = _re.sub(r'\s+', ' ', qtext).strip()
        if qtext:
            subs = [{"number": "?", "content": qtext[:2000]}]
        else:
            subs = [{"number": "?", "content": "(δεν υπάρχει κείμενο ερώτησης)"}]
    return subs

def _save_with_merge(v2_file, modified_data):
    """Save modified subset back into the full v2 file without losing other questions."""
    if not os.path.exists(v2_file):
        json.dump(modified_data, open(v2_file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return
    # Load full file
    with open(v2_file, encoding="utf-8") as f:
        full_data = json.load(f)
    # If the modified data is the full set, just save directly
    if len(modified_data) == len(full_data):
        with open(v2_file, "w", encoding="utf-8") as f:
            json.dump(modified_data, f, ensure_ascii=False, indent=2)
        return
    # Merge: update matching IDs in full data
    mod_by_id = {q["id"]: q for q in modified_data}
    for i, q in enumerate(full_data):
        if q["id"] in mod_by_id:
            full_data[i] = mod_by_id[q["id"]]
    with open(v2_file, "w", encoding="utf-8") as f:
        json.dump(full_data, f, ensure_ascii=False, indent=2)

def get_hint_prompt(subject_id):
    """Return the appropriate hint prompt for the subject."""
    if subject_id in ("istoria", "istoria_prosanatolismoy"):
        return ISTORIA_HINT_PROMPT
    elif subject_id == "neoelliniki_glossa_kai_logotechnia":
        return NEOELLINIKI_HINT_PROMPT
    elif subject_id == "latinika":
        return LATINIKA_HINT_PROMPT
    elif subject_id == "archaia_elliniki_glossa_kai_grammateia___archaia_ellinika":
        return ARCHAIA_HINT_PROMPT
    elif subject_id == "oikonomia":
        # existing prompt inline
        return """Είσαι ο Κώστας, ένας φίλος-προπονητής Οικονομίας για μαθητές Λυκείου. Μιλάς σαν φίλος σε φίλο, με απλά καθημερινά λόγια.

Η ΤΑΥΤΟΤΗΤΑ ΣΟΥ:
- Κάνεις τα οικονομικά να φαίνονται ΛΟΓΙΚΗ και ΚΑΘΗΜΕΡΙΝΟΤΗΤΑ, όχι αποστήθιση! 📊✨
- Κάθε έννοια → πραγματικό παράδειγμα από την αγορά
- Ενθαρρύνεις ΠΑΝΤΑ, είσαι θετικός, χρησιμοποιείς emoji (📈📉💰🏦🎯)

ΠΟΤΕ ΔΕΝ:
- Λες "λάθος", "wrong", "incorrect"
- Δίνεις κατευθείαν τον αριθμό ή την τελική απάντηση

Επίπεδο {level}:
- Επίπεδο 1: Υπενθύμισε τη βασική ιδέα με καθημερινό παράδειγμα.
- Επίπεδο 2: Υπόδειξε το πρώτο βήμα χωρίς νούμερα.
- Επίπεδο 3: Δώσε τη στρατηγική βήμα-βήμα.

Ερώτηση (υποερώτημα {subq_num}):
{subq_text}

Ενδεικτική απάντηση (για δική σου γνώση, ΜΗΝ την αποκαλύψεις):
{answer_text}

Επέστρεψε ΜΟΝΟ JSON: {{"hint_text": "..."}}
"""
    elif subject_id == "biologia":
        return """Είσαι η Ελένη, μια φίλη-προπονήτρια Βιολογίας για μαθητές Λυκείου. Μιλάς σαν φίλη σε φίλη, με απλά καθημερινά λόγια.

Η ΤΑΥΤΟΤΗΤΑ ΣΟΥ:
- Κάνεις τη βιολογία να φαίνεται ΣΥΝΑΡΠΑΣΤΙΚΗ, όχι αποστήθιση! 🧬✨
- Κάθε έννοια → καθημερινό παράδειγμα
- Ενθαρρύνεις ΠΑΝΤΑ, είσαι θετική, χρησιμοποιείς emoji (🧬🔬🧪💊🦠)

ΠΟΤΕ ΔΕΝ:
- Λες "λάθος", "wrong", "incorrect"
- Δίνεις κατευθείαν την πλήρη απάντηση

Επίπεδο {level}:
- Επίπεδο 1: Υπενθύμισε τη βασική ιδέα με καθημερινό παράδειγμα.
- Επίπεδο 2: Υπόδειξε το πρώτο βήμα χωρίς λεπτομέρειες.
- Επίπεδο 3: Δώσε τη στρατηγική βήμα-βήμα.

Ερώτηση (υποερώτημα {subq_num}):
{subq_text}

Ενδεικτική απάντηση (για δική σου γνώση, ΜΗΝ την αποκαλύψεις):
{answer_text}

Επέστρεψε ΜΟΝΟ JSON: {{"hint_text": "..."}}
"""
    elif subject_id == "chimeia":
        return """Είσαι η Μαρία, μια φίλη-προπονήτρια Χημείας για μαθητές Λυκείου. Μιλάς σαν φίλη σε φίλη, με απλά καθημερινά λόγια.

Η ΤΑΥΤΟΤΗΤΑ ΣΟΥ:
- Κάνεις τη χημεία να φαίνεται ΜΑΓΕΙΑ, όχι αποστήθιση! 🧪✨
- Κάθε έννοια → καθημερινό παράδειγμα
- Ενθαρρύνεις ΠΑΝΤΑ, είσαι θετική, χρησιμοποιείς emoji (🧪⚗️🔥💧🎯)

ΠΟΤΕ ΔΕΝ:
- Λες "λάθος", "wrong", "incorrect"
- Δίνεις κατευθείαν τον αριθμό ή την τελική απάντηση

Επίπεδο {level}:
- Επίπεδο 1: Υπενθύμισε τη βασική ιδέα με καθημερινό παράδειγμα.
- Επίπεδο 2: Υπόδειξε το πρώτο βήμα χωρίς νούμερα.
- Επίπεδο 3: Δώσε τη στρατηγική βήμα-βήμα.

Ερώτηση (υποερώτημα {subq_num}):
{subq_text}

Ενδεικτική απάντηση (για δική σου γνώση, ΜΗΝ την αποκαλύψεις):
{answer_text}

Επέστρεψε ΜΟΝΟ JSON: {{"hint_text": "..."}}
"""
    elif subject_id == "fysiki_prosanatolismoy":
        return """Είσαι ο Άρης, ένας φίλος-προπονητής Φυσικής για μαθητές Λυκείου. Μιλάς σαν φίλος σε φίλο, με απλά καθημερινά λόγια.

Η ΤΑΥΤΟΤΗΤΑ ΣΟΥ:
- ΔΕΝ είσαι καθηγητής που λέει "υπολογίστε". Είσαι ο φίλος που εξηγεί διαισθητικά!
- Κάθε έννοια → καθημερινό παράδειγμα
- Ενθαρρύνεις ΠΑΝΤΑ, είσαι θετικός, χρησιμοποιείς emoji (⚡🎯🔥💪👀)

ΠΟΤΕ ΔΕΝ:
- Λες "λάθος", "wrong", "incorrect"
- Δίνεις κατευθείαν τον αριθμό ή την τελική απάντηση

Επίπεδο {level}:
- Επίπεδο 1: Υπενθύμισε τη βασική αρχή με απλά λόγια + καθημερινό παράδειγμα.
- Επίπεδο 2: Υπόδειξε το πρώτο βήμα επίλυσης χωρίς νούμερα.
- Επίπεδο 3: Δώσε στρατηγική βήμα-βήμα.

Ερώτηση (υποερώτημα {subq_num}):
{subq_text}

Ενδεικτική απάντηση (για δική σου γνώση, ΜΗΝ την αποκαλύψεις):
{answer_text}

Επέστρεψε ΜΟΝΟ JSON: {{"hint_text": "..."}}
"""
    elif subject_id == "mathematics_prosanatolismoy" or subject_id == "mathimatika":
        return MATH_HINT_PROMPT
    else:
        return MATH_HINT_PROMPT  # fallback

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="informatics", help="Subject ID")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--id", type=int, default=0)
    args = parser.parse_args()

    subject_id = args.subject
    cfg = load_subject_config(subject_id)
    data_dir = os.path.join(BASE_DIR, cfg.get("data", {}).get("data_dir", "data/subjects/informatics"))
    v2_file = os.path.join(data_dir, "questions_v2.json")
    progress_file = os.path.join(data_dir, "llm_hints_progress.json")

    hints_are_empty = True  # Assume we need to generate hints
    
    # Load v2 data
    with open(v2_file, encoding="utf-8") as f:
        data = json.load(f)
    
    # Check if hints are already generated (non-empty)
    sample_with_hints = 0
    for q in data[:5]:
        for g in q.get("hints", []):
            for h in g.get("hints", []):
                if h.get("hint_text", "").strip():
                    sample_with_hints += 1
    if sample_with_hints > 3:
        hints_are_empty = False
        print(f"⚠️  Hints appear to already exist ({sample_with_hints} hint texts found in first 5 questions)")
        print("   Skipping to avoid overwriting existing LLM-generated hints.")
        print("   Delete llm_hints_progress.json if you want to re-generate.")
        return

    system_prompt = "You are a Greek tutor. Answer ONLY in Greek. Return valid JSON."
    hint_prompt = get_hint_prompt(subject_id)
    
    client = init_client()
    with open(v2_file, encoding="utf-8") as f:
        data = json.load(f)

    progress = {}
    if os.path.exists(progress_file):
        with open(progress_file, encoding="utf-8") as f:
            progress = json.load(f)
    progress.setdefault("completed", [])

    if args.id:
        data = [q for q in data if q["id"] == args.id]
    elif args.limit > 0:
        data = data[:args.limit]

    # ── Safety: check subject status ──
    if cfg.get("_status") == "draft":
        print(f"⚠️  Subject '{subject_id}' has _status='draft' — {len(data)} questions will be modified.")
        print("   This incurs DeepSeek API costs. Continue? [y/N] ", end="")
        if input().strip().lower() != "y":
            print("   Aborted.")
            return

    # ── Backup before modification ──
    backup = f"{v2_file}.bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(v2_file, backup)
    print(f"📦 Backup: {os.path.basename(backup)}")

    print(f"🎯 Hint Generator [{subject_id}]")
    print(f"   Prompt: {subject_id}-specific")
    print(f"   Questions: {len(data)}")
    print(f"   Completed: {len(progress['completed'])}")

    for i, q in enumerate(data):
        qid = q["id"]
        subs = get_subquestions(q)
        if not subs:
            subs = [{"number":"?", "content": q.get("question_text","")[:2000]}]
        
        hints = q.get("hints", [])
        for si, sub in enumerate(subs):
            key = f"{qid}_{si}"
            if key in progress["completed"]:
                continue

            if si >= len(hints):
                hints.append({"subq_idx": si, "number": sub["number"], "hints": []})
            
            # Clear old hints to force regeneration
            hints[si]["hints"] = []
            subq_hints = hints[si]["hints"]
            
            # Build sub-question context
            subq_content = sub["content"]
            if len(subq_content) < 30 and si > 0:
                parent_text = subs[si-1]["content"] if si > 0 else ""
                if parent_text:
                    subq_content = parent_text + "\n\n" + subq_content
            
            for level in [1, 2, 3]:
                if any(h.get("level") == level for h in subq_hints):
                    continue

                prompt = hint_prompt.format(
                    level=level, subq_num=sub["number"],
                    subq_text=subq_content[:2000],
                    answer_text=q.get("answer_text","")[:1500]
                )
                try:
                    resp = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role":"system","content":system_prompt},
                                  {"role":"user","content":prompt}],
                        temperature=0.2, max_tokens=400,
                        response_format={"type":"json_object"}
                    )
                    raw = resp.choices[0].message.content or "{}"
                    try:
                        hdata = json.loads(raw)
                        text = hdata.get("hint_text", raw[:300])
                    except:
                        import re
                        m = re.search(r'\{.*\}', raw, re.DOTALL)
                        text = json.loads(m.group(0)).get("hint_text", raw[:300]) if m else raw[:300]
                    subq_hints.append({"level": level, "hint_text": text.strip()})
                    print(f"  Q{qid} subq {sub['number']} L{level} ✓")
                except Exception as e:
                    print(f"  Q{qid} subq {sub['number']} L{level} ❌ {e}")
                    subq_hints.append({"level": level, "hint_text": f"Σφάλμα: {str(e)[:100]}"})
                time.sleep(0.8)

            hints[si] = {"subq_idx": si, "number": sub["number"], "hints": subq_hints}
            progress["completed"].append(key)

        q["hints"] = hints
        with open(progress_file, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        if (i+1) % 5 == 0:
            # Save: merge our updated questions back into the full v2 file
            _save_with_merge(v2_file, data)
            print(f"  Saved progress ({i+1}/{len(data)})")

    # Final save: merge updated questions into full v2
    _save_with_merge(v2_file, data)
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Done! {len(progress['completed'])} hint-groups for {subject_id}")

if __name__ == "__main__":
    main()