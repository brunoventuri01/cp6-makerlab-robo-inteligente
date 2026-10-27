"""Conversa e Arduino reais. Sem camera, visao, roteador por IA ou simulacao."""
import concurrent.futures
import json
import logging
import queue
import re
import threading
import time
import uuid
from pathlib import Path

from core.assistant import WakeWordGate
from core.local_audio import AudioLoop, PiperVoiceBackend, WindowsVoice
from core.llm import LLMClient
from core.robot import RobotController, physical_intent
from core.text_utils import normalizar

PERSONA = (
    'Voce e Roberto, um robo universitario. Responda em portugues brasileiro, '
    'com ate duas frases curtas, sem listas ou markdown. Voce conversa pelo '
    'microfone e alto-falante e tem um braco e um LED controlados pelo Arduino. '
    'Nao tem camera nem reconhecimento facial. Nunca diga que executou uma '
    'acao fisica: somente o controlador pode confirma-la. Se nao souber, diga.'
)


class SimpleRuntime:
    def __init__(self, root, config=None):
        self.root = Path(root)
        self.config = dict(config or json.loads((self.root/'config_roberto.json').read_text(encoding='utf-8')))
        self.lock = threading.RLock()
        self.processing_lock = threading.Lock()
        self.action_lock = threading.Lock()
        self.hardware_lock = threading.Lock()
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.actions = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.stop = threading.Event()
        self.speech = queue.Queue(maxsize=8)
        self.busy = self.speaking = self.action_busy = False
        self.mic_enabled = self.config.get('microfone_ativo', True)
        self.level = 0
        self.listening_activity = False
        self.window_until = 0
        self.sequence = 0
        self.events = []
        self.session = uuid.uuid4().hex
        self.history = []
        self.port = ''
        self.health = {'microfone':'Preparando', 'fala':'Preparando', 'voz':'Preparando', 'ia':'Preparando', 'arduino':'Procurando placa'}
        self.audio = AudioLoop(self)
        self.gate = WakeWordGate(self.config.get('wake_word','roberto'))
        self.robot = RobotController(False, self.emit)
        self.voice = (PiperVoiceBackend(self.root/self.config['modelo_voz'],self.config.get('ritmo_voz',1))
                      if self.config.get('motor_voz','piper') == 'piper' else WindowsVoice())
        self.llm = LLMClient()
        self.llm.url = self.config['ollama_url']
        self.llm.modelo = self.config['modelo_ia']
        self.llm.num_ctx = self.config.get('contexto_ia',1024)
        self.llm.read_timeout = 45

    def emit(self, kind, data):
        with self.lock:
            self.sequence += 1
            self.events.append({'seq':self.sequence,'type':kind,'data':data})
            self.events = self.events[-80:]

    def set_state(self, state):
        self.emit('state',state)

    def can_listen(self):
        return self.mic_enabled and not (self.busy or self.speaking or self.action_busy or self.speech.unfinished_tasks)

    def begin_processing(self):
        if not self.processing_lock.acquire(blocking=False):
            return False
        self.busy = True
        return True

    def finish_processing(self):
        self.audio.invalidate()
        self.busy = False
        if self.processing_lock.locked():
            self.processing_lock.release()

    def expire_window(self):
        if self.window_until and time.monotonic() > self.window_until:
            self.window_until = 0

    def fail(self, area, exc):
        logging.error('%s: %s',area,exc,exc_info=True)
        self.emit('error',f'{area}: {exc}')

    def speak(self, text):
        self.emit('assistant',text)
        if self.config.get('voz_ativa',True) and not self.stop.is_set():
            try:
                self.speech.put_nowait(text)
            except queue.Full:
                self.emit('error','Aguarde a fala terminar antes de enviar mais pedidos.')

    def _speech_worker(self):
        try:
            if isinstance(self.voice,PiperVoiceBackend):
                with self.voice.lock:
                    self.voice.load()
            self.health['voz'] = 'Pronta'
        except Exception as exc:
            self.health['voz'] = 'Falha ao preparar voz'
            self.fail('Voz',exc)
        while not self.stop.is_set():
            try:
                text = self.speech.get(timeout=.2)
            except queue.Empty:
                continue
            self.speaking = True
            self.audio.invalidate()
            try:
                self.voice.speak(text,self.config.get('dispositivo_saida'))
                self.health['voz'] = 'Pronta'
            except Exception as exc:
                self.health['voz'] = 'Falha na reproducao'
                self.fail('Voz',exc)
            finally:
                self.stop.wait(self.config.get('cauda_voz_segundos',.5))
                self.audio.invalidate()
                self.speaking = False
                self.speech.task_done()

    def toggle_mic(self, enabled):
        self.mic_enabled = enabled
        self.window_until = 0
        self.audio.invalidate()
        if self.audio.stream:
            try:
                if enabled and not self.audio.stream.active:
                    self.audio.stream.start()
                elif not enabled and self.audio.stream.active:
                    self.audio.stream.stop()
                self.health['microfone'] = 'Ativo' if enabled else 'Pausado'
            except Exception as exc:
                self.fail('Microfone',exc)

    def connect_serial(self, port):
        from serial.tools import list_ports
        with self.hardware_lock:
            self.robot.connect(port,self.config.get('baud_serial',115200))
            self.port = port
            self.health['arduino'] = 'Conectado em '+port
            self.config['porta_serial'] = port
            (self.root/'config_roberto.json').write_text(json.dumps(self.config,ensure_ascii=False,indent=2),encoding='utf-8')

    def auto_connect(self):
        from serial.tools import list_ports
        ports = [p for p in list_ports.comports() if p.vid is not None]
        preferred = self.config.get('porta_serial')
        selected = next((p for p in ports if p.device == preferred),None)
        if selected is None and len(ports) == 1:
            selected = ports[0]
        if selected is None:
            self.health['arduino'] = 'Desconectado: selecione a porta USB'
            return
        try:
            self.connect_serial(selected.device)
        except Exception as exc:
            self.health['arduino'] = 'Nao conectado: '+str(exc)

    def submit_action(self, action, text=None):
        if self.speech.full() or not self.action_lock.acquire(blocking=False):
            return False
        self.action_busy = True
        if text:
            self.emit('user',text)
        def execute():
            try:
                started = time.perf_counter()
                with self.hardware_lock:
                    self.robot.perform(action)
                self.speak({'ARM_UP':'Braço levantado.','ARM_DOWN':'Braço abaixado.',
                            'LED_ON':'Luz acesa.','LED_OFF':'Luz apagada.','WAVE':'Olá!'}[action])
                logging.info('Desempenho: acao %s %.3fs',action,time.perf_counter()-started)
            except Exception as exc:
                with self.hardware_lock:
                    self.robot.close()
                    self.health['arduino'] = 'Desconectado: reconecte a porta USB'
                self.fail('Arduino',exc)
                self.speak('Não recebi confirmação do Arduino. Confira a conexão USB. A ação pode ou não ter ocorrido.')
            finally:
                self.action_busy = False
                self.action_lock.release()
        try:
            self.actions.submit(execute)
        except Exception:
            self.action_busy = False
            self.action_lock.release()
            raise
        return True

    def submit(self, text):
        command = self.gate.extrair_comando(text)
        command = text if command is None else command
        action = physical_intent(command)
        if action:
            return self.submit_action(action,text)
        if not self.begin_processing():
            return False
        def execute():
            try:
                self.process(text,already_busy=True)
            finally:
                self.finish_processing()
        try:
            self.pool.submit(execute)
        except Exception:
            self.finish_processing()
            raise
        return True

    def process(self, text, source='texto', started_at=None, already_busy=False):
        if not already_busy and not self.begin_processing():
            return False
        try:
            if not text or (source == 'microfone' and (not self.mic_enabled or self.speaking)):
                return False
            command = self.gate.extrair_comando(text)
            if source == 'microfone' and command is None:
                if not self.window_until or (started_at or time.monotonic()) > self.window_until:
                    return False
            command = text if command is None else command
            if not command:
                self.speak('Oi, estou ouvindo!')
                self.window_until = time.monotonic()+self.config.get('janela_comando_segundos',7)+3
                return True
            self.window_until = 0
            action = physical_intent(command)
            if action:
                return self.submit_action(action,text)
            self.emit('user',text)
            normalized = normalizar(command)
            if re.search(r'\b(qual (e )?(o )?seu nome|como (voce )?se chama|quem (e )?voce)\b',normalized):
                response = 'Sou o Roberto, seu robô assistente!'
            elif re.search(r'\b(camera|webcam|reconhecimento facial|quem sou eu|o que.*vendo)\b',normalized):
                response = 'Estou funcionando sem câmera e sem reconhecimento facial. Posso conversar e controlar o braço e a luz.'
            else:
                messages = [{'role':'system','content':PERSONA}]+self.history[-4:]+[{'role':'user','content':command}]
                started = time.perf_counter()
                response = self.llm.conversar(messages,max_tokens=self.config.get('tokens_resposta_ia',96))
                logging.info('Desempenho: conversa %.3fs',time.perf_counter()-started)
                if not response:
                    raise RuntimeError('A IA nao retornou uma resposta')
                self.history = (self.history+[{'role':'user','content':command},{'role':'assistant','content':response}])[-4:]
            self.speak(response)
            return True
        except Exception as exc:
            self.fail('Conversa',exc)
            self.speak('A resposta demorou ou falhou. Os botões do braço e da luz continuam disponíveis.')
            return False
        finally:
            if not already_busy:
                self.finish_processing()

    def check_llm(self):
        import requests
        try:
            response = requests.post(self.llm.url+'/api/generate',json={'model':self.llm.modelo,'stream':False,
                'keep_alive':'20m','options':{'num_ctx':self.llm.num_ctx}},timeout=(5,90))
            response.raise_for_status()
            self.health['ia'] = 'Pronta: '+self.llm.modelo
        except Exception as exc:
            self.health['ia'] = 'Indisponivel: '+str(exc)

    def snapshot(self, after=0):
        self.expire_window()
        state = ('Falando' if self.speaking else 'Executando comando' if self.action_busy else
                 'Processando pergunta ou voz' if self.busy else 'Ouvindo seu pedido' if self.window_until else
                 'Diga Roberto e seu pedido' if self.mic_enabled else 'Microfone pausado')
        with self.lock:
            return {'title':self.config['titulo'],'session':self.session,'state':state,'busy':self.busy,
                    'action_busy':self.action_busy,'speaking':self.speaking,'mic':self.mic_enabled,
                    'level':self.level,'health':dict(self.health),'port':self.port,
                    'connected':bool(self.robot.serial and self.robot.serial.is_open),
                    'events':[e for e in self.events if e['seq']>after]}

    def start(self):
        self.audio.start()
        for job in (self._speech_worker,self.check_llm,self.auto_connect):
            threading.Thread(target=job,daemon=True).start()

    def close(self):
        self.stop.set()
        self.audio.close()
        with self.hardware_lock:
            self.robot.close()
        self.pool.shutdown(wait=False,cancel_futures=True)
        self.actions.shutdown(wait=False,cancel_futures=True)
