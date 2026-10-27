"""Painel leve: conversa falada e Arduino real, somente em loopback."""
import contextlib,json,logging,os,threading
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv
from fastapi import FastAPI,HTTPException
from fastapi.responses import HTMLResponse,Response
from pydantic import BaseModel,Field
ROOT=Path(__file__).resolve().parent
load_dotenv(ROOT/'.env')
from core.simple_runtime import SimpleRuntime
runtime=None
@contextlib.asynccontextmanager
async def lifespan(app):
    global runtime
    (ROOT/'data/logs').mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=ROOT/'data/logs/roberto.log',level=logging.INFO,encoding='utf-8',format='%(asctime)s %(levelname)s %(message)s')
    runtime=SimpleRuntime(ROOT)
    runtime.start()
    try:yield
    finally:runtime.close()
app=FastAPI(title='Roberto',lifespan=lifespan)
@app.middleware('http')
async def local_only(request,call_next):
    from urllib.parse import urlparse
    origin=request.headers.get('origin','')
    host=request.headers.get('host','')
    if urlparse('//'+host).hostname not in ('127.0.0.1','localhost','::1'):
        return Response('Acesso somente local',status_code=403)
    if origin and urlparse(origin).netloc!=host:
        return Response('Origem externa recusada',status_code=403)
    return await call_next(request)
class Utterance(BaseModel):text:str=Field(min_length=1,max_length=1200)
class Toggle(BaseModel):enabled:bool
class SerialOptions(BaseModel):port:str=Field(min_length=1,max_length=40)
class Action(BaseModel):action:Literal['ARM_UP','ARM_DOWN','LED_ON','LED_OFF','WAVE']
@app.get('/',response_class=HTMLResponse)
def index():return HTMLResponse((ROOT/'web/index.html').read_text(encoding='utf-8'),headers={'Cache-Control':'no-store'})
@app.get('/api/state')
def state(after:int=0):return runtime.snapshot(after)
@app.post('/api/utterance')
def utterance(body:Utterance):
    if not runtime.submit(body.text):raise HTTPException(409,'Aguarde a pergunta atual terminar. Os controles do Arduino continuam disponiveis.')
    return {'accepted':True}
@app.post('/api/action')
def action(body:Action):
    if not runtime.submit_action(body.action):raise HTTPException(409,'Aguarde o movimento atual terminar.')
    return {'accepted':True}
@app.post('/api/microphone')
def microphone(body:Toggle):
    runtime.toggle_mic(body.enabled)
    return {'enabled':runtime.mic_enabled}
@app.get('/api/ports')
def ports():
    from serial.tools import list_ports
    return [{'port':p.device,'name':p.description} for p in list_ports.comports() if p.vid is not None]
@app.post('/api/serial')
def connect(body:SerialOptions):
    if runtime.action_busy:raise HTTPException(409,'Aguarde o movimento terminar.')
    try:runtime.connect_serial(body.port)
    except Exception as exc:raise HTTPException(400,str(exc))
    return {'connected':True,'port':runtime.port}
@app.post('/api/shutdown')
def shutdown():
    runtime.toggle_mic(False)
    def stop():
        runtime.close()
        os._exit(0)
    threading.Timer(.3,stop).start()
    return {'ok':True}
if __name__=='__main__':
    import uvicorn
    config=json.loads((ROOT/'config_roberto.json').read_text(encoding='utf-8'))
    uvicorn.run(app,host='127.0.0.1',port=config['porta_painel'],log_level='warning')
