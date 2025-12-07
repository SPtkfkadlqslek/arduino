// 예시 아두이노 스케치 (MLX90614, LED, 부저)
#include <Wire.h>
#include <Adafruit_MLX90614.h> // 비접촉 온도 센서 라이브러리

Adafruit_MLX90614 mlx = Adafruit_MLX90614();

const int ledPin = 11;   // LED가 연결된 핀
const int buzzerPin = 3; // 부저가 연결된 핀

// 부저 제어를 위한 변수 (비블로킹 타이머)
unsigned long buzzerStartTime = 0;
const long buzzerDuration = 2000; // 2초 (밀리초 단위)
bool buzzerActive = false;

void setup() {
  Serial.begin(9600); // 시리얼 통신 초기화 (파이썬과 속도 맞추기)
  pinMode(ledPin, OUTPUT);
  pinMode(buzzerPin, OUTPUT); // 부저 핀 출력 설정
  mlx.begin(); // MLX90614 센서 초기화

  Serial.println("Arduino ready.");
}

void loop() {
  // 1. 비접촉 온도 센서 데이터 읽기 및 파이썬으로 전송 (1초마다)
  // 너무 자주 읽으면 시리얼 버퍼에 부담을 줄 수 있으니 파이썬에서 주기적으로 요청하는 방식도 고려
  static unsigned long lastSensorReadTime = 0;
  if (millis() - lastSensorReadTime > 1000) { // 1초마다 센서 읽기
    float objectTemp = mlx.readObjectTempC();
    Serial.print("TEMP:");
    Serial.println(objectTemp);
    lastSensorReadTime = millis();
  }

  // 2. 파이썬으로부터 명령 수신 및 처리
  if (Serial.available() > 0) {
    char command = Serial.read();
    if (command == 'R') { // 'R'(Rain) 명령이 오면 비/눈 예보 -> LED 켜고 부저 2초 울림
      digitalWrite(ledPin, HIGH); // LED 켜기 (예보가 있는 동안 유지)
      if (!buzzerActive) { // 부저가 현재 울리고 있지 않으면
        tone(buzzerPin, 1000); // 1000Hz 소리 재생 시작
        buzzerStartTime = millis(); // 타이머 시작
        buzzerActive = true;
        Serial.println("Rain/Snow detected: Activating LED and Buzzer for 2 seconds.");
      }
    } else if (command == 'C') { // 'C'(Clear) 명령이 오면 맑음 -> LED 끄고 부저 멈춤
      digitalWrite(ledPin, LOW); // LED 끄기
      noTone(buzzerPin);       // 부저 소리 정지
      buzzerActive = false;
      Serial.println("Clear: Deactivating LED and Buzzer.");
    }
  }

  // 부저 2초 동안 울리고 끄는 로직 (비블로킹)
  if (buzzerActive && millis() - buzzerStartTime >= buzzerDuration) {
    noTone(buzzerPin); // 소리 정지
    buzzerActive = false;
    Serial.println("Buzzer stopped after 2 seconds.");
  }

  // 딜레이를 짧게 유지하여 루프가 자주 실행되도록.
  // 이 루프 딜레이는 센서 읽기 딜레이와는 다름.
  delay(10); // 짧은 딜레이로 다른 작업을 원활하게 처리
}