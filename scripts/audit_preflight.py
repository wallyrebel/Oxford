"""Read-only authenticated preflight for a fixed list of published audit targets.

There is intentionally no WordPress mutation method or apply option.
"""
import base64
import copy
import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
FIELDS = ('id', 'link', 'slug', 'status', 'date', 'date_gmt', 'modified', 'modified_gmt', 'author', 'categories', 'tags', 'featured_media')
SEO = ('_seopress_titles_title', '_seopress_titles_desc', '_seopress_social_fb_title', '_seopress_social_fb_desc', '_seopress_social_twitter_title', '_seopress_social_twitter_desc')

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def proposed(before, target):
    if before['id'] != target['id'] or before['link'] != target['link'] or before['status'] != 'publish':
        raise ValueError('Post identity or status changed')
    for field in ('title', 'excerpt', 'content'):
        if digest(before[field]['rendered']) != target['rendered_sha256'][field]:
            raise ValueError('Public article changed since source review')
    payload = {}
    for (field, ops) in target.get('replacements', {}).items():
        if field not in ('title', 'excerpt', 'content'):
            raise ValueError('Disallowed field')
        value = before[field]['raw']
        for op in ops:
            matches = [old for old in [op['old']] + op.get('variants', []) if value.count(old) == op.get('count', 1)]
            if len(matches) != 1:
                raise ValueError('Exact replacement precondition failed')
            value = value.replace(matches[0], op['new'])
        if value != before[field]['raw']:
            payload[field] = value
    for (field, value) in target.get('set', {}).items():
        if field not in ('title', 'excerpt', 'content'):
            raise ValueError('Disallowed field')
        if before[field]['raw'] != value:
            payload[field] = value
    for (field, value) in target.get('append', {}).items():
        if field != 'content':
            raise ValueError('Disallowed append field')
        original = payload.get(field, before[field]['raw'])
        if value in original:
            raise ValueError('Correction note already exists')
        payload[field] = original.rstrip() + '\n' + value + '\n'
    metadata = {}
    for (key, ops) in target.get('meta_replacements', {}).items():
        if key not in SEO:
            raise ValueError('Disallowed metadata')
        value = before.get('meta', {}).get(key, '')
        for op in ops:
            if op['old'] in value:
                value = value.replace(op['old'], op['new'])
        if value != before.get('meta', {}).get(key, ''):
            metadata[key] = value
    if metadata:
        payload['meta'] = metadata
    return payload

def snapshot(post):
    return {**{k: post[k] for k in FIELDS}, **{k: {'raw': post[k]['raw'], 'rendered': post[k]['rendered']} for k in ('title', 'excerpt', 'content')}, 'meta': {k: post.get('meta', {}).get(k, '') for k in SEO}}

def capability_check(account, post):
    caps = account.get('capabilities', {})
    owned = account.get('id') == post['author']
    permitted = caps.get('edit_posts') is True and caps.get('edit_published_posts') is True
    permitted = permitted and (owned or caps.get('edit_others_posts') is True)
    return {'account_id': account.get('id'), 'post_author_id': post['author'],
            'owned_by_account': owned, 'eligible_from_capabilities': permitted,
            'write_verified': False}

class NoRedirect(urllib.request.HTTPRedirectHandler):

    def redirect_request(self, *args, **kwargs):
        raise ValueError('Redirect refused for authenticated request')

def main():
    manifest = json.loads(Path('review/audit-2026-10-13.json').read_text())
    report = {'site': manifest['site'], 'mode': 'read-only', 'verified': False, 'posts': []}
    try:
        if os.environ['WORDPRESS_BASE_URL'].rstrip('/') != manifest['site']:
            raise ValueError('Managed host mismatch')
        auth = base64.b64encode((os.environ['WORDPRESS_USERNAME'] + ':' + os.environ['WORDPRESS_APP_PASSWORD']).encode()).decode()
        opener = urllib.request.build_opener(NoRedirect())
        headers = {'Authorization': 'Basic ' + auth, 'User-Agent': 'EditorialCorrectionPreflight/1.0'}
        account_url = manifest['site'] + '/wp-json/wp/v2/users/me?context=edit&_fields=id,capabilities'
        with opener.open(urllib.request.Request(account_url, headers=headers, method='GET'), timeout=30) as response:
            account = json.load(response)
        report['account'] = {'id': account.get('id'), 'capabilities': {
            key: account.get('capabilities', {}).get(key) is True
            for key in ('edit_posts', 'edit_published_posts', 'edit_others_posts', 'upload_files')}}
        for target in manifest['posts']:
            url = manifest['site'] + '/wp-json/wp/v2/posts/' + str(target['id']) + '?context=edit'
            request = urllib.request.Request(url, headers={'Authorization': 'Basic ' + auth, 'User-Agent': 'EditorialCorrectionPreflight/1.0'}, method='GET')
            with opener.open(request, timeout=30) as response:
                before = json.load(response)
            saved = snapshot(before)
            eligibility = capability_check(account, before)
            entry = {'id': target['id'], 'url': target['link'], 'before': saved, 'before_sha256': digest(saved), 'capability': eligibility}
            try:
                payload = proposed(before, target)
                if payload and not eligibility['eligible_from_capabilities']:
                    raise ValueError('Account capabilities do not permit this existing published post')
                after = copy.deepcopy(saved)
                for (key, value) in payload.items():
                    if key == 'meta':
                        after['meta'].update(value)
                    else:
                        after[key]['raw'] = value
                entry.update({'ready': True, 'payload': payload, 'payload_sha256': digest(payload), 'proposed_sha256': digest(after)})
            except ValueError as exc:
                entry.update({'ready': False, 'reason': str(exc)})
            report['posts'].append(entry)
        report['verified'] = True
    except urllib.error.HTTPError as exc:
        report.update({'error_type': 'HTTPError', 'http_status': exc.code, 'reason': 'Site stopped; no permission bypass or mutation attempted'})
    except Exception as exc:
        report.update({'error_type': type(exc).__name__, 'reason': 'Preflight stopped; no mutation attempted'})
    path = Path('data/audit-preflight.json')
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for (k, v) in report.items() if k != 'posts'}))
    print(json.dumps([{'id': p['id'], 'ready': p['ready'], 'payload_sha256': p.get('payload_sha256')} for p in report['posts']]))
    return 0 if report['verified'] else 1
if __name__ == '__main__':
    raise SystemExit(main())
