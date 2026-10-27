"""Assistente local para gravar firmware pre-compilado; nenhum terminal necessario."""
import json,os,subprocess,threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox
from serial.tools import list_ports
ROOT=Path(__file__).resolve().parent
BOARDS={'Arduino Uno R3':('uno','arduino:avr:uno'),'Arduino Nano clássico':('nano','arduino:avr:nano:cpu=atmega328'),'Nano clássico — bootloader antigo':('nano_old','arduino:avr:nano:cpu=atmega328old')}
def main():
    window=tk.Tk();window.title('Roberto — Gravar Arduino');window.geometry('680x440')
    frame=ttk.Frame(window,padding=22);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Gravar o programa do Roberto no Arduino',font=('Segoe UI',16,'bold')).pack(anchor='w')
    ttk.Label(frame,text='Primeiro grave SOMENTE a placa, sem LED nem servo conectados.\nFeche o Monitor Serial e deixe o painel em SIMULAÇÃO.',wraplength=620).pack(anchor='w',pady=12)
    board=tk.StringVar(value='Arduino Uno R3');port=tk.StringVar()
    ttk.Label(frame,text='Sua placa').pack(anchor='w');ttk.Combobox(frame,textvariable=board,values=list(BOARDS),state='readonly',width=48).pack(anchor='w',pady=5)
    ttk.Label(frame,text='Porta USB (COM)').pack(anchor='w');ports=ttk.Combobox(frame,textvariable=port,state='readonly',width=48);ports.pack(anchor='w',pady=5)
    status=tk.StringVar(value='Conecte o Arduino com um cabo USB de dados e atualize as portas.')
    ttk.Label(frame,textvariable=status,wraplength=620).pack(anchor='w',pady=14)
    def refresh():
        values=[p.device for p in list_ports.comports()];ports['values']=values
        if values:port.set(values[0])
        else:port.set('');status.set('Nenhuma porta encontrada. Confira o cabo de dados e o driver da placa.')
    def finish(ok,text):
        button['state']='normal';status.set(text)
        if ok:messagebox.showinfo('Roberto','Gravação concluída. Desconecte o USB antes de ligar os fios. Consulte o guia de montagem.')
        else:messagebox.showerror('Roberto',text)
    def worker():
        try:
            kind,fqbn=BOARDS[board.get()];runtime=ROOT/'runtime';config=runtime/'arduino-config.yaml'
            config.write_text('directories:\n  data: '+json.dumps(str(runtime/'arduino-data'))+'\n  downloads: '+json.dumps(str(runtime/'arduino-downloads'))+'\n  user: '+json.dumps(str(runtime/'arduino-user'))+'\n',encoding='utf-8')
            command=[str(runtime/'arduino-cli'/'arduino-cli.exe'),'--config-file',str(config),'upload','--fqbn',fqbn,'--port',port.get(),'--input-dir',str(ROOT/'firmware'/'compilado'/kind)]
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=75,creationflags=0x08000000)
            (ROOT/'data'/'logs').mkdir(parents=True,exist_ok=True);(ROOT/'data'/'logs'/'gravacao_arduino.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
            text='Gravação concluída. Tire o USB antes de montar os fios.' if result.returncode==0 else 'A gravação falhou. Confira a placa, a porta COM e se outro programa ocupa a porta. Para Nano, tente o bootloader antigo. Detalhes em data/logs/gravacao_arduino.log.'
            window.after(0,lambda:finish(result.returncode==0,text))
        except Exception as exc:
            text=str(exc);window.after(0,lambda:finish(False,text))
    def upload():
        if not port.get():messagebox.showwarning('Roberto','Selecione a porta COM do Arduino.');return
        if not messagebox.askyesno('Gravar Arduino','Isto substitui o programa atual da placa selecionada.\nLED e servo estão desconectados? Deseja gravar?'):return
        button['state']='disabled';status.set('Gravando… aguarde. Não desconecte o USB.');threading.Thread(target=worker,daemon=True).start()
    buttons=ttk.Frame(frame);buttons.pack(anchor='w');ttk.Button(buttons,text='Atualizar portas',command=refresh).pack(side='left',padx=(0,10));button=ttk.Button(buttons,text='Gravar Roberto no Arduino',command=upload);button.pack(side='left')
    refresh();window.mainloop()
if __name__=='__main__':main()
