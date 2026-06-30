#!/usr/bin/env python3
"""Zip all raw directories for new subjects to save space"""
import os, zipfile, shutil

subjects = [
    'archaia_elliniki_glossa_kai_grammateia___archaia_ellinika',
    'biologia', 'chimeia', 'fysiki_prosanatolismoy',
    'istoria', 'istoria_prosanatolismoy', 'latinika',
    'mathimatika', 'neoelliniki_glossa_kai_logotechnia', 'oikonomia'
]

for slug in subjects:
    raw_dir = f'data/subjects/{slug}/raw'
    zip_path = f'data/subjects/{slug}/raw.zip'
    
    if not os.path.exists(raw_dir):
        print(f'{slug}: no raw dir, skipping')
        continue
    
    if os.path.exists(zip_path):
        os.remove(zip_path)
    
    print(f'{slug}: zipping...')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(raw_dir):
            for f in files:
                fp = os.path.join(root, f)
                zf.write(fp, os.path.relpath(fp, raw_dir))
    
    zip_size = os.path.getsize(zip_path) / (1024*1024)
    file_count = len(zipfile.ZipFile(zip_path).namelist())
    shutil.rmtree(raw_dir)
    print(f'  {zip_size:.0f}MB, {file_count} files, raw dir removed')

print('Done!')