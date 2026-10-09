#!/usr/bin/env python3
"""Personal skill registry, progressive discovery and recoverable local installation."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
AGENTS = {'codex': '.codex/skills', 'claude': '.claude/skills', 'shared': '.agents/skills'}
IGNORE = {'.git', '.local', '__pycache__', '.DS_Store', '.venv'}
SECRET = re.compile(r'(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{25,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)')

def ensure(ok, message):
    if not ok:
        raise ValueError(message)

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)

def inventory_files(folder):
    for f in sorted(folder.rglob('*')):
        parts = f.relative_to(folder).parts
        if any(x in IGNORE or x.endswith('.pyc') for x in parts):
            continue
        ensure(not f.is_symlink(), f'Skill-internal symlinks are not portable: {f.relative_to(folder)}')
        if f.is_file():
            yield f

def fingerprint(folder):
    h = hashlib.sha256()
    for f in inventory_files(folder):
        h.update(f.relative_to(folder).as_posix().encode())
        h.update(b'\0'); h.update(f.read_bytes()); h.update(b'\0')
    return h.hexdigest()

def source(root, entry):
    p = (root / entry['path']).resolve()
    ensure(p.is_relative_to((root / 'skills').resolve()), 'Skill source escapes skills directory')
    ensure((p / 'SKILL.md').is_file(), f'Missing SKILL.md: {entry["id"]}')
    return p

def registry(root):
    data = read(root / 'catalog.json')
    ensure(data.get('version') == 1, 'Unsupported registry version')
    entries = data['skills']
    ids = set()
    for entry in entries:
        name = entry.get('id', '')
        ensure(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name), f'Invalid skill ID: {name}')
        ensure(name not in ids, f'Duplicate skill ID: {name}')
        ids.add(name)
        ensure(entry.get('kind') in ('managed', 'reference'), f'Unknown kind: {name}')
        for key in ('title', 'summary', 'category', 'origin'):
            ensure(bool(entry.get(key)), f'Missing {key}: {name}')
        if entry['kind'] == 'managed':
            source(root, entry)
    return entries

def find(root, name):
    entry = next((x for x in registry(root) if x['id'] == name), None)
    ensure(entry is not None, f'Unknown skill: {name}')
    return entry

def state_path(root):
    return root / '.local/installations.json'

def state(root):
    return read(state_path(root)) if state_path(root).exists() else {}

def key(home, agent, name):
    return f'{home.resolve()}|{agent}|{name}'

def target(home, agent, name):
    base = (home / AGENTS[agent]).resolve()
    return base / name

def direct_link(path, destination):
    return path.is_symlink() and Path(os.path.abspath(path.parent / os.readlink(path))) == destination

def exists(p):
    return p.exists() or p.is_symlink()

def backup(root, path):
    name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    dst = root / '.local/backups' / name / path.name
    dst.parent.mkdir(parents=True)
    shutil.move(str(path), str(dst))
    return str(dst)

def install(root, home, name, agent, mode='auto', replace=False, dry_run=False):
    entry = find(root, name)
    ensure(entry['kind'] == 'managed', f'{name} is a reference only; inspect and import it first')
    src = source(root, entry)
    sha = fingerprint(src)
    dst = target(home, agent, name)
    db = state(root); k = key(home, agent, name); old = db.get(k)
    mode = ('copy' if os.name == 'nt' else 'link') if mode == 'auto' else mode
    same_link = mode == 'link' and direct_link(dst, src)
    same_copy = (mode == 'copy' and old and old['mode'] == 'copy' and dst.is_dir() and not dst.is_symlink()
                 and old['fingerprint'] == sha and fingerprint(dst) == sha)
    if same_link or same_copy:
        record = dict(skill=name, agent=agent, target=str(dst), source=str(src), mode='link' if same_link else 'copy', fingerprint=sha, previous_backup=old.get('previous_backup') if old else None)
        if not dry_run:
            db[k] = record; write(state_path(root), db)
        return {'skill': name, 'agent': agent, 'status': 'already-current', 'target': str(dst)}
    ensure(not exists(dst) or replace, f'Existing installation preserved: {dst}; compare first, then use --replace to retain a backup')
    if dry_run:
        return {'skill': name, 'agent': agent, 'status': 'would-install', 'mode': mode, 'backup_existing': exists(dst), 'target': str(dst)}
    dst.parent.mkdir(parents=True, exist_ok=True)
    staged = dst.with_name('.hub-stage-' + uuid.uuid4().hex)
    prior = None
    try:
        if mode == 'link':
            staged.symlink_to(src, target_is_directory=True)
        else:
            shutil.copytree(src, staged, ignore=shutil.ignore_patterns(*IGNORE, '*.pyc'))
        if exists(dst):
            prior = backup(root, dst)
        try:
            os.replace(staged, dst)
        except OSError:
            if prior and not exists(dst):
                shutil.move(prior, str(dst))
            raise
    finally:
        if staged.is_symlink():
            staged.unlink()
        elif staged.exists():
            shutil.rmtree(staged)
    db[k] = dict(skill=name, agent=agent, target=str(dst), source=str(src), mode=mode, fingerprint=sha, previous_backup=prior or (old.get('previous_backup') if old else None))
    write(state_path(root), db)
    return {'skill': name, 'agent': agent, 'status': 'installed', 'target': str(dst), 'mode': mode, 'backup': prior}

def inspect_install(root, home, agent, name):
    rec = state(root).get(key(home, agent, name))
    if not rec:
        return {'skill': name, 'agent': agent, 'status': 'not-managed'}
    dst = target(home, agent, name)
    src = source(root, find(root, name))
    if not exists(dst): status = 'missing'
    elif rec['mode'] == 'link': status = 'current' if direct_link(dst, src) else 'replaced-locally'
    elif dst.is_symlink() or not dst.is_dir(): status = 'replaced-locally'
    elif fingerprint(dst) != rec['fingerprint']: status = 'locally-modified'
    else: status = 'current' if fingerprint(src) == rec['fingerprint'] else 'update-available'
    return {'skill': name, 'agent': agent, 'status': status, 'mode': rec['mode'], 'target': str(dst)}

def update(root, home, agent, name, dry_run=False):
    status = inspect_install(root, home, agent, name)['status']
    ensure(status in ('current', 'update-available', 'missing'), f'Refusing to overwrite {status}: {name}')
    rec = state(root)[key(home, agent, name)]
    return install(root, home, name, agent, mode=rec['mode'], replace=status == 'update-available', dry_run=dry_run)

def uninstall(root, home, agent, name, restore_previous=False):
    status = inspect_install(root, home, agent, name)['status']
    ensure(status in ('current', 'update-available', 'missing'), f'Refusing to remove {status}: {name}')
    db = state(root); k = key(home, agent, name); rec = db[k]
    dst = target(home, agent, name); previous = rec.get('previous_backup')
    if restore_previous:
        ensure(previous is not None, 'No previous installation backup recorded')
        old = Path(previous)
        ensure(old.parent.resolve().is_relative_to((root / '.local/backups').resolve()) and exists(old), 'Previous backup is unavailable')
    saved = backup(root, dst) if exists(dst) else None
    if restore_previous:
        shutil.move(previous, str(dst))
    del db[k]; write(state_path(root), db)
    return {'skill': name, 'agent': agent, 'status': 'restored-previous' if restore_previous else 'uninstalled', 'removed_backup': saved}

def validate(root):
    root = root.resolve()
    entries = registry(root)
    errors = []
    for item in entries:
        if item['kind'] != 'managed': continue
        p = source(root, item)
        text = (p/'SKILL.md').read_text(encoding='utf-8')
        m = re.match(r'---\n(.*?)\n---', text, re.S)
        if not m or not re.search(r'^name:\s*'+re.escape(item['id'])+r'\s*$',m[1],re.M) or not re.search(r'^description:\s*\S',m[1],re.M):
            errors.append(f'{item["id"]}: invalid skill frontmatter')
        for f in inventory_files(p):
            rel = f.relative_to(root)
            if f.name.startswith('.env') or f.suffix.lower() in ('.pem','.key','.p12'):
                errors.append(f'{rel}: credential-like filename')
            if f.stat().st_size > 2_000_000:
                errors.append(f'{rel}: unexpectedly large file')
            if SECRET.search(f.read_bytes().decode('utf-8', errors='replace')):
                errors.append(f'{rel}: possible secret; value omitted')
    for label,names in read(root/'profiles.json').items():
        for name in names:
            if not any(x['id']==name and x['kind']=='managed' for x in entries):errors.append(f'Profile {label}: unavailable {name}')
    ensure(not errors, '\n'.join(errors))
    return {'valid': True, 'managed': sum(x['kind']=='managed' for x in entries), 'references': sum(x['kind']=='reference' for x in entries)}

def build(root):
    entries = registry(root); e=html.escape
    cards=[]; rows=[]
    categories={'reporting':'进展汇报','research':'研究分析','documents':'文档处理','collaboration':'多助手协作','development':'开发工具','learning':'学习','management':'技能管理','planning':'任务规划'}
    for v in entries:
        managed=v['kind']=='managed'; label='可安装' if managed else ('版本有分歧' if v.get('review')=='divergent-copies' else '待整理')
        summary=v['summary'] if managed else v['summary'][:180]
        href='../'+v['path']+'/SKILL.md' if managed else '../catalog.json'
        cards.append(f'<article data-kind="{v["kind"]}" data-search="{e((v["id"]+" "+v["title"]+" "+v["category"]+" "+v["summary"]).lower(),quote=True)}"><div class="meta"><span>{e(categories.get(v["category"],v["category"]))}</span><b class="{v["kind"]}">{label}</b></div><h2>{e(v["title"])}</h2><code>{e(v["id"])}</code><p>{e(summary)}</p><a href="{e(href,quote=True)}">'+('读取技能说明' if managed else '查看来源登记')+'</a></article>')
        rows.append(f'| `{v["id"]}` | {v["category"]} | {label} | {summary.replace("|","/")} |')
    markup='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Personal Skill Hub</title><style>
:root{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;color:#20314a;background:#f5f6f8}*{box-sizing:border-box}body{margin:0}main{max-width:1120px;margin:64px auto;padding:0 28px}.eyebrow{font-size:12px;letter-spacing:2px;color:#6c7c90}h1{font-size:40px;letter-spacing:-1px;margin:18px 0}header p{color:#596a7e;line-height:1.8;max-width:720px}.toolbar{display:flex;gap:12px;margin:30px 0 20px}input,select{font:inherit;border:1px solid #d8dfe7;border-radius:9px;padding:13px;background:white;color:inherit}input{flex:1;min-width:0}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}article{background:white;border:1px solid #e3e7ed;border-radius:12px;padding:24px;display:flex;flex-direction:column}article[hidden]{display:none}.meta{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:#6c7c90}.meta b{font-weight:500;padding:2px 6px;border-radius:4px}.managed{color:#226947;background:#edf7f0}.reference{color:#746038;background:#f8f2e8}h2{font-size:19px;margin:18px 0 7px}code{font-size:12px;overflow-wrap:anywhere;color:#687a90}article p{font-size:14px;line-height:1.8;flex:1;color:#526278}a{color:#315f99;text-underline-offset:4px;font-size:13px}.count{font-size:12px;color:#748295;margin-bottom:20px}footer{margin:28px 0;font-size:12px;color:#748295;line-height:1.8}button:focus-visible,input:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid #a5c5ec;outline-offset:3px}@media(max-width:850px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:540px){main{margin:32px auto;padding:0 18px}.grid{grid-template-columns:1fr}.toolbar{flex-direction:column}h1{font-size:31px}}
</style><main><header><div class="eyebrow">PERSONAL LIBRARY · 私有技能库</div><h1>找到需要的技能，再按需加载。</h1><p>统一保存自己维护的技能，记录其他技能的来源。安装时选择设备和 agent，阅读时从目录进入说明，再深入需要的细节。</p></header><div class="toolbar"><input id="q" aria-label="搜索技能" placeholder="搜索名称、用途或关键词"><select id="kind" aria-label="安装状态"><option value="managed">可安装</option><option value="">全部技能</option><option value="reference">待整理与版本分歧</option></select></div><div id="count" class="count" aria-live="polite"></div><section class="grid">'''+''.join(cards)+'''</section><footer>这是本地目录页面，没有发布到公开网站。可安装表示源码已纳管，不表示运行依赖已安装或所有功能已在本机验证。<br><a href="../README.md">安装与维护说明</a> · <a href="../catalog.json">Agent 读取索引</a></footer></main><script>
const q=document.querySelector('#q'),kind=document.querySelector('#kind'),cards=[...document.querySelectorAll('article')];function filter(){let n=0;for(const c of cards){c.hidden=!(c.dataset.search.includes(q.value.toLowerCase())&&(!kind.value||c.dataset.kind===kind.value));if(!c.hidden)n++}document.querySelector('#count').textContent=`显示 ${n} / ${cards.length} 项技能`}q.addEventListener('input',filter);kind.addEventListener('change',filter);filter();</script></html>'''
    (root/'docs').mkdir(exist_ok=True)
    (root/'docs/index.html').write_text(markup,encoding='utf-8')
    (root/'docs/catalog.md').write_text('# 技能目录\n\n由 `hub.py build` 生成；编辑 catalog.json。\n\n| Skill | 分类 | 状态 | 用途 |\n|---|---|---|---|\n'+'\n'.join(rows)+'\n',encoding='utf-8')
    return str(root/'docs/index.html')

def selected_names(root,args):
    names=list(args.names)
    if args.profile:
        profiles=read(root/'profiles.json');ensure(args.profile in profiles,'Unknown profile');names+=profiles[args.profile]
    if args.all: names += [v['id'] for v in registry(root) if v['kind']=='managed']
    ensure(names,'Choose a skill, --profile, or --all')
    return list(dict.fromkeys(names))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home',type=Path,default=Path.home(),help='Target home; also useful for isolated tests')
    subs=p.add_subparsers(dest='command',required=True)
    l=subs.add_parser('list');l.add_argument('query',nargs='?',default='');l.add_argument('--available',action='store_true')
    s=subs.add_parser('show');s.add_argument('name');s.add_argument('--instructions',action='store_true')
    i=subs.add_parser('install');i.add_argument('names',nargs='*');i.add_argument('--profile');i.add_argument('--all',action='store_true');i.add_argument('--agent',action='append',choices=AGENTS,required=True);i.add_argument('--mode',choices=['auto','link','copy'],default='auto');i.add_argument('--replace',action='store_true');i.add_argument('--dry-run',action='store_true')
    u=subs.add_parser('update');u.add_argument('--agent',action='append',choices=AGENTS);u.add_argument('--dry-run',action='store_true')
    r=subs.add_parser('uninstall');r.add_argument('name');r.add_argument('--agent',choices=AGENTS,required=True);r.add_argument('--restore-previous',action='store_true')
    subs.add_parser('doctor');subs.add_parser('check');subs.add_parser('build')
    a=p.parse_args();root=ROOT;home=a.home.expanduser().resolve()
    if a.command=='list':
        result=[{'id':x['id'],'title':x['title'],'kind':x['kind'],'category':x['category'],'summary':x['summary'][:180]} for x in registry(root) if a.query.lower() in (x['id']+' '+x['title']+' '+x['category']+' '+x['summary']).lower() and (not a.available or x['kind']=='managed')]
    elif a.command=='show':
        result=find(root,a.name)
        if a.instructions:
            ensure(result['kind']=='managed','Reference has no bundled instructions')
            print((source(root,result)/'SKILL.md').read_text(encoding='utf-8'));return
        if result['kind']=='managed':
            result=dict(result,resources=[f.relative_to(root).as_posix() for f in inventory_files(source(root,result))])
    elif a.command=='install':
        names=selected_names(root,a)
        # Preflight all destinations so a known conflict cannot leave a partial batch.
        for agent in dict.fromkeys(a.agent):
            for name in names:install(root,home,name,agent,a.mode,a.replace,True)
        result=[install(root,home,n,g,a.mode,a.replace,a.dry_run) for g in dict.fromkeys(a.agent) for n in names]
    elif a.command in ('doctor','update'):
        records=[r for k,r in state(root).items() if k.startswith(str(home)+'|')]
        if a.command=='doctor':result=[inspect_install(root,home,r['agent'],r['skill']) for r in records]
        else:
            result=[]
            for r in records:
                if not a.agent or r['agent'] in a.agent:
                    try:result.append(update(root,home,r['agent'],r['skill'],a.dry_run))
                    except ValueError as ex:result.append({'skill':r['skill'],'agent':r['agent'],'error':str(ex)})
    elif a.command=='uninstall':result=uninstall(root,home,a.agent,a.name,a.restore_previous)
    elif a.command=='check':result=validate(root)
    else:result=build(root)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if isinstance(result,list) and any('error' in x for x in result if isinstance(x,dict)):sys.exit(1)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
