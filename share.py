"""Run an isolated, password-protected demonstration through a Quick Tunnel."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

PROJECT = Path(__file__).resolve().parent
RUNTIME = PROJECT / '.share'
STATUS = RUNTIME / 'status.json'


def extract_msi(package, destination):
    """Read embedded cabinets directly; never invoke an elevated installer."""
    import ctypes
    msi = ctypes.WinDLL('msi')
    handle = ctypes.c_uint()
    if msi.MsiOpenDatabaseW(str(package), None, ctypes.byref(handle)):
        raise RuntimeError('无法读取已验证的官方安装包。')
    view = ctypes.c_uint()
    try:
        query = 'SELECT `Name`, `Data` FROM `_Streams`'
        if msi.MsiDatabaseOpenViewW(handle, query, ctypes.byref(view)) or msi.MsiViewExecute(view, 0):
            raise RuntimeError('无法读取安装包中的压缩文件。')
        destination.mkdir(parents=True, exist_ok=True)
        while True:
            record = ctypes.c_uint()
            result = msi.MsiViewFetch(view, ctypes.byref(record))
            if result == 259:
                break
            if result:
                raise RuntimeError('安装包读取失败。')
            try:
                name = ctypes.create_unicode_buffer(512)
                length = ctypes.c_uint(512)
                msi.MsiRecordGetStringW(record, 1, name, ctypes.byref(length))
                if not name.value.lower().endswith('.cab'):
                    continue
                cabinet = destination / Path(name.value).name
                with cabinet.open('wb') as output:
                    while True:
                        buffer = ctypes.create_string_buffer(65536)
                        size = ctypes.c_uint(len(buffer))
                        if msi.MsiRecordReadStream(record, 2, buffer, ctypes.byref(size)):
                            raise RuntimeError('压缩文件读取失败。')
                        if not size.value:
                            break
                        output.write(buffer.raw[:size.value])
                subprocess.run(['expand.exe', '-R', str(cabinet), '-F:*', str(destination)], check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            finally:
                msi.MsiCloseHandle(record)
    finally:
        if view.value:
            msi.MsiCloseHandle(view)
        msi.MsiCloseHandle(handle)


def write_status(value):
    temp = STATUS.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(STATUS)


def cloudflared():
    existing = shutil.which('cloudflared')
    if existing:
        return existing
    target = RUNTIME / 'tools' / 'cloudflared.exe'
    if target.exists():
        return str(target)
    if sys.platform != 'win32':
        raise RuntimeError('请先安装官方 cloudflared，再运行分享脚本。')
    target.parent.mkdir(parents=True, exist_ok=True)
    print('Downloading official Cloudflare client...', flush=True)
    request = urllib.request.Request('https://api.github.com/repos/cloudflare/cloudflared/releases/latest', headers={'User-Agent': 'Shizhi-demo-launcher'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.load(response)
    except OSError:
        # Verified official MSI, pinned from the Microsoft WinGet manifest.
        # Read the embedded cabinet without installing a service or requesting UAC.
        package = target.parent / 'cloudflared-2026.10.7.msi'
        with urllib.request.urlopen('https://github.com/cloudflare/cloudflared/releases/download/2026.10.7/cloudflared-windows-amd64.msi', timeout=120) as response, package.open('wb') as output:
            shutil.copyfileobj(response, output)
        if hashlib.sha256(package.read_bytes()).hexdigest() != '057a1370fe26b1a4d45d8673c219fa3ddb3c3b4bcbf0cde25ee938c932645387':
            package.unlink()
            raise RuntimeError('官方安装包校验失败。')
        extracted = target.parent / 'extracted'
        extract_msi(package, extracted)
        binary = next(extracted.rglob('cloudflared.exe'), None) or next(extracted.rglob('ApplicationFile0'), None)
        if not binary:
            raise RuntimeError('安装包中没有找到 cloudflared.exe。')
        shutil.copy2(binary, target)
        return str(target)
    asset = next(a for a in release['assets'] if a['name'] == 'cloudflared-windows-amd64.exe')
    digest = asset.get('digest', '')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
        raise RuntimeError('官方发布未提供可验证的 SHA256，请通过官方渠道安装 cloudflared。')
    partial = target.with_suffix('.download')
    with urllib.request.urlopen(asset['browser_download_url'], timeout=120) as response, partial.open('wb') as output:
        shutil.copyfileobj(response, output)
    if hashlib.sha256(partial.read_bytes()).hexdigest() != digest.split(':')[1]:
        partial.unlink()
        raise RuntimeError('Cloudflared 下载校验失败，请重试。')
    partial.replace(target)
    return str(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stop', action='store_true', help='Stop the current demo and tunnel')
    parser.add_argument('--status', action='store_true', help='Show the current link and access password')
    args = parser.parse_args()
    RUNTIME.mkdir(exist_ok=True)
    state = json.loads(STATUS.read_text(encoding='utf-8')) if STATUS.exists() else {}
    if args.status:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return
    if args.stop:
        run_id = state.get('run_id', '')
        if state.get('running') and re.fullmatch(r'[a-f0-9]{32}', run_id):
            (RUNTIME / f'stop-{run_id}').touch()
            for _ in range(100):
                time.sleep(.1)
                if not json.loads(STATUS.read_text(encoding='utf-8')).get('running'):
                    print('Sharing stopped.')
                    return
            raise RuntimeError('停止请求已提交，请查看 share.log。')
        print('No active sharing session.')
        return
    if state.get('running'):
        raise RuntimeError('已有分享会话，请先运行 share.py --stop；链接见 .share/status.json。')
    if not (PROJECT / 'dist' / 'index.html').exists():
        raise RuntimeError('请先运行 npm run build。')
    executable = cloudflared()
    run_id = secrets.token_hex(16)
    password = secrets.token_urlsafe(12)
    data_dir = RUNTIME / 'sessions' / run_id
    data_dir.mkdir(parents=True)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    env = os.environ.copy()
    env.update(STUDY_SHARE_MODE='1', STUDY_DATA_DIR=str(data_dir), STUDY_SHARE_PASSWORD=password, STUDY_API_KEY='')
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    state = {'running': True, 'run_id': run_id, 'url': '', 'password': password, 'local_url': f'http://127.0.0.1:{port}', 'data_dir': str(data_dir)}
    stop_file = RUNTIME / f'stop-{run_id}'
    children = []
    write_status(state)
    try:
        with (RUNTIME / 'server.log').open('w', encoding='utf-8') as server_log, (RUNTIME / 'tunnel.log').open('w', encoding='utf-8') as tunnel_log:
            server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', str(port), '--no-access-log'], cwd=PROJECT, env=env, stdout=server_log, stderr=subprocess.STDOUT, creationflags=flags)
            children.append(server)
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError('演示服务启动失败，详情见 .share/server.log。')
                try:
                    with urllib.request.urlopen(state['local_url'] + '/share/login', timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.2)
            else:
                raise RuntimeError('演示服务启动超时。')
            tunnel = subprocess.Popen([executable, 'tunnel', '--no-autoupdate', '--url', state['local_url'], '--protocol', 'http2'], cwd=data_dir, stdout=tunnel_log, stderr=subprocess.STDOUT, creationflags=flags)
            children.append(tunnel)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if tunnel.poll() is not None:
                    raise RuntimeError('隧道启动失败，详情见 .share/tunnel.log。')
                log = (RUNTIME / 'tunnel.log').read_text(encoding='utf-8', errors='replace')
                found = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', log)
                if found:
                    state['url'] = found.group()
                    write_status(state)
                    print(f"Share URL: {state['url']}\nAccess password: {password}\nStop with: python share.py --stop", flush=True)
                    break
                if stop_file.exists():
                    return
                time.sleep(.3)
            else:
                raise RuntimeError('未能获取临时分享网址，详情见 .share/tunnel.log。')
            while not stop_file.exists():
                if any(child.poll() is not None for child in children):
                    raise RuntimeError('演示服务或隧道已经退出，详情见 .share 日志。')
                time.sleep(.5)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        state['error'] = str(error)
        raise
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        state['running'] = False
        write_status(state)
        stop_file.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
