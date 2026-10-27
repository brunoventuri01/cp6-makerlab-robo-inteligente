"""Baixa a ferramenta oficial Arduino e compila o firmware, sem placa conectada."""
import json,os,subprocess,sys,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from preparar_local import download
runtime=ROOT/'runtime';cli_dir=runtime/'arduino-cli';cli_dir.mkdir(parents=True,exist_ok=True)
exe=cli_dir/'arduino-cli.exe'
if not exe.exists():
    req=urllib.request.Request('https://api.github.com/repos/arduino/arduino-cli/releases/latest',headers={'User-Agent':'Roberto-CP5'})
    release=json.load(urllib.request.urlopen(req,timeout=30))
    asset=next(a for a in release['assets'] if a['name'].endswith('Windows_64bit.zip'))
    path=runtime/'arduino-cli.zip';download(asset['browser_download_url'],path)
    with zipfile.ZipFile(path) as archive:archive.extractall(cli_dir)
cfg=runtime/'arduino-config.yaml'
cfg.write_text('directories:\n  data: '+json.dumps(str(runtime/'arduino-data'))+'\n  downloads: '+json.dumps(str(runtime/'arduino-downloads'))+'\n  user: '+json.dumps(str(runtime/'arduino-user'))+'\n',encoding='utf-8')
def run(*args):
    print('Arduino:',*args,flush=True)
    subprocess.run([str(exe),'--config-file',str(cfg),*args],check=True)
run('core','update-index')
run('core','install','arduino:avr')
run('lib','install','Servo')
for name,fqbn in [('uno','arduino:avr:uno'),('nano','arduino:avr:nano:cpu=atmega328'),('nano_old','arduino:avr:nano:cpu=atmega328old')]:
    run('compile','--fqbn',fqbn,'--output-dir',str(ROOT/'firmware'/'compilado'/name),str(ROOT/'firmware'/'Roberto'))
print('Firmware compilado para Uno e Nano classico.',flush=True)
