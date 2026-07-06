import json, os
subjects = ['chimeia','biologia','mathimatika','oikonomia','istoria','istoria_prosanatolismoy','latinika','neoelliniki_glossa_kai_logotechnia','archaia_elliniki_glossa_kai_grammateia___archaia_ellinika']
for slug in subjects:
    vp = f'data/subjects/{slug}/questions_v2.json'
    v2 = json.load(open(vp, encoding='utf-8'))
    for q in v2: q['hints'] = []
    json.dump(v2, open(vp, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    pp = f'data/subjects/{slug}/llm_hints_progress.json'
    if os.path.exists(pp): os.remove(pp)
    print(f'{slug}: cleared')
print('\nNow run one at a time:')
for slug in subjects:
    print(f'  caffeinate -i python3 build_llm_hints.py --subject {slug}')