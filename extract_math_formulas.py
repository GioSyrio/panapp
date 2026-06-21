#!/usr/bin/env python3
"""Extract formula images from math DOCX files to static/images/math_formulas/"""
import json, zipfile, os, shutil, sys

DOCX_DIR = 'data/subjects/mathematics/raw/docx'
OUT_DIR = 'static/images/math_formulas'
ITEMS_FILE = 'trapeza_data_1_3_17/items_raw.json'

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    items = json.load(open(ITEMS_FILE))['items']
    qids = [item['id'] for item in items]
    
    total_files = 0
    for qid in qids:
        docx_path = os.path.join(DOCX_DIR, f'{qid}-0.doc')
        if not os.path.exists(docx_path):
            continue
        
        q_dir = os.path.join(OUT_DIR, str(qid))
        os.makedirs(q_dir, exist_ok=True)
        
        try:
            with zipfile.ZipFile(docx_path, 'r') as zf:
                for f in zf.namelist():
                    if f.startswith('word/media/'):
                        fname = os.path.basename(f)
                        out_path = os.path.join(q_dir, fname)
                        if not os.path.exists(out_path):
                            data = zf.read(f)
                            with open(out_path, 'wb') as wf:
                                wf.write(data)
                            total_files += 1
        except Exception as e:
            print(f'  Q{qid}: {e}', file=sys.stderr)
    
    print(f'Extracted {total_files} files for {len(os.listdir(OUT_DIR))} questions')

if __name__ == '__main__':
    main()