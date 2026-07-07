#!/usr/bin/env python3
"""Test: Answer detection for all subjects."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import _is_student_answer

def test_math_detection():
    # Should detect math answers
    assert _is_student_answer("η παράγωγος της f είναι f'(x)=3x^2", "mathematics_prosanatolismoy") == True
    assert _is_student_answer("f(x)=x^2 άρα είναι συνεχής", "mathematics_prosanatolismoy") == True
    assert _is_student_answer("το όριο στο 0 είναι 3", "mathematics_prosanatolismoy") == True
    # Should NOT detect questions
    assert _is_student_answer("τι είναι παράγωγος;", "mathematics_prosanatolismoy") == False
    assert _is_student_answer("πώς λύνω αυτό;", "mathematics_prosanatolismoy") == False

def test_code_detection():
    # Should detect code answers
    assert _is_student_answer("Διάβασε x\nΓΙΑ i ΑΠΟ 1 ΜΕΧΡΙ 10", "informatics") == True
    assert _is_student_answer("Όσο x>0 επανάλαβε", "informatics") == True
    # Should NOT detect questions
    assert _is_student_answer("τι είναι διάβασε;", "informatics") == False

def test_physics_detection():
    # Should detect physics answers
    assert _is_student_answer("η δύναμη είναι F=ma", "fysiki_prosanatolismoy") == True
    assert _is_student_answer("η ταχύτητα μετά την κρούση", "fysiki_prosanatolismoy") == True
    assert _is_student_answer("εφαρμόζουμε διατήρηση της ενέργειας", "fysiki_prosanatolismoy") == True
    # Should NOT detect questions
    assert _is_student_answer("πώς βρίσκω την ταχύτητα;", "fysiki_prosanatolismoy") == False

def test_none_detection():
    # Draft subjects with answer_detection="none" should not trigger
    assert _is_student_answer("η παράγωγος είναι", "biologia") == False
    assert _is_student_answer("ΔΙΑΒΑΣΕ x", "biologia") == False

def test_long_message():
    # Messages >100 chars with newlines auto-detect
    msg = "x\n" * 51  # >100 chars
    assert _is_student_answer(msg, "mathematics_prosanatolismoy") == True

if __name__ == "__main__":
    tests = [test_math_detection, test_code_detection, test_physics_detection, test_none_detection, test_long_message]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {test.__name__}: assertion failed — {e}")
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed")