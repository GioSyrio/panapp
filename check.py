import json, os
for slug in sorted(os.listdir('data/subjects')):
    vp = f'data/subjects/{slug}/questions_v2.json'
    pp = f'data/subjects/{slug}/llm_hints_progress.json'
    if not os.path.exists(vp): continue
    total = len(json.load(open(vp, encoding='utf-8')))
    done = len(json.load(open(pp, encoding='utf-8')).get('completed',[])) if os.path.exists(pp) else 0
    pct = int(done*100//max(total,1))
    icon = 'Y' if pct>=100 else ('>' if done>0 else 'X')
    print(f'{icon} {slug}: {done}/{total} ({pct}%)')

all_done = True
protected = {'mathematics','mathimatika_prosanatolismoy','informatics','pliroforiki'}
for s in os.listdir('data/subjects'):
    if s.startswith('.'): continue
    if not os.path.isdir(f'data/subjects/{s}'): continue
    vp = f'data/subjects/{s}/questions_v2.json'
    if not os.path.exists(vp): continue
    if s in protected: continue
    total = len(json.load(open(vp, encoding='utf-8')))
    pp = f'data/subjects/{s}/llm_hints_progress.json'
    done = len(json.load(open(pp, encoding='utf-8')).get('completed',[])) if os.path.exists(pp) else 0
    if done < total: all_done = False

print('ALL DONE' if all_done else 'STILL IN PROGRESS')