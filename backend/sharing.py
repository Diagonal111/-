"""Password-protected demo access; personal mode never enables these routes."""
import hashlib
import hmac
import os
import re
import secrets
import time
from collections import deque
from urllib.parse import parse_qs

from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

ENABLED = os.environ.get('STUDY_SHARE_MODE') == '1'
COOKIE = 'shizhi_share'
LIFETIME = 8 * 60 * 60
SESSION_SECRET = secrets.token_bytes(32)
FAILURES = deque()


def valid_cookie(value):
    try:
        stamp, nonce, signature = value.split('.')
        age = time.time() - int(stamp)
        expected = hmac.new(SESSION_SECRET, f'{stamp}.{nonce}'.encode(), hashlib.sha256).hexdigest()
        return 0 <= age < LIFETIME and hmac.compare_digest(signature, expected)
    except (ValueError, AttributeError):
        return False


def origin_allowed(request, origin):
    host = request.headers.get('host', '')
    if request.url.hostname in ('localhost', '127.0.0.1', 'testserver'):
        return origin == f'http://{host}'
    return origin == f'https://{host}'


def permitted(path, method):
    if method in ('GET', 'HEAD'):
        return path == '/api/bootstrap' or bool(re.fullmatch(r'/api/(questions|attempts)(/[\w-]+)?', path))
    if method == 'POST':
        return path in ('/api/attempts', '/api/plans/generate') or bool(re.fullmatch(r'/api/attempts/[\w-]+/(confirm|status)', path))
    return False


LOGIN = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>拾知 · 进入演示空间</title>
<style>*{box-sizing:border-box}body{margin:0;min-height:100dvh;display:grid;place-items:center;padding:24px;font:14px "Segoe UI","Microsoft YaHei",sans-serif;color:#345545;background:radial-gradient(ellipse at top right,#dcece0,transparent 65%),#f5f8f0}.card{width:410px;max-width:100%;padding:38px;border:1px solid #ffffffd9;border-radius:20px;background:#ffffffc9;box-shadow:0 20px 70px #294f3512;backdrop-filter:blur(15px)}.logo{background:linear-gradient(140deg,#4a876a,#245d4e);color:#f3f5de;width:48px;height:48px;border-radius:13px;display:grid;place-items:center;font-size:24px}small{display:block;color:#96a388;letter-spacing:2px;margin-top:25px;font-size:9px}h1{font-size:25px;font-weight:500;margin:11px 0 14px}p{color:#8a9b7c;line-height:1.9;font-size:12px}label{display:block;font-size:12px;margin:25px 0 9px}input{width:100%;padding:13px;border:1px solid #d9e5cf;border-radius:8px;background:#fffffc;font:inherit;color:#345545}input:focus{outline:2px solid #abc6b7}button{width:100%;border:0;border-radius:8px;padding:13px;margin-top:17px;background:linear-gradient(120deg,#34765f,#245d4e);color:white;font:inherit;cursor:pointer}.note{margin-top:23px;font-size:10px}.error{color:#a36c50;font-size:12px}</style>
<main class="card"><div class="logo">拾</div><small>SHIZHI · DEMO SPACE</small><h1>欢迎翻开这份学习积累。</h1><p>这是拾知的演示空间。输入分享者提供的口令，就可以体验书架、刷题和学习计划。</p><form method="post" action="/share/login"><label for="password">访问口令</label><input id="password" name="password" type="password" autocomplete="current-password" required maxlength="200" autofocus>ERROR<button type="submit">进入演示空间 →</button></form><p class="note">演示作答由访客共同使用；请使用示例答案，不填写个人信息。AI 调用与材料上传已关闭。</p></main></html>'''


def install(app):
    if not ENABLED:
        return
    if len(os.environ.get('STUDY_SHARE_PASSWORD', '')) < 12:
        raise RuntimeError('分享口令至少需要 12 个字符，请使用 share.py 启动。')

    @app.middleware('http')
    async def demo_access(request, call_next):
        path = request.url.path
        if path == '/share/login' and request.method == 'GET':
            response = HTMLResponse(LOGIN.replace('ERROR', ''))
        elif path == '/share/login' and request.method == 'POST':
            if not origin_allowed(request, request.headers.get('origin', '')):
                return JSONResponse({'detail': '请求来源无效'}, status_code=403)
            while FAILURES and time.monotonic() - FAILURES[0] > 60:
                FAILURES.popleft()
            if len(FAILURES) >= 10:
                return JSONResponse({'detail': '尝试次数较多，请一分钟后重试。'}, status_code=429)
            raw = b''
            async for chunk in request.stream():
                raw += chunk
                if len(raw) > 2048:
                    return JSONResponse({'detail': '请求过大'}, status_code=413)
            try:
                password = parse_qs(raw.decode(), max_num_fields=4).get('password', [''])[0]
            except (ValueError, UnicodeDecodeError):
                password = ''
            if hmac.compare_digest(password.encode(), os.environ['STUDY_SHARE_PASSWORD'].encode()):
                payload = f'{int(time.time())}.{secrets.token_hex(16)}'
                signature = hmac.new(SESSION_SECRET, payload.encode(), hashlib.sha256).hexdigest()
                response = RedirectResponse('/', status_code=303)
                response.set_cookie(COOKIE, f'{payload}.{signature}', max_age=LIFETIME, httponly=True, secure=request.url.scheme == 'https', samesite='lax')
            else:
                FAILURES.append(time.monotonic())
                response = HTMLResponse(LOGIN.replace('ERROR', '<p class="error" role="alert">口令不正确，请再试一次。</p>'), status_code=401)
        elif not valid_cookie(request.cookies.get(COOKIE, '')):
            response = JSONResponse({'detail': '请先输入分享口令。'}, status_code=401) if path.startswith('/api/') else RedirectResponse('/share/login', status_code=303)
        elif path.startswith('/api/') and not permitted(path, request.method):
            response = JSONResponse({'detail': '演示空间未开放此功能。'}, status_code=403)
        else:
            response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # Form POST navigation needs a same-origin referrer policy so browsers
        # send the real Origin instead of the opaque value "null".
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response
