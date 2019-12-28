int OUTPUT_PROBE = 5;
int SENSE_VOLT_PROBE = A0;
int LOAD_VOLT_PROBE = A1;

void setup() {
  pinMode(OUTPUT_PROBE, OUTPUT);
  pinMode(SENSE_VOLT_PROBE, INPUT);
  pinMode(LOAD_VOLT_PROBE, INPUT);

  analogWrite(OUTPUT_PROBE, 0);
  
  Serial.begin(9600);
  while (!Serial) {
    ; // wait for serial port to connect. Needed for native USB port only
  }
  establishContact();  // send a byte to establish contact until receiver responds
}

String command = "";
void loop() {
  char inByte;
  if (Serial.available() > 0) {
    inByte = Serial.read();
    if (inByte == 'c'){
      command.trim();

      String op = command.substring(0,3);
      String val = command.substring(3);
      val.trim();
      int value = val.toInt();

      if (op == "set"){
        analogWrite(OUTPUT_PROBE, value);
        Serial.println(0);
      }
      else if (op == "get"){
        int readValue;
        if (value == 0){
          Serial.println(analogRead(SENSE_VOLT_PROBE));
        }
        else {
          Serial.println(analogRead(LOAD_VOLT_PROBE));
        }
      }
      else{
        Serial.println(-1);
      }
      command = "";
    }
    else{
      command = command + inByte;
    }
  }
}

void establishContact() {
  while (Serial.available() <= 0) {
    Serial.write(13);   // send a capital A
    delay(300);
  }
}
