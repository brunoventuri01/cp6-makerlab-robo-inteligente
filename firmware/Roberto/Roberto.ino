// Roberto CP5: Uno R3/Nano CLASSICO ATmega328P, 5 V. Servo sinal D9.
// LED em serie com resistor externo (ex.: 330 ohms), entre D6 e GND.
// D6 usa OUTPUT/HIGH para brilho normal. Nao conectar LED sem resistor.
// Protocolo por linha: {"id":"abc123","action":"ARM_UP"}
// ACK so depois de aplicar o comando. Sem sensor: nao comprova posicao mecanica.
#include <Servo.h>
Servo braco;
const int PIN_SERVO=9, PIN_LED=6;
// Calibrar SEM o braco antes de aumentar o curso. USB deve ser validado sob carga.
const int ANGULO_BAIXO=90, ANGULO_ALTO=180;
int atual=ANGULO_BAIXO;
String linha;
void luz(bool acesa){
  pinMode(PIN_LED,OUTPUT);
  digitalWrite(PIN_LED,acesa?HIGH:LOW);
}
String campo(const String &s,const String &nome){
  int i=s.indexOf("\""+nome+"\""); if(i<0)return "";
  i=s.indexOf(':',i); i=s.indexOf('"',i);if(i<0)return "";
  int fim=s.indexOf('"',i+1);return fim<0?"":s.substring(i+1,fim);
}
void mover(int destino){
  while(atual!=destino){atual+=destino>atual?1:-1;braco.write(atual);delay(20);}
}
void executar(String s){
  String id=campo(s,"id"),acao=campo(s,"action");
  if(id.length()==0||id.length()>32)return;
  for(unsigned int i=0;i<id.length();i++)if(!isAlphaNumeric(id[i]))return;
  bool ok=true;
  if(acao=="ARM_UP")mover(ANGULO_ALTO);
  else if(acao=="ARM_DOWN")mover(ANGULO_BAIXO);
  else if(acao=="LED_ON")luz(true);
  else if(acao=="LED_OFF")luz(false);
  else if(acao=="WAVE"){int anterior=atual;for(int i=0;i<2;i++){mover(ANGULO_ALTO);mover(ANGULO_ALTO-20);}mover(anterior);}
  else ok=false;
  Serial.print("{\"id\":\"");Serial.print(id);Serial.print("\",\"ok\":");Serial.print(ok?"true":"false");Serial.println("}");
}
void setup(){luz(false);braco.attach(PIN_SERVO);braco.write(atual);Serial.begin(115200);linha.reserve(160);}
void loop(){while(Serial.available()){char c=Serial.read();if(c=='\n'){executar(linha);linha="";}else if(c!='\r'){if(linha.length()<160)linha+=c;else linha="";}}}
