"""Comandos fisicos, simulacao explicita e confirmacao serial correlacionada."""
import json, re, threading, time, uuid
from core.text_utils import normalizar
from skills.base import Skill

def physical_intent(text):
    text=normalizar(text)
    if re.search(r'\b(nao|nunca)\b',text): return None
    if re.search(r'\b(cumprimente|cumprimentar|cumprimente me|acene|acenar|de um oi|diga oi)\b',text): return 'WAVE'
    if 'braco' in text:
        if re.search(r'\b(levante|levanta|levantar|erga|erguer|suba|sobe|subir)\b',text): return 'ARM_UP'
        if re.search(r'\b(abaixe|abaixa|abaixar|baixe|baixar|desca|desce|descer)\b',text): return 'ARM_DOWN'
    if re.search(r'\b(luz|led|peito)\b',text):
        if re.search(r'\b(acenda|acende|acender|ligue|liga|ligar)\b',text): return 'LED_ON'
        if re.search(r'\b(apague|apaga|apagar|desligue|desliga|desligar)\b',text): return 'LED_OFF'
    return None

class RobotController:
    def __init__(self, simulation=True, publish=None):
        self.simulation=simulation; self.publish=publish or (lambda *_:None)
        self.serial=None;self.lock=threading.Lock();self.arm_up=False;self.led_on=False
    def connect(self,port,baud=115200):
        import serial
        self.close()
        connection=serial.Serial(port,baud,timeout=.15,write_timeout=1)
        time.sleep(2)
        connection.reset_input_buffer()
        self.serial=connection;self.simulation=False
    def close(self):
        if self.serial:self.serial.close()
        self.serial=None
    def perform(self,action):
        if action not in {'ARM_UP','ARM_DOWN','LED_ON','LED_OFF','WAVE'}:raise ValueError('Acao desconhecida')
        with self.lock:
            if not self.simulation:
                if not self.serial or not self.serial.is_open:raise RuntimeError('Arduino nao conectado; nenhuma acao confirmada')
                request_id=uuid.uuid4().hex[:12]
                payload={'id':request_id,'action':action}
                self.serial.write((json.dumps(payload)+'\n').encode())
                deadline=time.monotonic()+12
                while time.monotonic()<deadline:
                    line=self.serial.readline()
                    if not line:continue
                    try:ack=json.loads(line)
                    except (ValueError,UnicodeError):continue
                    if ack.get('id')!=request_id:continue
                    if ack.get('ok') is not True:raise RuntimeError(ack.get('error','Arduino recusou o comando'))
                    break
                else:raise TimeoutError('Arduino nao confirmou; o movimento pode ou nao ter ocorrido')
            if action in ('ARM_UP','ARM_DOWN'):self.arm_up=action=='ARM_UP'
            if action in ('LED_ON','LED_OFF'):self.led_on=action=='LED_ON'
            self.publish('action',{'action':action,'simulated':self.simulation,'arm_up':self.arm_up,'led_on':self.led_on})
            texts={'ARM_UP':'levantei meu braço','ARM_DOWN':'abaixei meu braço','LED_ON':'acendi a luz','LED_OFF':'apaguei a luz','WAVE':'fiz um aceno. Olá!'}
            return ('Na simulação, ' if self.simulation else 'O Arduino confirmou: ')+texts[action]+'.'

class RobotSkill(Skill):
    nome='roberto_acoes'
    def __init__(self,controller):self.controller=controller
    def matches(self,text):return physical_intent(text) is not None
    def execute(self,text,ctx):
        ctx.assistente.set_state('EXECUTANDO AÇÃO')
        return self.controller.perform(physical_intent(text))
