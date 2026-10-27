"""Inicializador sem terminal: reutiliza servicos e abre o painel no navegador."""
import json,os,subprocess,sys,time,urllib.request,webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CREATE_NO_WINDOW=0x08000000 if os.name=='nt' else 0
def get(url):
    try:
        with urllib.request.urlopen(url,timeout=2) as result:return json.load(result)
    except Exception:return None
def main():
    cfg=json.loads((ROOT/'config_roberto.json').read_text(encoding='utf-8'))
    url=f'http://127.0.0.1:{cfg["porta_painel"]}'
    status=get(url+'/api/state')
    if status and status.get('title')==cfg['titulo']:webbrowser.open(url);return
    (ROOT/'data'/'logs').mkdir(parents=True,exist_ok=True)
    if not get(cfg['ollama_url']+'/api/tags'):
        exe=ROOT/'runtime'/'ollama'/'ollama.exe'
        if not exe.exists():raise RuntimeError('O motor de IA local nao esta instalado. Execute a preparacao indicada no README.md.')
        env=os.environ.copy();env.update(OLLAMA_HOST='127.0.0.1:11435',OLLAMA_MODELS=str(ROOT/'models'/'ollama'),OLLAMA_NO_CLOUD='1',OLLAMA_KEEP_ALIVE='20m')
        with open(ROOT/'data'/'logs'/'ollama.log','a',encoding='utf-8') as log:
            subprocess.Popen([str(exe),'serve'],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=CREATE_NO_WINDOW)
        for _ in range(40):
            if get(cfg['ollama_url']+'/api/tags'):break
            time.sleep(.5)
        else:raise RuntimeError('A IA local nao iniciou. Consulte data/logs/ollama.log.')
    python=ROOT/'python'/'python.exe'
    if not python.exists():python=ROOT/'.venv'/'Scripts'/'python.exe'
    with open(ROOT/'data'/'logs'/'painel.log','a',encoding='utf-8') as log:
        subprocess.Popen([str(python),str(ROOT/'app.py')],cwd=ROOT,stdout=log,stderr=log,creationflags=CREATE_NO_WINDOW)
    for _ in range(90):
        if get(url+'/api/state'):webbrowser.open(url);return
        time.sleep(.5)
    raise RuntimeError('O painel nao iniciou. Consulte data/logs/painel.log.')
if __name__=='__main__':
    try:main()
    except Exception as exc:
        (ROOT/'data'/'logs').mkdir(parents=True,exist_ok=True)
        (ROOT/'data'/'logs'/'erro_inicio.txt').write_text(str(exc),encoding='utf-8')
        import ctypes
        ctypes.windll.user32.MessageBoxW(0,str(exc),'Roberto — erro ao iniciar',16)
