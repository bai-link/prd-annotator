#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prd_scan.py — 扫描原型 HTML，抽取可锚定元素，输出 scan.json

支持两类原型：
  1) 配置驱动 + 函数渲染的单页应用（页面 section 空壳，由 renderXxx() 注入）
  2) 普通静态 HTML（按 id / class / 标题抽卡片与按钮）

用法：
  python prd_scan.py prototype.html [-o scan.json]

输出结构见 references/anchor-rules.md。
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime
from html.parser import HTMLParser

TOOL = 'prd_scan/1.0'
LITERAL = re.compile(r"'([^']*)'")


def sha8(s):
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:8]


def line_of(t, pos):
    return t.count('\n', 0, pos) + 1


def ctx(t, pos, span=110):
    return t[max(0, pos - span):pos + span]


def read(path):
    with io.open(path, encoding='utf-8', errors='replace') as f:
        return f.read()


def js_str_map(t, name):
    """解析 const NAME={k:'v', 'k-2':'v'} 形式的简单对象映射"""
    m = re.search(r'const\s+' + name + r'\s*=\s*\{(.*?)\}\s*;', t, re.S)
    if not m:
        return {}
    return dict(re.findall(r"['\"]?([A-Za-z_][\w\-]*)['\"]?\s*:\s*'([^']*)'", m.group(1)))


def js_str_array(t, name):
    m = re.search(r'const\s+' + name + r'\s*=\s*\[(.*?)\]\s*;', t, re.S)
    if not m:
        return []
    return re.findall(r"'([^']*)'", m.group(1))


def literals(expr):
    return [x.strip() for x in LITERAL.findall(expr) if x.strip()]


def add(out, seen, item):
    if item['anchor'] in seen:
        return
    seen.add(item['anchor'])
    out.append(item)


def scan_pages(t, titles, out, seen):
    pats = [
        r'<section[^>]*class="[^"]*\bpage\b[^"]*"[^>]*id="p-([\w\-]+)"',
        r'<section[^>]*id="p-([\w\-]+)"[^>]*class="[^"]*\bpage\b',
    ]
    for pat in pats:
        for m in re.finditer(pat, t):
            key = m.group(1)
            add(out, seen, {
                'kind': 'page', 'key': key, 'page': key,
                'anchor': 'page:' + key,
                'title': titles.get(key, key),
                'line': line_of(t, m.start()),
                'hash': sha8(ctx(t, m.start())),
                'ref': '<section id="p-%s">' % key,
            })


def scan_actions(t, out, seen):
    i = 0
    body = t  # Include reassigned actions() wrappers; results are candidates, not runtime permissions.
    for m in re.finditer(r"a\.push\(\s*\[\s*'([\w\-]+)'\s*,\s*(.+?)\]\s*\)", body):
        key, labelexpr = m.group(1), m.group(2)
        labels = literals(labelexpr)
        add(out, seen, {
            'kind': 'action', 'key': key, 'page': '',
            'anchor': 'action:' + key,
            'title': ' / '.join(labels) or key,
            'labels': labels,
            'line': line_of(t, i + m.start()),
            'hash': sha8(labelexpr),
            'ref': "actions(): a.push(['%s', ...])" % key,
        })


def scan_dialogs(t, out, seen):
    for m in re.finditer(r"showModal\(\s*'([^']{2,40})'", t):
        title = m.group(1).strip().rstrip('·').strip()
        key = re.sub(r'\s+', '', title)
        add(out, seen, {
            'kind': 'dialog', 'key': key, 'page': '',
            'anchor': 'dialog:' + key,
            'title': title,
            'line': line_of(t, m.start()),
            'hash': sha8(ctx(t, m.start(), 60)),
            'ref': "showModal('%s', ...)" % title,
        })


def scan_fields(t, out, seen):
    for m in re.finditer(r"\b(?:field|area)\(\s*'([\w\-]+)'\s*,\s*'([^']*)'", t):
        fid, label = m.group(1), m.group(2)
        add(out, seen, {
            'kind': 'field', 'key': fid, 'page': '',
            'anchor': 'field:' + fid,
            'title': label or fid,
            'line': line_of(t, m.start()),
            'hash': sha8(label),
            'ref': "field('%s', '%s')" % (fid, label),
        })


def scan_states(t, out, seen):
    for s in js_str_array(t, 'FLOW'):
        add(out, seen, {
            'kind': 'state', 'key': s, 'page': '',
            'anchor': 'state:' + s,
            'title': s,
            'line': line_of(t, t.find('const FLOW')),
            'hash': sha8(s),
            'ref': 'FLOW 状态集合',
        })


def scan_rules(t, out, seen):
    rules = {
        'guard': '操作前置校验（身份 + 状态 + 可用动作）',
        'move': '状态迁移与留痕（写入日志、消息、归档）',
        'log': '变更日志（操作人/前后状态/备注/版本号）',
        'final': '终态判定（归档后不可再操作）',
        'own': '提案人本人判定',
        'canSee': '数据可见范围判定',
        'late': '逾期判定（派生标记，不改变状态）',
    }
    for name, desc in rules.items():
        m = re.search(r'function\s+' + name + r'\s*\(', t)
        if not m:
            continue
        add(out, seen, {
            'kind': 'rule', 'key': name, 'page': '',
            'anchor': 'rule:' + name,
            'title': desc,
            'line': line_of(t, m.start()),
            'hash': sha8(ctx(t, m.start(), 200)),
            'ref': 'function %s()' % name,
        })


def scan_cards(t, out, seen):
    """卡片/区块：class="card" 后紧跟 <h3>标题</h3>"""
    for m in re.finditer(r'class="card"[^>]*>', t):
        seg = t[m.end():m.end() + 320]
        h = re.search(r'<h3>([^<]{1,32})</h3>', seg)
        if not h:
            continue
        title = h.group(1).strip()
        if any(ch in title for ch in ("'", '+', '$', '{', '}')):
            continue
        key = re.sub(r'[\s/·]+', '', title)[:18]
        add(out, seen, {
            'kind': 'card', 'key': key, 'page': '',
            'anchor': 'card:' + key,
            'title': title,
            'line': line_of(t, m.start()),
            'hash': sha8(ctx(t, m.start(), 80)),
            'ref': 'div.card > h3',
        })


def scan_static_fallback(t, out, seen):
    """静态 HTML 兜底：可交互元素按 id / 主要按钮抽取"""
    for m in re.finditer(r'<(button|a|input|select)[^>]*\bid="([\w\-]+)"[^>]*>(.{0,60}?)</\1>', t, re.S):
        tag, eid, inner = m.group(1), m.group(2), m.group(3)
        label = re.sub(r'<[^>]+>', '', inner).strip()[:24]
        add(out, seen, {
            'kind': 'control', 'key': eid, 'page': '',
            'anchor': 'control:' + eid,
            'title': label or eid,
            'line': line_of(t, m.start()),
            'hash': sha8(inner),
            'ref': '<%s id="%s">' % (tag, eid),
        })


class ExplicitAnchors(HTMLParser):
    def __init__(self, out, seen):
        super().__init__()
        self.out, self.seen = out, seen
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        anchor = attrs.get('data-prd-anchor')
        if not anchor and tag in ('input', 'textarea', 'select', 'button') and attrs.get('id'):
            anchor = 'control:' + attrs['id']
        if not anchor:
            return
        if not re.fullmatch(r'[a-z]+:[^\s]+', anchor):
            raise ValueError('无效显式锚点: ' + anchor)
        if attrs.get('data-prd-anchor') and anchor in self.seen:
            raise ValueError('重复显式锚点: ' + anchor)
        add(self.out, self.seen, {'kind': anchor.split(':', 1)[0], 'key': anchor.split(':', 1)[1],
            'anchor': anchor, 'page': attrs.get('data-prd-page', ''),
            'title': attrs.get('aria-label') or attrs.get('title') or anchor,
            'line': self.getpos()[0], 'hash': sha8(self.get_starttag_text()),
            'ref': self.get_starttag_text(), 'confidence': 'explicit' if attrs.get('data-prd-anchor') else 'id'})
    handle_startendtag = handle_starttag


def scan_explicit(t, out, seen):
    ExplicitAnchors(out, seen).feed(t)


def main():
    ap = argparse.ArgumentParser(description='扫描原型 HTML，输出可锚定元素清单')
    ap.add_argument('html', help='原型 HTML 路径')
    ap.add_argument('-o', '--out', help='输出 scan.json（默认 <原型目录>/.prd/scan.json）')
    ap.add_argument('--kind', help='只输出指定类型，逗号分隔：page,action,dialog,field,state,rule,card,control')
    args = ap.parse_args()

    path = os.path.abspath(args.html)
    if not os.path.isfile(path):
        sys.exit('找不到文件：' + path)
    t = read(path)
    titles = js_str_map(t, 'TITLES')

    out, seen = [], set()
    scan_explicit(t, out, seen)
    scan_pages(t, titles, out, seen)
    scan_actions(t, out, seen)
    scan_dialogs(t, out, seen)
    scan_fields(t, out, seen)
    scan_states(t, out, seen)
    scan_rules(t, out, seen)
    scan_cards(t, out, seen)
    scan_static_fallback(t, out, seen)

    if args.kind:
        keep = {k.strip() for k in args.kind.split(',')}
        out = [e for e in out if e['kind'] in keep]

    out.sort(key=lambda e: ({'page': 0, 'card': 1, 'action': 2, 'dialog': 3,
                             'field': 4, 'state': 5, 'rule': 6, 'control': 7}.get(e['kind'], 9),
                            e['line']))

    data = {
        'tool': TOOL,
        'scanned_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'prototype': {
            'path': path,
            'name': os.path.basename(path),
            'bytes': os.path.getsize(path),
            'lines': t.count('\n') + 1,
            'sha1': hashlib.sha1(t.encode('utf-8')).hexdigest(),
        },
        'counts': {},
        'elements': out,
    }
    for e in out:
        data['counts'][e['kind']] = data['counts'].get(e['kind'], 0) + 1

    dst = args.out or os.path.join(os.path.dirname(path), '.prd', 'scan.json')
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    with io.open(dst, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print('扫描完成：%d 个元素 %s' % (len(out), json.dumps(data['counts'], ensure_ascii=False)))
    print('输出：' + dst)


if __name__ == '__main__':
    main()
