"""Instala os modelos locais sem alterar configuracoes do Windows."""
import json, os, sys, urllib.request, zipfile, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'runtime'
RUNTIME.mkdir(exist_ok=True)

def download(url, path):
    if path.exists(): return
    tmp=path.with_suffix(path.suffix+'.part')
    print('Baixando',path.name,flush=True)
    with urllib.request.urlopen(url,timeout=120) as source,open(tmp,'wb') as dest:
        total=int(source.headers.get('Content-Length',0)); got=0;last=time.monotonic()
        while True:
            block=source.read(4*1024*1024)
            if not block: break
            dest.write(block);got+=len(block)
            if time.monotonic()-last>10:
                print(f'{got//1048576} / {total//1048576} MB',flush=True);last=time.monotonic()
    tmp.replace(path)

def main():
    mode=sys.argv[1] if len(sys.argv)>1 else 'all'
    if mode in ('all','ollama'):
        target=RUNTIME/'ollama'
        if not (target/'ollama.exe').exists():
            req=urllib.request.Request('https://api.github.com/repos/ollama/ollama/releases/latest',headers={'User-Agent':'Roberto-CP5'})
            release=json.load(urllib.request.urlopen(req,timeout=30))
            asset=next(a for a in release['assets'] if a['name']=='ollama-windows-amd64.zip')
            path=RUNTIME/'ollama-windows-amd64.zip'; download(asset['browser_download_url'],path)
            target.mkdir(exist_ok=True)
            with zipfile.ZipFile(path) as archive: archive.extractall(target)
            (RUNTIME/'ollama-release.json').write_text(json.dumps({'version':release['tag_name'],'url':asset['browser_download_url']}),encoding='utf-8')
        print('Ollama pronto',flush=True)
    if mode in ('all','whisper'):
        os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING']='1'
        from huggingface_hub import snapshot_download
        dest=ROOT/'models'/'whisper-small'
        snapshot_download('Systran/faster-whisper-small',local_dir=str(dest),allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.*','preprocessor_config.json'])
        print('Reconhecimento de fala local pronto',flush=True)
    if mode in ('all','piper'):
        import subprocess
        subprocess.run([sys.executable,'-m','piper.download_voices','pt_BR-cadu-medium','--download-dir',str(ROOT/'models'/'piper')],check=True)

if __name__=='__main__':main()
