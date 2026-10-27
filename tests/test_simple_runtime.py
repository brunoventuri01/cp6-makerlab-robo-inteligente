import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from core.simple_runtime import SimpleRuntime
from core.robot import physical_intent

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def simple(tmp_path):
    config=json.loads((ROOT/'config_roberto.json').read_text(encoding='utf-8'))
    config.update(voz_ativa=False,microfone_ativo=False)
    r=SimpleRuntime(tmp_path,config)
    yield r
    r.close()

def wait_until(predicate):
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.01)
    pytest.fail('Operacao nao terminou no prazo')

def test_arduino_is_real_and_disconnected_action_never_claims_success(simple):
    assert simple.robot.simulation is False
    assert simple.submit_action('LED_ON')
    wait_until(lambda:not simple.action_busy)
    assert not any(e['type']=='action' for e in simple.events)
    assert not any(e['type']=='assistant' and e['data']=='Luz acesa.' for e in simple.events)
    assert any(e['type']=='error' for e in simple.events)
    assert not simple.snapshot()['connected']

def test_hardware_command_does_not_wait_for_conversation(simple):
    started=threading.Event()
    release=threading.Event()
    def slow(*args,**kwargs):
        started.set()
        release.wait(3)
        return 'Resposta de teste.'
    simple.llm.conversar=slow
    simple.robot.perform=Mock(return_value='Confirmado')
    try:
        assert simple.submit('Quanto e dois mais dois?')
        assert started.wait(1)
        assert simple.busy
        assert simple.submit('Roberto, acenda a luz')
        wait_until(lambda:not simple.action_busy)
        simple.robot.perform.assert_called_once_with('LED_ON')
        assert simple.busy
        assert any(e['data']=='Luz acesa.' for e in simple.events if e['type']=='assistant')
    finally:
        release.set()
        wait_until(lambda:not simple.busy)

def test_typed_question_does_not_require_wake_word(simple):
    simple.llm.conversar=Mock(return_value='Brasilia.')
    assert simple.process('Qual e a capital do Brasil?')
    simple.llm.conversar.assert_called_once()
    assert any(e['data']=='Brasilia.' for e in simple.events)

def test_microphone_still_requires_wake_word(simple):
    simple.mic_enabled=True
    simple.llm.conversar=Mock()
    assert not simple.process('Acenda a luz',source='microfone')
    simple.llm.conversar.assert_not_called()
    assert not simple.action_busy

def test_response_is_queued_for_voice_and_blocks_self_listening(simple):
    simple.config['voz_ativa']=True
    simple.mic_enabled=True
    simple.speak('Ola, estou aqui.')
    assert simple.speech.get_nowait()=='Ola, estou aqui.'
    assert not simple.can_listen()
    simple.speech.task_done()
    assert simple.can_listen()

@pytest.mark.parametrize('text,action',[
    ('sobe o braco','ARM_UP'),('desce o braco','ARM_DOWN'),
    ('acende a luz','LED_ON'),('apaga a luz','LED_OFF'),
    ('nao sobe o braco',None),('nao acende a luz',None),
])
def test_natural_commands_and_negation(text,action):
    assert physical_intent(text)==action

def test_camera_and_simulation_routes_removed(simple,monkeypatch):
    import app
    from fastapi.testclient import TestClient
    monkeypatch.setattr(app,'SimpleRuntime',lambda root:simple)
    simple.start=Mock()
    with TestClient(app.app,base_url='http://127.0.0.1') as client:
        assert client.get('/api/camera.jpg').status_code==404
        assert client.post('/api/simulation').status_code==404
        state=client.get('/api/state').json()
        assert 'simulated' not in state
        assert 'webcam' not in state['health']
        assert 'data-action="LED_ON"' in client.get('/').text
        assert client.post('/api/action',json={'action':'INVALID'}).status_code==422
