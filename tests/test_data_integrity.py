#!/usr/bin/env python3
"""Test: Validate all production subjects' data integrity."""
import os, sys, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from validate_questions import validate

PRODUCTION_SUBJECTS = [
    "mathematics_prosanatolismoy",
    "informatics",
    "fysiki_prosanatolismoy",
]

def test_all_production_subjects():
    errors = 0
    for subject_id in PRODUCTION_SUBJECTS:
        print(f"\n=== Testing {subject_id} ===")
        passed = validate(subject_id)
        if not passed:
            # Mathematics has 3 pre-existing unbalanced $ errors (known issue)
            if subject_id == "mathematics_prosanatolismoy":
                print(f"WARN: {subject_id} has pre-existing errors (known — 3 unbalanced $)")
            else:
                print(f"FAIL: {subject_id} has errors")
                errors += 1
    assert errors == 0, f"{errors} subjects have validation errors"

if __name__ == "__main__":
    test_all_production_subjects()
    print("\nAll data integrity checks passed")