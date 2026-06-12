#!/usr/bin/env python3
"""
prompt_loader.py — Dynamic prompt loading per subject.

Reads the subject config (subjects/{subject}.json) and imports the
corresponding prompt module. Falls back to prompts/informatics.py
if no config is specified.

Usage:
    from prompt_loader import load_prompts
    prompts = load_prompts("informatics")
    # Use prompts.GREEK_TUTOR_SYSTEM_PROMPT, prompts.EVALUATION_SYSTEM_PROMPT, etc.
"""

import json, os, sys, importlib.util

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUBJECTS_DIR = os.path.join(BASE_DIR, "subjects")

def load_prompts(subject_id="informatics"):
    """Load the prompt module for a given subject."""
    config_path = os.path.join(SUBJECTS_DIR, f"{subject_id}.json")
    
    if not os.path.exists(config_path):
        print(f"WARNING: Subject config not found: {config_path}, falling back to informatics")
        config_path = os.path.join(SUBJECTS_DIR, "informatics.json")
    
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)
    
    prompt_file = config.get("prompt_file", "prompts/informatics.py")
    prompt_path = os.path.join(BASE_DIR, prompt_file)
    
    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    
    # Import the module dynamically
    spec = importlib.util.spec_from_file_location(
        f"prompts_{subject_id}", prompt_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"prompts_{subject_id}"] = module
    spec.loader.exec_module(module)
    
    return module