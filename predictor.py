#!/usr/bin/env python3
"""
Ranking predictor for next exam questions based on past appearance and cyclicality.

Formula: Priority = (Years Since Last Appearance) × (Average Historical Points)

Usage: python3 predictor.py
"""

import json
import os
from collections import defaultdict

CURRENT_YEAR = 2026

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "subjects", "informatics")
QUESTIONS_FILE = os.path.join(DATA_DIR, "questions_classified.json")


def clean_tag(tag):
    """Remove leftover numbering prefixes from material names."""
    import re
    cleaned = re.sub(r'^\d+\.\d+(\.\d+)?\s*', '', tag).strip()
    return cleaned if cleaned else tag


def calculate_topic_priorities(exam_data):
    """
    Calculates a dynamic focus priority score for each exam tag.
    Formula Priority = (Years Since Last Appearance * Average Historical Points Allocation)
    """
    tag_history = defaultdict(list)
    tag_points = defaultdict(list)

    # Map past questions
    for exam in exam_data:
        year = exam["year"]
        if year is None:
            continue
        points = exam["points"]
        for tag in exam["conceptual_tags"]:
            cleaned = clean_tag(tag)
            tag_history[cleaned].append(year)
            tag_points[cleaned].append(points)

    priorities = {}
    details = {}
    for tag, years in tag_history.items():
        last_seen = max(years)
        years_absent = CURRENT_YEAR - last_seen
        appearances = len(years)
        avg_points = sum(tag_points[tag]) / appearances
        # If a major topic (avg > 10 points) has been skipped for 2+ years, it becomes critical SOS
        priority_score = years_absent * avg_points
        priorities[tag] = round(priority_score, 2)
        details[tag] = {
            "appearances": appearances,
            "years_seen": sorted(set(years)),
            "last_seen": last_seen,
            "years_absent": years_absent,
            "avg_points": round(avg_points, 2),
            "total_points": sum(tag_points[tag]),
        }

    # Sort topics by highest priority score
    ranked = sorted(priorities.items(), key=lambda x: x[1], reverse=True)
    return ranked, details


def main():
    print("=" * 70)
    print(f"  EXAM TOPIC PRIORITY RANKING  (Current Year: {CURRENT_YEAR})")
    print("=" * 70)

    if not os.path.exists(QUESTIONS_FILE):
        print(f"ERROR: {QUESTIONS_FILE} not found. Run build_questions.py first.")
        return

    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        questions = json.load(f)

    print(f"\n  Loaded {len(questions)} questions.")

    # Show year distribution
    years_avail = sorted(set(q["year"] for q in questions if q["year"]))
    print(f"  Available years: {years_avail}")
    print(f"  Years since latest data: {CURRENT_YEAR - max(years_avail)}")

    ranked, details = calculate_topic_priorities(questions)

    # Filter out noise tags
    noise = {"ΠΛΗΡΟΦΟΡΙΚΗ:", "ΑΕΠΠ:", ""}
    ranked = [(t, s) for t, s in ranked if t not in noise]

    print(f"\n  {'Rank':<5} {'Topic':<50} {'Priority':>8}  {'#App':>5}  {'Last':>5}  {'AvgPts':>7}")
    print(f"  {'-'*5} {'-'*50} {'-'*8}  {'-'*5}  {'-'*5}  {'-'*7}")

    for rank, (tag, score) in enumerate(ranked, 1):
        d = details[tag]
        print(f"  {rank:<5} {tag:<50} {score:>8.2f}  {d['appearances']:>5}  {d['last_seen']:>5}  {d['avg_points']:>7.2f}")

    # Top 10 SOS topics
    print(f"\n  {'='*70}")
    print(f"  TOP 10 TOPICS MOST LIKELY TO APPEAR IN {CURRENT_YEAR}")
    print(f"  {'='*70}")
    for tag, score in ranked[:10]:
        d = details[tag]
        print(f"  [{d['avg_points']:.1f} pts avg] {tag}")
        print(f"     Appeared in: {d['years_seen']} | Last seen: {d['last_seen']} "
              f"({d['years_absent']} years ago) | Total: {d['appearances']}x")

    # Recommendations by part
    print(f"\n  {'='*70}")
    print(f"  PREDICTED COMPOSITION FOR ΘΕΜΑ 2 & ΘΕΜΑ 4")
    print(f"  {'='*70}")

    thema2_tags = defaultdict(list)
    thema4_tags = defaultdict(list)
    for q in questions:
        for tag in q["conceptual_tags"]:
            cleaned = clean_tag(tag)
            if cleaned in noise:
                continue
            if q["part"] == "Θέμα 2":
                thema2_tags[cleaned].append(q["year"])
            elif q["part"] == "Θέμα 4":
                thema4_tags[cleaned].append(q["year"])

    for part_name, part_tags in [("Θέμα 2", thema2_tags), ("Θέμα 4", thema4_tags)]:
        # Top tags for this part, by priority
        part_ranked = []
        for tag in part_tags:
            if tag in dict(ranked):
                part_ranked.append((tag, dict(ranked)[tag]))
        part_ranked.sort(key=lambda x: x[1], reverse=True)
        print(f"\n  {part_name}:")
        for tag, score in part_ranked[:5]:
            d = details[tag]
            print(f"     {tag} (priority: {score:.1f}, avg pts: {d['avg_points']}, appeared {d['appearances']}x)")

    print(f"\n  {'='*70}")


if __name__ == "__main__":
    main()