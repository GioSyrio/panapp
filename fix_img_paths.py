#!/usr/bin/env python3
"""Fix ALL diagram image paths: /static/images/ → /images/"""
import json, re
v2 = json.load(open('data/subjects/mathematics/questions_v2.json', encoding='utf-8'))
cnt = 0
for q in v2:
    parts = q.get('question_html_parts', [])
    new_parts = []
    for p in parts:
        new_p = re.sub(r'src="/static/images/', 'src="/images/', p)
        new_parts.append(new_p)
        if new_p != p: cnt += 1
    q['question_html_parts'] = new_parts
    q['question_html'] = '\n'.join(new_parts)
    url = q.get('diagram_url', '')
    if url and url.startswith('static/'):
        q['diagram_url'] = url.replace('static/', '', 1)
        cnt += 1
with open('data/subjects/mathematics/questions_v2.json', 'w', encoding='utf-8') as f:
    json.dump(v2, f, ensure_ascii=False, indent=2)
print(f'Fixed {cnt} items')
for qid in [25235, 25257, 27318]:
    q = next(x for x in v2 if x['id']==qid)
    print(f"Q{qid}: url={q.get('diagram_url','?')}")
    for p in q.get('question_html_parts', []):
        if 'src=' in p:
            print(f"  src={p[p.find('src=')+5:p.find('src=')+65]}")
            break