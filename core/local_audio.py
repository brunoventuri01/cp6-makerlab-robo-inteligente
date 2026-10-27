"""VAD WebRTC + Whisper local. Nenhum audio e enviado para a internet."""
from collections import deque
from pathlib import Path
import json, logging, queue, threading, time
import numpy as np

class LocalRecognizer:
    def __init__(self,path,beam_size=1,cpu_threads=4):
        from faster_whisper import WhisperModel
        self.beam_size=beam_size
        self.model=WhisperModel(str(path),device='cpu',compute_type='int8',cpu_threads=cpu_threads,num_workers=1,local_files_only=True)
    def transcribe(self,audio):
        if isinstance(audio,bytes):audio=np.frombuffer(audio,dtype=np.int16).astype(np.float32)/32768
        segments,info=self.model.transcribe(audio,language='pt',beam_size=self.beam_size,best_of=1,temperature=0,
            condition_on_previous_text=False,vad_filter=True,
            vad_parameters={'min_silence_duration_ms':350},no_speech_threshold=.6,
            # Nao sugerir o nome no prompt: poderia converter "Roberta" em "Roberto".
            initial_prompt=None)
        accepted=[s.text.strip() for s in segments if s.no_speech_prob<.65 and s.avg_logprob>-1.05]
        return ' '.join(accepted).strip()

class AudioLoop:
    RATE=16000;FRAME=480
    def __init__(self,runtime):
        self.runtime=runtime;self.queue=queue.Queue(maxsize=80);self.stop=threading.Event();self.thread=None
        self.recognizer=None;self.stream=None;self.epoch=0
    def invalidate(self):
        self.epoch+=1
        while True:
            try:self.queue.get_nowait()
            except queue.Empty:break
    def start(self):
        self.thread=threading.Thread(target=self._run,name='Roberto-microfone',daemon=True);self.thread.start()
    def _callback(self,data,frames,time_info,status):
        raw=bytes(data)
        a=np.frombuffer(raw,dtype=np.int16).astype(np.float32)
        self.runtime.level=min(1,float(np.sqrt(np.mean(a*a)))/5000) if len(a) else 0
        if not self.runtime.can_listen():return
        try:self.queue.put_nowait((raw,self.epoch,time.monotonic()))
        except queue.Full:pass
    def _run(self):
        import sounddevice as sd, webrtcvad
        r=self.runtime
        try:
            r.health['fala']='Carregando Whisper local…'
            self.recognizer=LocalRecognizer(r.root/r.config['modelo_fala'],r.config.get('beam_fala',1),r.config.get('threads_fala',4))
            r.health['fala']='Whisper small · português · local'
            vad=webrtcvad.Vad(2)
            self.stream=sd.RawInputStream(samplerate=self.RATE,blocksize=self.FRAME,dtype='int16',channels=1,
                device=r.config.get('dispositivo_microfone'),callback=self._callback)
            with self.stream:
                if not r.mic_enabled:self.stream.stop()
                r.health['microfone']='Ativo' if r.mic_enabled else 'Pausado';r.emit('health',r.health)
                pre=deque(maxlen=10);frames=[];speech=0;silence=0;current=self.epoch;started=0
                while not self.stop.is_set():
                    try:raw,epoch,stamp=self.queue.get(timeout=.15)
                    except queue.Empty:
                        r.expire_window();continue
                    if epoch!=self.epoch or not r.can_listen():
                        frames=[];pre.clear();speech=silence=0;continue
                    if current!=epoch:
                        frames=[];pre.clear();speech=silence=0;current=epoch
                    amplitude=float(np.sqrt(np.mean(np.frombuffer(raw,dtype=np.int16).astype(np.float32)**2)))
                    voiced=vad.is_speech(raw,self.RATE) and amplitude>110
                    if not frames:
                        pre.append(raw)
                        if not voiced:continue
                        frames=list(pre);started=stamp;speech=1;silence=0
                    else:
                        frames.append(raw)
                        if voiced:speech+=1;silence=0
                        else:silence+=1
                    r.listening_activity=voiced
                    if len(frames)<500 and silence*.03<r.config['pausa_final_segundos']:continue
                    audio=b''.join(frames);frames=[];pre.clear()
                    if speech<6:speech=silence=0;continue
                    speech=silence=0
                    if not r.begin_processing():continue
                    epoch=self.epoch
                    try:
                        transcribe_started=time.perf_counter()
                        text=self.recognizer.transcribe(audio)
                        logging.info('Desempenho: reconhecimento %.3fs',time.perf_counter()-transcribe_started)
                        if epoch==self.epoch and r.mic_enabled:
                            r.process(text,source='microfone',started_at=started,already_busy=True)
                    except Exception as exc:r.fail('Reconhecimento de fala',exc)
                    finally:r.finish_processing()
        except Exception as exc:
            r.health['microfone']='Indisponível: '+str(exc);r.emit('health',r.health);r.fail('Microfone',exc)
    def close(self):self.stop.set();self.invalidate()

class WindowsVoice:
    """SAPI inicializado na thread que fala; pt-BR instalado no Windows."""
    def __init__(self,rate=175):self.rate=rate;self.last_voice=''
    def speak(self,text,output_device=None):
        import pythoncom,win32com.client
        pythoncom.CoInitialize()
        try:
            voice=win32com.client.Dispatch('SAPI.SpVoice')
            for token in voice.GetVoices():
                if '416' in token.GetAttribute('Language').lower():voice.Voice=token;break
            self.last_voice=voice.Voice.GetDescription()
            if 'portug' not in self.last_voice.lower():raise RuntimeError('Voz portuguesa nao instalada no Windows')
            voice.Rate=max(-5,min(5,round((self.rate-175)/25)));voice.Volume=90
            if output_device:
                for token in voice.GetAudioOutputs():
                    if output_device.casefold() in token.GetDescription().casefold():voice.AudioOutput=token;break
            voice.Speak(text,0)
        finally:pythoncom.CoUninitialize()

class PiperVoiceBackend:
    """Voz neural masculina pt-BR; inferencia e reproducao integralmente locais."""
    def __init__(self,path,length_scale=1.0):
        self.path=Path(path);self.length_scale=length_scale;self.model=None
        self.last_voice='Piper · '+self.path.stem.split('-')[1].title()+' · masculino · pt-BR'
        self.lock=threading.Lock()
    def load(self):
        if self.model is None:
            from piper import PiperVoice
            self.model=PiperVoice.load(str(self.path))
        return self.model
    def synthesize_wav(self,text,path):
        import wave
        from piper import SynthesisConfig
        with self.lock:
            model=self.load()
            with wave.open(str(path),'wb') as wav:
                model.synthesize_wav(text,wav,syn_config=SynthesisConfig(length_scale=self.length_scale,noise_scale=.60,noise_w_scale=.75,volume=.85))
    def speak(self,text,output_device=None):
        import sounddevice as sd
        from piper import SynthesisConfig
        with self.lock:
            model=self.load()
            config=SynthesisConfig(length_scale=self.length_scale,noise_scale=.60,noise_w_scale=.75,volume=.85)
            stream=None
            try:
                for chunk in model.synthesize(text,syn_config=config):
                    if stream is None:
                        stream=sd.RawOutputStream(samplerate=chunk.sample_rate,channels=chunk.sample_channels,dtype='int16',device=output_device)
                        stream.start()
                    stream.write(chunk.audio_int16_bytes)
            finally:
                if stream:stream.stop();stream.close()
