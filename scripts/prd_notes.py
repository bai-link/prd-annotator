#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prd_notes.py — 原型 PRD 备注的单一事实源管理器（notes.json）

子命令：
  init    由 scan.json 生成备注骨架（按锚点，不覆盖已有）
  upsert  新增/更新一条备注（按 anchor 匹配，默认保留已填字段）
  merge   批量增量合并 patch.json
  check   体检：覆盖率 / 孤儿 / 元素已变更 / 字段缺失
  render  渲染为结构化 PRD 备注文档（Markdown）
  inject  生成带旁注角标的副本 annotated.html（原型本体不改）
  list    列出备注清单

设计要点：
  - anchor 是唯一键，绑定原型代码结构（page/action/dialog/state/rule/card/field）
  - 备注与原型双向可追溯：anchor + source.line + hash
  - 增量更新：只按 anchor upsert，其余条目原样保留；hash 变化只标"需复核"，不改文案
"""
import argparse
import io
import json
import os
import re
import sys
import hashlib
import tempfile
from datetime import datetime

SCHEMA = 1
KIND_CN = {'page': '页面', 'card': '卡片', 'action': '操作', 'dialog': '弹窗',
           'field': '字段', 'state': '状态', 'rule': '规则', 'control': '控件',
           'custom': '自定义标注'}
KIND_ORDER = ['page', 'card', 'action', 'dialog', 'field', 'state', 'rule', 'control', 'custom']
FIELDS = ['func', 'interaction', 'rules', 'edges', 'accept']
FIELD_CN = {'func': '功能描述', 'interaction': '交互逻辑', 'rules': '业务规则',
            'edges': '边界情况', 'accept': '验收要点'}


# ---------------- 基础读写 ----------------

def read_json(p):
    with io.open(p, encoding='utf-8') as f:
        return json.load(f)


def write_json(p, data):
    folder = os.path.dirname(os.path.abspath(p))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_notes(p):
    if not os.path.isfile(p):
        sys.exit('找不到备注文件：%s（先执行 init 或提供 --notes 路径）' % p)
    return read_json(p)


def save_notes(p, data):
    data['meta']['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    write_json(p, data)


def make_id(anchor):
    """anchor → 可读编号，如 page:finance → page.finance"""
    return re.sub(r'[:/\s]+', '.', anchor).strip('.')


def split_list(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in re.split(r'[|｜;\n]+', v or '') if x.strip()]


def new_note(el):
    return {
        'id': make_id(el['anchor']),
        'anchor': el['anchor'],
        'kind': el['kind'],
        'page': el.get('page', ''),
        'title': el.get('title', ''),
        'req': '',
        'func': '',
        'interaction': [],
        'rules': [],
        'edges': [],
        'accept': [],
        'status': 'draft',
        'version': 1,
        'updated': '',
        'hash': el.get('hash', ''),
        'source': {'line': el.get('line', 0), 'ref': el.get('ref', '')},
    }


# ---------------- init ----------------

def cmd_init(args):
    scan = read_json(args.scan)
    kinds = {k.strip() for k in (args.kinds or 'page,action,dialog,state,rule').split(',')}
    notes = []
    if os.path.isfile(args.out):
        notes = read_json(args.out).get('notes', [])
    have = {n['anchor'] for n in notes}
    added = 0
    for el in scan['elements']:
        if el['kind'] not in kinds or el['anchor'] in have:
            continue
        notes.append(new_note(el))
        have.add(el['anchor'])
        added += 1
    data = {
        'meta': {
            'schema': SCHEMA,
            'prototype': scan['prototype']['name'],
            'prototype_path': scan['prototype']['path'],
            'prototype_sha1': scan['prototype']['sha1'],
            'version': (read_json(args.out)['meta'].get('version', 0) + 1) if os.path.isfile(args.out) else 1,
            'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'generator': 'prd-annotator',
        },
        'notes': notes,
    }
    save_notes(args.out, data)
    print('初始化完成：新增 %d 条骨架，共 %d 条 → %s' % (added, len(notes), args.out))


# ---------------- upsert ----------------

def apply_fields(note, args, overwrite=True):
    if args.title is not None:
        note['title'] = args.title
    if args.req is not None:
        note['req'] = args.req
    for f in FIELDS:
        v = getattr(args, f, None)
        if v is None:
            continue
        val = split_list(v) if f != 'func' else v
        if not overwrite and note.get(f):
            continue
        note[f] = val
    if args.status:
        note['status'] = args.status
    if args.page is not None:
        note['page'] = args.page


def cmd_upsert(args):
    data = load_notes(args.notes)
    notes = data['notes']
    hit = [n for n in notes if n['anchor'] == args.anchor]
    if hit:
        n = hit[0]
        before = json.dumps({k: n.get(k) for k in ['req'] + FIELDS}, ensure_ascii=False)
        apply_fields(n, args, overwrite=args.overwrite)
        after = json.dumps({k: n.get(k) for k in ['req'] + FIELDS}, ensure_ascii=False)
        if before != after:
            n['version'] = n.get('version', 1) + 1
            n['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        action = '更新'
    else:
        n = {
            'id': make_id(args.anchor), 'anchor': args.anchor,
            'kind': (args.kind or args.anchor.split(':')[0]),
            'page': args.page or '', 'title': args.title or '',
            'req': '', 'func': '', 'interaction': [], 'rules': [], 'edges': [], 'accept': [],
            'status': 'draft', 'version': 1, 'updated': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'hash': '', 'source': {'line': 0, 'ref': '手工新增'},
        }
        apply_fields(n, args, overwrite=True)
        notes.append(n)
        action = '新增'
    save_notes(args.notes, data)
    print('%s：%s（%s）' % (action, n['anchor'], n.get('req') or '无需求编号'))


# ---------------- merge ----------------

def cmd_merge(args):
    data = load_notes(args.notes)
    patch = read_json(args.patch)
    if not isinstance(patch, (dict, list)):
        sys.exit('补丁必须是对象或数组')
    items = patch if isinstance(patch, list) else patch.get('notes', [])
    if not isinstance(items, list) or any(not isinstance(it, dict) or not isinstance(it.get('anchor'), str) for it in items):
        sys.exit('补丁条目必须有字符串 anchor')
    notes = data['notes']
    idx = {n['anchor']: n for n in notes}
    added = updated = skipped = 0
    for it in items:
        anchor = it.get('anchor')
        if not anchor:
            print('跳过无 anchor 条目：%r' % it.get('title', ''))
            skipped += 1
            continue
        if anchor in idx:
            n = idx[anchor]
            changed = False
            for k in ['title', 'req', 'status', 'page', 'css', 'evidence', 'decision'] + FIELDS:
                if k not in it:
                    continue
                v = it[k]
                if k in FIELDS and k != 'func':
                    v = split_list(v)
                if not args.overwrite and n.get(k):
                    continue
                if n.get(k) != v:
                    n[k] = v
                    changed = True
            if changed:
                n['version'] = n.get('version', 1) + 1
                n['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
                updated += 1
        else:
            n = new_note({'anchor': anchor, 'kind': it.get('kind', anchor.split(':')[0]),
                          'page': it.get('page', ''), 'title': it.get('title', ''), 'hash': ''})
            n['source'] = {'line': it.get('line', 0), 'ref': 'merge 导入'}
            for k in ['req', 'func', 'status', 'css', 'evidence', 'decision']:
                if k in it:
                    n[k] = it[k]
            for k in FIELDS:
                if k == 'func':
                    continue
                if k in it:
                    n[k] = split_list(it[k])
            n['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            notes.append(n)
            idx[anchor] = n
            added += 1
    deprecated = 0
    for a in ((patch.get('deleted') or []) if isinstance(patch, dict) else []):
        n = idx.get(a)
        if n and n.get('status') != 'deprecated':
            n['status'] = 'deprecated'
            n['version'] = n.get('version', 1) + 1
            n['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            deprecated += 1
    save_notes(args.notes, data)
    print('合并完成：新增 %d，更新 %d，标废弃 %d，跳过 %d，共 %d 条'
          % (added, updated, deprecated, skipped, len(notes)))


# ---------------- check ----------------

def cmd_check(args):
    data = load_notes(args.notes)
    notes = data['notes']
    scan = read_json(args.scan) if args.scan else None
    by_anchor = {n['anchor']: n for n in notes}
    print('备注总数：%d' % len(notes))
    problems = 0
    if scan:
        kinds = {k.strip() for k in (args.kinds or 'page,action,dialog,state,rule').split(',')}
        els = [e for e in scan['elements'] if e['kind'] in kinds]
        covered = 0
        changed, orphan = [], []
        for el in els:
            n = by_anchor.get(el['anchor'])
            if n and n.get('status') not in ('deprecated', 'n/a'):
                covered += 1
                if n.get('hash') and el.get('hash') and n['hash'] != el['hash']:
                    changed.append((el, n))
        scanned = {e['anchor'] for e in scan['elements']}
        problems += len(els) - sum(1 for e in els if e['anchor'] in by_anchor and by_anchor[e['anchor']].get('status') != 'deprecated')
        orphan = [n for n in notes if n['anchor'] not in scanned and n['kind'] not in ('control', 'custom') and n.get('status') not in ('deprecated', 'n/a')]
        print('扫描元素：%d · 已覆盖：%d（%.0f%%）' % (len(els), covered, 100.0 * covered / max(1, len(els))))
        if changed:
            print('\n[需复核] 原型元素已改动，备注可能过期（%d）：' % len(changed))
            for el, n in changed:
                print('  - %-28s L%-5s %s' % (el['anchor'], el.get('line'), n.get('title', '')))
            problems += len(changed)
        if orphan:
            print('\n[孤儿] 备注对应的元素在原型中已找不到（保留不删，确认后可标 deprecated）：')
            for n in orphan:
                print('  - %-28s %s' % (n['anchor'], n.get('title', '')))
            problems += len(orphan)
    lack = [n for n in notes if n.get('status') not in ('n/a', 'deprecated') and (not n.get('req') or not n.get('func') or not n.get('rules') or not n.get('edges'))]
    if lack:
        print('\n[待补] 缺需求编号/功能描述/业务规则（%d）：' % len(lack))
        for n in lack[:40]:
            miss = [FIELD_CN[k] for k in ['func', 'rules', 'edges'] if not n.get(k)]
            if not n.get('req'):
                miss.insert(0, '需求编号')
            print('  - %-28s %s ← 缺 %s' % (n['anchor'], n.get('title', ''), '、'.join(miss)))
        if len(lack) > 40:
            print('  ... 其余 %d 条省略' % (len(lack) - 40))
    problems += len(notes) - len(by_anchor)
    problems += sum(n.get('status') not in ('draft','confirmed','n/a','deprecated') for n in notes)
    confirmed = sum(1 for n in notes if n.get('status') == 'confirmed')
    na = sum(1 for n in notes if n.get('status') == 'n/a')
    print('\n状态：已确认 %d · 草稿 %d · 非需求项 %d' % (confirmed, len(notes) - confirmed - na, na))
    print('体检结论：%s' % ('通过，可交付评审' if problems == 0 and not lack else '存在 %d 项待处理' % (problems + len(lack))))


    if problems or lack:
        raise SystemExit(1)


# ---------------- render ----------------

def md_list(items, ordered=False):
    if not items:
        return '—'
    out = []
    for i, x in enumerate(items, 1):
        out.append(('%d. %s' % (i, x)) if ordered else ('- %s' % x))
    return '<br>'.join(out)


def cmd_render(args):
    data = load_notes(args.notes)
    meta, notes = data['meta'], data['notes']
    if args.status:
        notes = [n for n in notes if n.get('status') in args.status.split(',')]
    scan = read_json(args.scan) if args.scan else None
    cov = ''
    if scan:
        kinds = {'page', 'action', 'dialog', 'state', 'rule'}
        els = {e['anchor'] for e in scan['elements'] if e['kind'] in kinds}
        c = sum(1 for n in notes if n['anchor'] in els)
        cov = ' · 覆盖 %d/%d（%.0f%%）' % (c, len(els), 100.0 * c / max(1, len(els)))
    confirmed = sum(1 for n in notes if n.get('status') == 'confirmed')

    L = []
    L.append('# %s · 原型 PRD 备注' % os.path.splitext(meta.get('prototype', '原型'))[0])
    L.append('')
    L.append('> 原型文件：`%s`%s' % (meta.get('prototype', ''), ('（sha1 `%s`）' % meta['prototype_sha1'][:12]) if meta.get('prototype_sha1') else ''))
    L.append('> 备注版本：v%s · 更新：%s · 条目：%d（已确认 %d）%s' % (meta.get('version', 1), meta.get('updated', ''), len(notes), confirmed, cov))
    L.append('> 本文档由 `notes.json` 渲染生成，请勿手工编辑；改备注请用 `prd_notes.py upsert/merge`。')
    L.append('')

    # 总览
    L.append('## 一、备注总览')
    L.append('')
    L.append('| # | 需求编号 | 元素 | 类型 | 锚点 | 状态 |')
    L.append('| --- | --- | --- | --- | --- | --- |')
    for i, n in enumerate(notes, 1):
        L.append('| %d | %s | %s | %s | `%s` | %s |' % (
            i, n.get('req') or '—', n.get('title', ''), KIND_CN.get(n['kind'], n['kind']),
            n['anchor'], status_cn(n)))
    L.append('')

    # 按页面分组
    pages = [n for n in notes if n['kind'] == 'page']
    page_keys = [n['page'] or n['key'] if 'key' in n else n['page'] for n in pages]
    L.append('## 二、按页面详述')
    L.append('')
    if not pages:
        L.append('_（暂无页面级备注）_')
        L.append('')
    for p in pages:
        pkey = p['page']
        L.append('### %s　`page:%s`' % (p.get('title', pkey), pkey))
        L.append('')
        L.append(render_note(p))
        sub = [n for n in notes if n.get('page') == pkey and n['anchor'] != p['anchor']]
        if sub:
            L.append('')
            L.append('**本页关联元素**')
            L.append('')
            for n in sub:
                L.append(render_note(n))
        L.append('')

    # 跨页面
    cross = [n for n in notes if n['kind'] != 'page' and not n.get('page')]
    if cross:
        L.append('## 三、跨页面组件（弹窗 / 状态 / 规则 / 字段）')
        L.append('')
        for kind in ['dialog', 'card', 'action', 'field', 'state', 'rule', 'control']:
            grp = [n for n in cross if n['kind'] == kind]
            if not grp:
                continue
            L.append('### %s（%d 条）' % (KIND_CN.get(kind, kind), len(grp)))
            L.append('')
            for n in grp:
                L.append(render_note(n))
            L.append('')

    # 附录
    L.append('## 四、追溯说明')
    L.append('')
    L.append('| 项 | 说明 |')
    L.append('| --- | --- |')
    L.append('| 锚点规则 | `page:<页面>` / `action:<操作key>` / `dialog:<弹窗标题>` / `state:<状态名>` / `rule:<函数名>` / `card:<卡片标题>` / `field:<字段id>` |')
    L.append('| 源码定位 | 备注中的 L 行号为扫描时定位，供研发快速跳转；元素重构后行号可能偏移，以锚点为准 |')
    L.append('| 增量维护 | 新增/修改备注按锚点 upsert，不重建文档；原型元素改动后 `check` 会标出「需复核」 |')
    L.append('| 备注状态 | `draft` 草稿待评审；`confirmed` 已与产品/研发确认；`deprecated` 元素已下线 |')
    L.append('')
    L.append('> 本备注文档为产品设计参考，具体实施请结合公司合规与法务要求确认。')

    out = '\n'.join(L)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with io.open(args.out, 'w', encoding='utf-8') as f:
            f.write(out)
        print('已渲染：%s（%d 条备注）' % (args.out, len(notes)))
    else:
        sys.stdout.write(out)


STATUS_CN = {'confirmed': '已确认', 'draft': '草稿', 'n/a': '非需求项', 'deprecated': '已废弃'}


def status_cn(n):
    return STATUS_CN.get(n.get('status', 'draft'), '草稿')


def render_note(n):
    t = []
    t.append('#### %s　%s' % (n.get('req') or '（待编号）', n.get('title', '')))
    t.append('')
    t.append('| 项 | 内容 |')
    t.append('| --- | --- |')
    t.append('| 锚点 | `%s` |' % n['anchor'])
    for f in ['func'] + FIELDS[1:]:
        val = n.get(f) or ''
        if f != 'func' and isinstance(val, list):
            val = md_list(val, ordered=(f == 'interaction'))
        t.append('| %s | %s |' % (FIELD_CN[f], val.replace('\n', '<br>') if val else '—'))
    src = n.get('source') or {}
    t.append('| 源码定位 | L%s `%s` |' % (src.get('line') or '—', src.get('ref', '')))
    t.append('| 版本 | v%s · %s · %s |' % (n.get('version', 1), n.get('updated') or '—', status_cn(n)))
    t.append('')
    return '\n'.join(t)


# ---------------- inject ----------------

PANEL_CSS = """
.prd-badge{position:absolute;z-index:9998;width:18px;height:18px;border:none;padding:0;border-radius:50%;
 background:#2f6bff;color:#fff;font:700 11px/18px -apple-system,'Microsoft YaHei',sans-serif;text-align:center;
 cursor:pointer;box-shadow:0 1px 5px rgba(47,107,255,.45);opacity:.55;transition:opacity .15s,transform .15s}
.prd-badge:hover{opacity:1;transform:scale(1.15)}
.prd-pop{position:fixed;z-index:10001;width:356px;max-width:88vw;max-height:76vh;overflow:auto;background:#fff;
 border:1px solid #e3e8f0;border-radius:12px;box-shadow:0 14px 38px rgba(15,23,42,.2);
 font:13px/1.7 -apple-system,'Microsoft YaHei',sans-serif;color:#1f2937;padding:14px 16px 12px}
.prd-pop .phd{display:flex;align-items:flex-start;gap:8px}
.prd-pop .pt{font-weight:700;font-size:14px;color:#111827;flex:1;line-height:1.5}
.prd-pop .chip{flex:none;background:#eef4ff;color:#2f6bff;border:1px solid #d5e3ff;border-radius:10px;
 padding:0 8px;font-size:11px;line-height:18px;white-space:nowrap;margin-top:2px}
.prd-pop .pm{color:#9aa3b2;font-size:11px;margin:2px 0 6px;word-break:break-all}
.prd-pop .pk{display:inline-block;color:#fff;background:#2f6bff;border-radius:4px;padding:0 6px;font-size:11px;
 margin:10px 0 4px;line-height:17px}
.prd-pop .pk.gray{background:#94a3b8}
.prd-pop ul{margin:0;padding-left:18px}
.prd-pop li{margin:2px 0;color:#374151}
.prd-pop p{margin:0;color:#374151}
.prd-pop .pft{display:flex;gap:8px;margin-top:12px;padding-top:10px;border-top:1px dashed #e8edf5}
.prd-pop .pft button{border:1px solid #d5e3ef;background:#f8fafc;border-radius:6px;padding:3px 11px;
 font-size:12px;cursor:pointer;color:#334155}
.prd-pop .pft button.pri{background:#2f6bff;border-color:#2f6bff;color:#fff}
.prd-pop .pft .sp{flex:1}
.prd-pop .ed{width:100%;box-sizing:border-box;border:1px solid #d5e3ef;border-radius:6px;padding:5px 8px;
 font:12px/1.6 -apple-system,'Microsoft YaHei',sans-serif;margin:2px 0 6px;resize:vertical}
.prd-pop .tip{color:#98a2b3;font-size:11px;margin:0 0 4px}
.prd-hit{outline:2px solid #2f6bff !important;outline-offset:2px;border-radius:4px;transition:outline .15s}
.prd-fabs{position:fixed;right:18px;bottom:18px;z-index:9999;display:flex;gap:8px}
.prd-fab{height:32px;padding:0 12px;border:1px solid #dbe3ef;border-radius:16px;background:#fff;color:#4b5563;
 font:600 12px/30px -apple-system,'Microsoft YaHei',sans-serif;cursor:pointer;box-shadow:0 3px 12px rgba(15,23,42,.12)}
.prd-fab.off{opacity:.55}
body.prd-picking,body.prd-picking *{cursor:crosshair !important}
body.prd-picking .prd-badge,body.prd-picking .prd-fabs,body.prd-picking .prd-pickhover{outline:none !important}
.prd-pickhover{outline:2px dashed #f59e0b !important;outline-offset:1px;background:rgba(245,158,11,.08) !important}
.prd-toast{position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:10002;background:#111827;color:#fff;
 border-radius:8px;padding:7px 16px;font:13px/1.5 -apple-system,'Microsoft YaHei',sans-serif;box-shadow:0 8px 22px rgba(0,0,0,.25)}
"""

PANEL_JS = r"""
(function(){
  var RAW = window.__PRD_NOTES__ || [];
  if(!RAW.length) return;
  var PATCH_KEY='prd-annotator-patch-v2:'+location.pathname;
  var PATCH=loadPatch(), NOTES=[];
  var pop=null, curAnchor=null, hitEl=null, showBadges=true, picking=false, pickHover=null;
  var KIND_CN={page:'页面',action:'操作',dialog:'弹窗',state:'状态',rule:'规则',custom:'自定义'};
  function clone(o){return JSON.parse(JSON.stringify(o));}
  function el(tag,cls){var d=document.createElement(tag); if(cls)d.className=cls; return d;}
  function norm(s){return String(s==null?'':s).replace(/\s+/g,'');}
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  function lines(v){return String(v||'').split('\n').map(function(x){return x.trim();}).filter(Boolean);}
  function loadPatch(){try{return JSON.parse(localStorage.getItem(PATCH_KEY)||'{}');}catch(e){return {};}}
  function savePatch(){try{localStorage.setItem(PATCH_KEY,JSON.stringify(PATCH));}catch(e){}}
  function build(){
    var out=[];
    for(var i=0;i<RAW.length;i++){
      var n=clone(RAW[i]), p=PATCH[n.anchor];
      if(p && p.__deleted__) continue;
      if(p){ ['title','func','rules','interaction','edges'].forEach(function(k){ if(p[k]!==undefined) n[k]=p[k]; }); n.status='edited'; }
      out.push(n);
    }
    for(var a in PATCH){
      var q=PATCH[a];
      if(q.__deleted__) continue;
      if(q.__new__ && !RAW.some(function(r){return r.anchor===a;})){ var nn=clone(q); delete nn.__new__; nn.status='edited'; out.push(nn); }
    }
    NOTES=out;
  }
  function byAnchor(a){for(var i=0;i<NOTES.length;i++){if(NOTES[i].anchor===a)return NOTES[i];}return null;}
  function hostOf(n){
    var explicit=document.querySelector('[data-prd-anchor="'+CSS.escape(n.anchor)+'"]');if(explicit)return explicit;

    if(n.kind==='page'){var s=document.getElementById('p-'+n.page); return s?(s.querySelector('.ph')||s):null;}
    if(n.kind==='action'){
      var key=n.key||'', scopes=[document.getElementById('p-'+n.page),document.getElementById('logicDialog'),document.getElementById('logicDrawer'),document];
      var labs=n.labels||[];
      for(var s=0;s<scopes.length;s++){
        if(!scopes[s]) continue;
        var btns=scopes[s].querySelectorAll('button');
        for(var i=0;i<btns.length;i++){
          var oc=btns[i].getAttribute('onclick')||'';
          if(key && oc.indexOf("act('"+key+"'")>=0) return btns[i];
        }
      }
      for(var s2=0;s2<scopes.length;s2++){
        if(!scopes[s2]) continue;
        var bs=scopes[s2].querySelectorAll('button');
        for(var j=0;j<bs.length;j++){
          var tx=norm(bs[j].textContent);
          for(var k=0;k<labs.length;k++){ var lb=norm(labs[k]); if(lb && tx===lb) return bs[j]; }
        }
      }
      return null;
    }
    if(n.kind==='state'){
      var want=norm(n.key).replace(/^状态[:：]/,'');
      var badges=document.querySelectorAll('.bg,.badge,.status,.st');
      for(var i=0;i<badges.length;i++){ if(norm(badges[i].textContent)===want) return badges[i]; }
      return null;
    }
    if(n.kind==='dialog'){
      var t=document.getElementById('dialogTitle');
      if(t && norm(t.textContent).indexOf(norm(n.key))>=0) return document.querySelector('#logicDialog .mh');
      return null;
    }
    if(n.css){ try{ return document.querySelector(n.css); }catch(e){ return null; } }
    return null;
  }
  function toast(msg){
    var t=el('div','prd-toast'); t.textContent=msg; document.body.appendChild(t);
    setTimeout(function(){ if(t.parentNode) t.parentNode.removeChild(t); },2000);
  }
  function clearBadges(){
    var ds=document.querySelectorAll('.prd-badge');
    for(var i=0;i<ds.length;i++) ds[i].parentNode.removeChild(ds[i]);
  }
  function closePop(){
    if(hitEl){ hitEl.classList.remove('prd-hit'); hitEl=null; }
    if(pop && pop.parentNode) pop.parentNode.removeChild(pop);
    pop=null; curAnchor=null;
  }
  function mount(){
    if(!showBadges){ clearBadges(); return; }
    clearBadges();
    for(var i=0;i<NOTES.length;i++){
      var n=NOTES[i], h=hostOf(n);
      if(!h) continue;
      if(h.querySelector(':scope > .prd-badge')) continue;
      var cs=getComputedStyle(h);
      if(cs.position==='static') h.style.position='relative';
      var d=el('button','prd-badge');
      d.type='button'; d.textContent='?'; d.title=(n.title||'')+' · 点击查看业务规则';
      d.dataset.a=n.anchor; d.style.top='-9px'; d.style.right='-9px';
      d.__n=n;
      d.onclick=function(ev){ ev.stopPropagation(); ev.preventDefault(); openPop(this.__n, this.parentNode); };
      h.appendChild(d);
    }
  }
  function place(host){
    if(!pop) return;
    var r=host.getBoundingClientRect();
    var w=pop.offsetWidth||356, h=pop.offsetHeight||220;
    var left=r.right+10;
    if(left+w>window.innerWidth-12) left=Math.max(12, r.left-w-10);
    var top=r.top-8;
    if(top+h>window.innerHeight-12) top=Math.max(12, window.innerHeight-h-12);
    pop.style.left=left+'px'; pop.style.top=top+'px';
  }
  function viewHtml(n){
    var h='<div class="phd"><span class="pt">'+esc(n.title||n.key||'')+'</span><span class="chip">'+esc(KIND_CN[n.kind]||n.kind||'标注')+'</span></div>';
    h+='<div class="pm">'+esc(n.req||'未编号')+(n.status==='edited'?' · 已编辑':'')+'</div>';
    if(n.func) h+='<span class="pk">功能</span><p>'+esc(n.func)+'</p>';
    if(n.rules&&n.rules.length){ h+='<span class="pk">业务规则</span><ul>'; n.rules.forEach(function(x){h+='<li>'+esc(x)+'</li>';}); h+='</ul>'; }
    if(n.interaction&&n.interaction.length){ h+='<span class="pk gray">交互逻辑</span><ul>'; n.interaction.forEach(function(x){h+='<li>'+esc(x)+'</li>';}); h+='</ul>'; }
    if(n.edges&&n.edges.length){ h+='<span class="pk gray">边界条件</span><ul>'; n.edges.forEach(function(x){h+='<li>'+esc(x)+'</li>';}); h+='</ul>'; }
    if(!n.func && !(n.rules||[]).length && !(n.interaction||[]).length && !(n.edges||[]).length){
      h+='<p class="tip">这条标注还没有内容，点「编辑标注」补充业务规则。</p>';
    }
    h+='<div class="pft"><button class="pri" data-m="edit">编辑标注</button><span class="sp"></span><button data-m="del">删除</button></div>';
    return h;
  }
  function editHtml(n){
    var h='<div class="phd"><span class="pt">编辑标注</span><span class="chip">'+esc(KIND_CN[n.kind]||'标注')+'</span></div>';
    h+='<div class="pm">'+esc(n.req||'未编号')+' · 每行一条，空行自动忽略</div>';
    h+='<label class="pk gray">标题</label><textarea class="ed" data-f="title" rows="1">'+esc(n.title||'')+'</textarea>';
    h+='<label class="pk gray">功能</label><textarea class="ed" data-f="func" rows="2">'+esc(n.func||'')+'</textarea>';
    h+='<label class="pk">业务规则</label><textarea class="ed" data-f="rules" rows="5">'+esc((n.rules||[]).join('\n'))+'</textarea>';
    h+='<label class="pk gray">交互逻辑</label><textarea class="ed" data-f="interaction" rows="3">'+esc((n.interaction||[]).join('\n'))+'</textarea>';
    h+='<label class="pk gray">边界条件</label><textarea class="ed" data-f="edges" rows="3">'+esc((n.edges||[]).join('\n'))+'</textarea>';
    h+='<div class="pft"><button class="pri" data-m="save">保存</button><button data-m="cancel">取消</button><span class="sp"></span><button data-m="del">删除标注</button></div>';
    return h;
  }
  function openPop(n, host){
    if(curAnchor===n.anchor && !pop) {}
    if(curAnchor===n.anchor){ closePop(); return; }
    closePop();
    curAnchor=n.anchor;
    pop=el('div','prd-pop');
    pop.innerHTML=viewHtml(n);
    document.body.appendChild(pop);
    wireView(n,host); place(host);
    hitEl=host; host.classList.add('prd-hit');
  }
  function wireView(n,host){
    pop.addEventListener('mousedown',function(ev){ev.stopPropagation();});
    var e=pop.querySelector('[data-m=edit]');
    if(e) e.onclick=function(ev){ ev.stopPropagation(); pop.innerHTML=editHtml(n); wireEdit(n,host); };
    var d=pop.querySelector('[data-m=del]');
    if(d) d.onclick=function(ev){ ev.stopPropagation(); delNote(n,host); };
  }
  function wireEdit(n,host){
    var sv=pop.querySelector('[data-m=save]');
    sv.onclick=function(ev){
      ev.stopPropagation();
      var p=PATCH[n.anchor]||{};
      pop.querySelectorAll('textarea[data-f]').forEach(function(t){
        var f=t.dataset.f;
        p[f]=(f==='title'||f==='func')?t.value.trim():lines(t.value);
      });
      delete p.__deleted__;
      PATCH[n.anchor]=p; savePatch(); build();
      var nn=byAnchor(n.anchor)||n;
      toast('已保存（本地），可点右下角「导出修改」同步到 PRD');
      pop.innerHTML=viewHtml(nn); wireView(nn,host); place(host);
    };
    var cc=pop.querySelector('[data-m=cancel]');
    cc.onclick=function(ev){ ev.stopPropagation(); pop.innerHTML=viewHtml(n); wireView(n,host); };
    var dl=pop.querySelector('[data-m=del]');
    dl.onclick=function(ev){ ev.stopPropagation(); delNote(n,host); };
  }
  function delNote(n,host){
    if(!window.confirm('确定删除这条标注？')) return;
    var p=PATCH[n.anchor]||{};
    if(p.__new__){ delete PATCH[n.anchor]; } else { p.__deleted__=true; PATCH[n.anchor]=p; }
    savePatch(); build(); closePop(); mount();
    toast('标注已删除（本地），可导出修改同步');
  }
  function cssPath(node){
    var parts=[], cur=node, guard=0;
    while(cur && cur.nodeType===1 && cur!==document.body && guard<8){
      var sel=cur.tagName.toLowerCase();
      if(cur.id){ parts.unshift('#'+cur.id); break; }
      var cls=(typeof cur.className==='string'?cur.className:'').trim().split(/\s+/).filter(function(c){return c && c.indexOf('prd-')!==0;});
      if(cls.length) sel+='.'+cls[0];
      var par=cur.parentNode;
      if(par){
        var sibs=Array.prototype.filter.call(par.children,function(c2){return c2.tagName===cur.tagName;});
        if(sibs.length>1) sel+=':nth-of-type('+(sibs.indexOf(cur)+1)+')';
      }
      parts.unshift(sel); cur=cur.parentNode; guard++;
    }
    return parts.join(' > ');
  }
  function startPick(){
    if(picking) return;
    picking=true; document.body.classList.add('prd-picking');
    toast('点一下需要加标注的按钮或区域，Esc 取消');
    document.addEventListener('mousemove',onHover,true);
    document.addEventListener('click',onPick,true);
    document.addEventListener('keydown',onEsc,true);
  }
  function endPick(){
    picking=false; document.body.classList.remove('prd-picking');
    if(pickHover){ pickHover.classList.remove('prd-pickhover'); pickHover=null; }
    document.removeEventListener('mousemove',onHover,true);
    document.removeEventListener('click',onPick,true);
    document.removeEventListener('keydown',onEsc,true);
  }
  function onEsc(ev){ if(ev.key==='Escape'){ ev.preventDefault(); endPick(); } }
  function onHover(ev){
    var t=ev.target;
    if(!t || t.nodeType!==1 || t.closest('.prd-pop') || t.closest('.prd-fabs') || t.classList.contains('prd-badge')) return;
    if(pickHover===t) return;
    if(pickHover) pickHover.classList.remove('prd-pickhover');
    pickHover=t; t.classList.add('prd-pickhover');
  }
  function onPick(ev){
    var t=ev.target;
    if(!t || t.nodeType!==1 || t.closest('.prd-pop') || t.closest('.prd-fabs') || t.classList.contains('prd-badge')) return;
    ev.preventDefault(); ev.stopPropagation();
    var css=cssPath(t);
    var anchor='custom:'+Date.now().toString(36);
    var title=(t.textContent||'').replace(/\s+/g,' ').trim().slice(0,24) || '新标注';
    var page='';
    try{ page=(typeof PAGE!=='undefined'&&PAGE)?PAGE:''; }catch(e){}
    PATCH[anchor]={__new__:true, anchor:anchor, kind:'custom', page:page, key:anchor.split(':')[1], title:title, req:'（自定义）', func:'', rules:[], interaction:[], edges:[], css:css};
    savePatch(); build(); endPick(); mount();
    var n=byAnchor(anchor);
    var host=hostOf(n);
    if(host){ openPop(n,host); var e=pop.querySelector('[data-m=edit]'); if(e) e.click(); }
    else toast('已新增标注，但落点未找到，请刷新后再试');
  }
  function exportPatch(){
    var keys=Object.keys(PATCH);
    if(!keys.length){ toast('还没有修改'); return; }
    var out={updated:'', notes:[], deleted:[]};
    var d=new Date(), pad=function(x){return ('0'+x).slice(-2);};
    out.updated=d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+pad(d.getHours())+':'+pad(d.getMinutes());
    keys.forEach(function(a){
      var p=PATCH[a];
      if(p.__deleted__){ out.deleted.push(a); return; }
      var n=clone(p); delete n.__new__;
      if(!n.anchor) n.anchor=a;
      out.notes.push(n);
    });
    var blob=new Blob([JSON.stringify(out,null,2)],{type:'application/json'});
    var url=URL.createObjectURL(blob), a2=document.createElement('a');
    a2.href=url; a2.download='annotations-patch.json'; a2.click();
    setTimeout(function(){URL.revokeObjectURL(url);},4000);
    toast('已导出 annotations-patch.json');
  }
  function start(){
    build(); mount();
    var wrap=el('div','prd-fabs');
    var b1=el('button','prd-fab'); b1.type='button'; b1.textContent='规则标注 · 开';
    b1.title='显示/隐藏页面上的 ? 规则标注';
    var b2, b3;
    function syncFabs(){
      b1.textContent=showBadges?'规则标注 · 开':'规则标注 · 关';
      b1.classList.toggle('off',!showBadges);
      b1.title=showBadges?'隐藏页面上的 ? 规则标注':'显示页面上的 ? 规则标注';
      if(b2) b2.style.display=showBadges?'':'none';
      if(b3) b3.style.display=showBadges?'':'none';
    }
    b1.onclick=function(){
      showBadges=!showBadges;
      if(!showBadges){ if(picking) endPick(); closePop(); }
      syncFabs();
      mount();
    };
    b2=el('button','prd-fab'); b2.type='button'; b2.textContent='＋ 新增标注';
    b2.title='点击后在页面上选一个按钮或区域，为它加一条业务规则标注';
    b2.onclick=function(){ startPick(); };
    b3=el('button','prd-fab'); b3.type='button'; b3.textContent='导出修改';
    b3.title='把本次增删改导出为 JSON 补丁，用于同步 PRD 文档';
    b3.onclick=function(){ exportPatch(); };
    wrap.appendChild(b1); wrap.appendChild(b2); wrap.appendChild(b3);
    document.body.appendChild(wrap);
    syncFabs();
  }
  document.addEventListener('keydown',function(ev){
    if(ev.key!=='Escape' || !pop) return;
    ev.preventDefault(); ev.stopPropagation();
    closePop();
  },true);
  document.addEventListener('mousedown',function(ev){
    if(!pop) return;
    var t=ev.target;
    if(!t || t.nodeType!==1) return;
    if(pop.contains(t)) return;
    if(t.closest('.prd-badge') || t.closest('.prd-fabs') || t.closest('.prd-toast')) return;
    closePop();
  },true);
  function reposition(){ if(pop && hitEl && document.contains(hitEl)) place(hitEl); }
  window.addEventListener('scroll',reposition,true);
  window.addEventListener('resize',reposition);
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', start); else start();
  function isOwn(node){
    if(!node || node.nodeType!==1) return true;
    return node.classList && (node.classList.contains('prd-pop')||node.classList.contains('prd-badge')||node.classList.contains('prd-fab')||node.classList.contains('prd-toast'));
  }
  var t=null;
  function schedule(){ if(t) return; t=setTimeout(function(){ t=null; if(!hitEl || !document.contains(hitEl)) closePop(); mount(); },200); }
  new MutationObserver(function(recs){
    for(var i=0;i<recs.length;i++){
      var rec=recs[i];
      if(pop && (rec.target===pop || pop.contains(rec.target))) continue;
      var add=rec.addedNodes, rem=rec.removedNodes, foreign=false, a, r;
      for(a=0;a<add.length;a++){ if(!isOwn(add[a])){ foreign=true; break; } }
      if(!foreign) for(r=0;r<rem.length;r++){ if(!isOwn(rem[r])){ foreign=true; break; } }
      if(foreign){ schedule(); return; }
    }
  }).observe(document.body,{childList:true,subtree:true});
})();
"""


def cmd_inject(args):
    data = load_notes(args.notes)
    if not os.path.isfile(args.html):
        sys.exit('找不到原型：' + args.html)
    with io.open(args.html, encoding='utf-8', errors='replace') as f:
        t = f.read()
    if re.search(r'(?:src|href)=[\"\'][^:/#\"\']', t) and args.out and os.path.dirname(os.path.abspath(args.out)) != os.path.dirname(os.path.abspath(args.html)):
        print('提示：输出目录改变，请检查原型相对资源路径。')
    t = re.sub(r'<(?:style|script)\b[^>]*id=[\"\']prd-annotator-(?:css|data|js)[\"\'][^>]*>.*?</(?:style|script)>', '', t, flags=re.S|re.I)
    raw = [n for n in data['notes'] if n.get('status') != 'deprecated']
    payload = []
    for n in raw:
        payload.append({
            'anchor': n['anchor'], 'kind': n['kind'], 'page': n.get('page', ''),
            'key': n['anchor'].split(':', 1)[1] if ':' in n['anchor'] else n['anchor'],
            'title': n.get('title', ''), 'req': n.get('req', ''), 'status': n.get('status', 'draft'),
            'css': n.get('css', ''), 'func': n.get('func', ''), 'rules': n.get('rules', []),
            'edges': n.get('edges', []), 'interaction': n.get('interaction', []),
            'labels': n.get('labels') or [x for x in (n.get('title') or '').split(' / ') if x],
        })
    inject = (
        '<style id="prd-annotator-css">' + PANEL_CSS + '</style>'
        '<script id="prd-annotator-data">window.__PRD_NOTES__=' +
        json.dumps(payload, ensure_ascii=False).replace('<', r'\u003c') + ';</script>'
        '<script id="prd-annotator-js">' + PANEL_JS + '</script>'
    )
    out = t.replace('</body>', inject + '</body>') if '</body>' in t else t + inject
    dst = args.out or os.path.join(os.path.dirname(os.path.abspath(args.html)),
                                   os.path.splitext(os.path.basename(args.html))[0] + '-annotated.html')
    if os.path.realpath(dst) == os.path.realpath(args.html):
        sys.exit('输出不能覆盖原型本体，请指定副本路径')
    _dst_dir = os.path.dirname(dst)
    if _dst_dir:
        os.makedirs(_dst_dir, exist_ok=True)
    with io.open(dst, 'w', encoding='utf-8') as f:
        f.write(out)
    print('已生成旁注副本：%s（%d 条备注，原型本体未改动）' % (dst, len(payload)))


# ---------------- list ----------------

def cmd_list(args):
    data = load_notes(args.notes)
    for n in data['notes']:
        if args.kind and n['kind'] not in args.kind.split(','):
            continue
        print('%-30s %-8s %-4s %-10s %s' % (n['anchor'], KIND_CN.get(n['kind'], n['kind']),
                                            'OK' if n.get('status') == 'confirmed' else '..',
                                            n.get('req') or '—', n.get('title', '')))


def cmd_ack(args):
    data = load_notes(args.notes)
    scan = read_json(args.scan)
    el = next((e for e in scan['elements'] if e['anchor'] == args.anchor), None)
    n = next((n for n in data['notes'] if n['anchor'] == args.anchor), None)
    if not el or not n:
        sys.exit('锚点必须同时存在于扫描和备注中')
    n['hash'] = el['hash']
    n['source'] = {'line': el.get('line', 0), 'ref': el.get('ref', '')}
    n['version'] = n.get('version', 1) + 1
    n['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    save_notes(args.notes, data)
    print('已确认复核：' + args.anchor)


def main():
    ap = argparse.ArgumentParser(description='原型 PRD 备注管理器')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('init', help='由 scan.json 生成备注骨架')
    p.add_argument('--scan', required=True)
    p.add_argument('-o', '--out', required=True)
    p.add_argument('--kinds', help='参与初始化的类型，默认 page,action,dialog,state,rule')
    p.set_defaults(func=cmd_init)

    p = sub.add_parser('upsert', help='新增/更新一条备注')
    p.add_argument('--notes', required=True)
    p.add_argument('--anchor', required=True)
    p.add_argument('--title'); p.add_argument('--req'); p.add_argument('--page'); p.add_argument('--kind')
    p.add_argument('--func')
    for f in ['interaction', 'rules', 'edges', 'accept']:
        p.add_argument('--' + f, help='多个用 | 分隔')
    p.add_argument('--status', choices=['draft', 'confirmed', 'deprecated', 'n/a'])
    p.add_argument('--overwrite', action='store_true', help='覆盖已有字段')
    p.set_defaults(func=cmd_upsert)

    p = sub.add_parser('merge', help='批量增量合并')
    p.add_argument('--notes', required=True)
    p.add_argument('--patch', required=True)
    p.add_argument('--overwrite', action='store_true')
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser('check', help='体检')
    p.add_argument('--notes', required=True)
    p.add_argument('--scan')
    p.add_argument('--kinds', help='纳入覆盖率统计的类型，默认 page,action,dialog,state,rule')
    p.set_defaults(func=cmd_check)

    p = sub.add_parser('render', help='渲染 PRD 备注文档')
    p.add_argument('--notes', required=True)
    p.add_argument('-o', '--out')
    p.add_argument('--scan')
    p.add_argument('--status', help='只渲染指定状态，如 confirmed')
    p.set_defaults(func=cmd_render)

    p = sub.add_parser('inject', help='生成带旁注的副本')
    p.add_argument('html')
    p.add_argument('--notes', required=True)
    p.add_argument('-o', '--out')
    p.set_defaults(func=cmd_inject)

    p = sub.add_parser('list', help='列出备注')
    p.add_argument('--notes', required=True)
    p.add_argument('--kind')
    p.set_defaults(func=cmd_list)

    p = sub.add_parser('ack', help='人工复核后更新单条源码指纹')
    p.add_argument('--notes', required=True)
    p.add_argument('--scan', required=True)
    p.add_argument('--anchor', required=True)
    p.set_defaults(func=cmd_ack)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
