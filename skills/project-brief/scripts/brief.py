#!/usr/bin/env python3
"""Render project briefs and expose bounded, progressively disclosed evidence."""
import argparse
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote

STATES = {
    'verified': ('pass', '✓', '已验证', '指定场景有通过记录'),
    'in_progress': ('running', '◷', '进行中', '正在做，还没达到条件'),
    'blocked': ('blocked', '!', '受阻', '有条件挡住下一步'),
    'unverified': ('unverified', '○', '未验证', '还缺少完整通过证据'),
}
ASSETS = Path(__file__).resolve().parent.parent / 'assets'

def check(ok, message):
    if not ok:
        raise ValueError(message)

def text_fields(obj, names):
    check(isinstance(obj, dict), 'Expected object')
    for name in names:
        check(isinstance(obj.get(name), str) and obj[name].strip(), f'Missing text: {name}')

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def stamp(value, date_ok=False):
    check(isinstance(value, str), 'Timestamp must be text')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date_ok and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return
    check(parsed.tzinfo is not None, 'Timestamp must include timezone')

def index_read(path):
    d = load(path)
    check(d.get('version') == 1, 'Unsupported version')
    text_fields(d, ['project', 'snapshot_at', 'headline', 'context', 'update'])
    stamp(d['snapshot_at'])
    check(isinstance(d.get('items'), list) and d['items'], 'items must be nonempty')
    ids = []
    for item in d['items']:
        text_fields(item, ['id', 'title', 'status', 'summary', 'detail'])
        check(re.fullmatch(r'[A-Za-z0-9_-]+', item['id']), 'Invalid item ID')
        check(item['status'] in STATES, 'Unknown status')
        ids.append(item['id'])
    check(len(ids) == len(set(ids)), 'Duplicate item ID')
    text_fields(d.get('next'), ['title', 'owner', 'precondition', 'user_action_now'])
    for seq in (d['next'].get('steps'), d.get('limitations')):
        check(isinstance(seq, list) and all(isinstance(x, str) and x.strip() for x in seq), 'Expected text list')
    return d

def item_read(path, item):
    target = (path.parent / item['detail']).resolve()
    check(target.is_relative_to(path.parent.resolve()), 'Item detail escapes brief directory')
    d = load(target)
    text_fields(d, ['acceptance', 'boundary'])
    check(not any(k in d for k in ('id', 'title', 'status', 'summary')), 'Item metadata belongs only in index')
    check(isinstance(d.get('observations'), list), 'observations must be a list')
    for ob in d['observations']:
        text_fields(ob, ['label', 'text'])
    check(isinstance(d.get('evidence'), list), 'evidence must be a list')
    seen = set()
    for ev in d['evidence']:
        text_fields(ev, ['id', 'summary', 'observed_at'])
        check(re.fullmatch(r'[A-Za-z0-9_-]+', ev['id']), 'Invalid evidence ID')
        check(ev['id'] not in seen, 'Duplicate evidence ID')
        seen.add(ev['id'])
        stamp(ev['observed_at'], date_ok=True)
        s = ev.get('source')
        text_fields(s, ['path', 'sha256'])
        check(not re.match(r'^[a-zA-Z][\w+.-]*://', s['path']), 'Only local evidence paths supported')
        check(re.fullmatch(r'[a-f0-9]{64}', s['sha256']), 'Invalid SHA-256')
        check(('pointer' in s) != ('lines' in s), 'Choose exactly one source selector')
        if 'pointer' in s:
            check(isinstance(s['pointer'], str) and s['pointer'].startswith('/'), 'Nonempty JSON Pointer required')
            check(not re.search(r'~(?![01])', s['pointer']), 'Invalid JSON Pointer escape')
        else:
            v = s['lines']
            check(isinstance(v, list) and len(v) == 2 and all(type(x) is int for x in v) and 1 <= v[0] <= v[1], 'Invalid line range')
    if item['status'] == 'verified':
        check(bool(d['evidence']), 'Verified item requires evidence')
    if item['status'] == 'blocked':
        text_fields(d.get('blocker'), ['reason', 'owner', 'resume'])
    return d

def selected_source(path, ev):
    s = ev['source']
    target = (path.parent / s['path']).resolve()
    raw = target.read_bytes()
    check(digest(raw) == s['sha256'], f'Evidence changed: {ev["id"]}; recheck selected facts before refreshing snapshot')
    if 'pointer' in s:
        value = json.loads(raw)
        for part in s['pointer'][1:].split('/'):
            key = part.replace('~1', '/').replace('~0', '~')
            if isinstance(value, list):
                check(bool(re.fullmatch(r'0|[1-9][0-9]*', key)), 'Invalid array index')
                check(int(key) < len(value), f'JSON Pointer index out of range: {s["pointer"]} in {s["path"]}')
                value = value[int(key)]
            else:
                check(isinstance(value, dict) and key in value, f'JSON Pointer not found: {s["pointer"]} in {s["path"]}')
                value = value[key]
    else:
        lines = raw.decode('utf-8').splitlines()
        first, last = s['lines']
        check(last <= len(lines), 'Line range exceeds source length')
        value = '\n'.join(f'{i+1}: {lines[i]}' for i in range(first-1, last))
    return {'evidence': ev, 'hash_verified': True, 'selected_content': value}

def all_details(path, d):
    return [item_read(path, i) for i in d['items']]

def display_time(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if len(value) == 10:
        return dt.strftime("%Y年%m月%d日")
    offset = dt.strftime("%z")
    zone = f"UTC{offset[:3]}:{offset[3:]}"
    return dt.strftime("%Y年%m月%d日 %H:%M") + f"（{zone}）"

def render(d, details, generated_at):
    e = lambda s: html.escape(str(s), quote=True)
    css = (ASSETS / 'style.css').read_text(encoding='utf-8')
    data_hash = digest((dump([d, details]) + css).encode())
    bits = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<meta name="brief-generated-at" content="{e(generated_at)}">',
        f'<meta name="brief-content-sha256" content="{data_hash}">',
        f'<title>{e(d["project"])} · 项目进展</title><style>{css}</style></head><body><main class="sheet">',
        f'<header class="topbar"><div class="project">{e(d["project"])}</div><div class="timestamp">项目记录快照<br><b>{e(display_time(d["snapshot_at"]))}</b></div></header>',
        f'<section class="intro"><h1>{e(d["headline"])}</h1><p class="lead">{e(d["context"])}</p></section>',
        '<div class="legend" aria-label="固定状态词表">']
    for klass, symbol, label, meaning in STATES.values():
        bits.append(f'<div class="legend-item"><span class="symbol {klass}" aria-hidden="true">{symbol}</span><div><div class="legend-name">{label}</div><div class="legend-explain">{meaning}</div></div></div>')
    bits.append(f'</div><div class="content"><section><div class="sectionbar"><h2>能力进展</h2><span class="count">本页关注的 {len(details)} 项能力</span></div>')
    for item, detail in zip(d['items'], details):
        klass, symbol, label, _ = STATES[item['status']]
        bits.append(f'<details class="capability" id="item-{e(item["id"])}"><summary class="cap-summary"><div class="cap-main"><div class="cap-title"><span class="cap-id">{e(item["id"])}</span>{e(item["title"])}</div><p class="cap-desc">{e(item["summary"])}</p></div><div class="cap-action"><span class="badge {klass}">{symbol} {label}</span><span class="more">查看依据 <i class="chevron" aria-hidden="true"></i></span></div></summary><div class="detail-content"><dl class="facts">')
        rows = [{'label': '通过条件', 'text': detail['acceptance']}] + detail['observations']
        if 'blocker' in detail:
            rows += [{'label': k, 'text': detail['blocker'][v]} for k,v in [('障碍','reason'),('由谁解除','owner'),('之后做什么','resume')]]
        for ob in rows:
            bits.append(f'<dt>{e(ob["label"])}</dt><dd>{e(ob["text"])}</dd>')
        bits.append(f'</dl><p class="boundary">{e(detail["boundary"])}</p>')
        for ev in detail['evidence']:
            s = ev['source']
            locator = s.get('pointer') or f'行 {s["lines"][0]}–{s["lines"][1]}'
            src = Path(s['path'])
            href = src.as_uri() if src.is_absolute() else quote(s['path'], safe='/')
            bits.append(f'<details class="evidence-record" id="evidence-{e(item["id"])}-{e(ev["id"])}"><summary>{e(ev["id"])} · {e(ev["summary"])}</summary><p>观察时间：{e(display_time(ev["observed_at"]))}</p><p>原始位置：<code>{e(s["path"])}</code><br>片段：<code>{e(locator)}</code></p><a href="{e(href)}">打开本地原文件</a><p class="boundary">这是本地原文件链接；HTTP 预览或其他机器可能无法打开。Agent 可按本项编号读取指定片段。</p></details>')
        bits.append('</div></details>')
    n = d['next']
    bits.append(f'</section><aside class="next"><h2>下一步要验证什么</h2><p class="next-target">{e(n["title"])}</p><p class="next-desc">执行者：{e(n["owner"])}</p><ol class="steps">')
    bits.extend(f'<li>{e(step)}</li>' for step in n['steps'])
    bits.append(f'</ol><div class="precondition"><strong>前置条件</strong>{e(n["precondition"])}</div><p class="no-action">{e(n["user_action_now"])}</p></aside></div>')
    bits.append('<details class="records"><summary>记录范围与读取入口 <i class="chevron" aria-hidden="true"></i></summary><ul>')
    bits.extend(f'<li>{e(v)}</li>' for v in d['limitations'])
    bits.append(f'</ul><p><a href="index.json">简报索引</a> · 各项展开后可追溯原始证据。记录截止时间与页面生成时间分别保留。</p><p class="file-name">页面生成：{e(display_time(generated_at))}</p></details><footer class="tail"><span>{e(d["update"])}</span><span>按需展开，查看结果与边界。</span></footer></main>')
    bits.append('<script>let previous=[];addEventListener("beforeprint",()=>{previous=[...document.querySelectorAll("details")].map(d=>[d,d.open]);previous.forEach(([d])=>d.open=true)});addEventListener("afterprint",()=>previous.forEach(([d,o])=>d.open=o));</script></body></html>')
    return '\n'.join(bits)

def emit(value, limit):
    data = dump(value)
    if len(data) > limit:
        print(dump({'truncated': True, 'total_chars': len(data), 'preview': data[:limit], 'next': 'Use a narrower selector or explicitly increase --max-chars (max 20000)'}))
    else:
        print(data)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('read', 'validate', 'render'):
        cmd = sub.add_parser(name)
        cmd.add_argument('index', type=Path)
        if name == 'read':
            cmd.add_argument('--item')
            cmd.add_argument('--evidence')
            cmd.add_argument('--source', action='store_true')
            cmd.add_argument('--max-chars', type=int, default=4000)
        elif name == 'validate':
            cmd.add_argument('--sources', action='store_true')
        else:
            cmd.add_argument('--check', action='store_true')
    a = p.parse_args()
    path = a.index.resolve()
    d = index_read(path)
    if a.command == 'read':
        check(100 <= a.max_chars <= 20000, '--max-chars must be 100..20000')
        check(not a.evidence or a.item, '--evidence requires --item')
        check(not a.source or a.evidence, '--source requires --evidence')
        out = d
        if a.item:
            item = next((i for i in d['items'] if i['id'] == a.item), None)
            check(item is not None, f'Unknown item {a.item}')
            detail = item_read(path, item)
            out = {'item': item, 'detail': detail}
            if a.evidence:
                ev = next((ev for ev in detail['evidence'] if ev['id'] == a.evidence), None)
                check(ev is not None, f'Unknown evidence {a.evidence}')
                out = selected_source(path, ev) if a.source else ev
        emit(out, a.max_chars)
        return
    details = all_details(path, d)
    if a.command == 'validate':
        if a.sources:
            for detail in details:
                for ev in detail['evidence']:
                    selected_source(path, ev)
        print(dump({'valid': True, 'items': len(details), 'original_sources_checked': a.sources}))
    else:
        target = path.parent / 'brief.html'
        now = datetime.now().astimezone().isoformat(timespec='seconds')
        if a.check:
            old = target.read_text(encoding='utf-8')
            m = re.search(r'<meta name="brief-generated-at" content="([^"]+)">', old)
            check(m is not None, 'Missing generation timestamp')
            check(old == render(d, details, html.unescape(m[1])), 'HTML differs from current data/template; render again')
            print('HTML matches current snapshot and template')
        else:
            target.write_text(render(d, details, now), encoding='utf-8')
            print(str(target))

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, IndexError, StopIteration) as error:
        print(dump({'error': str(error)}), file=sys.stderr)
        sys.exit(1)
