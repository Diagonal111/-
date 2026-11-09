"""Launch the local application, reusing an existing Shizhi process if present."""
import json
import threading
import time
import urllib.error
import urllib.request
import webbrowser

URL='http://127.0.0.1:8765'


def open_when_ready():
    for _ in range(60):
        try:
            with urllib.request.urlopen(URL+'/api/bootstrap',timeout=1) as response:
                if json.load(response).get('app')=='shizhi':
                    webbrowser.open(URL)
                    return
        except (OSError,ValueError):
            time.sleep(.25)


if __name__=='__main__':
    existing=False
    try:
        with urllib.request.urlopen(URL+'/api/bootstrap',timeout=1) as response:
            existing=json.load(response).get('app')=='shizhi'
    except (OSError,ValueError):
        pass
    if existing:
        webbrowser.open(URL)
        print('Shizhi is already running: '+URL)
    else:
        import uvicorn
        threading.Thread(target=open_when_ready,daemon=True).start()
        print('Shizhi: '+URL+'  |  Press Ctrl+C to stop.')
        uvicorn.run('backend.main:app',host='127.0.0.1',port=8765)
