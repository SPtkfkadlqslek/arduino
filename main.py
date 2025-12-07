# 예시 파이썬 스크립트 (pyserial, requests 라이브러리 필요)
import serial
import time
import requests
import datetime
import json

# --- 아두이노 시리얼 통신 설정 ---
arduino_port = 'COM5' 
baud_rate = 9600
ser = serial.Serial(arduino_port, baud_rate, timeout=1)
time.sleep(2) # 시리얼 포트 연결 대기

# --- 기상청 API 설정 ---
api_key = "74104ce75d56baaaa24697ad4cec939e7d73de4e39cd81e78bdb95013ffa595b" 
# 광양시 기준 격자 좌표 (기상청 API 활용가이드 참고하여 정확한 좌표 확인 필요)
# 위도 34.93, 경도 127.69 (광양시청/지리 좌표 위치) -> 격자 X: 61, Y: 125
weather_nx = 35
weather_ny = 127.6

# 기상청 단기예보 발표 시각 리스트
# 이 시각 이전에 호출했다면 이전 시각 발표 자료를 가져와야 함.
KMA_FORECAST_BASE_TIMES = ["0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300"]

# 현재 시각을 기준으로 가장 적절한 base_time을 찾는 함수
def get_kma_base_time(now_dt):
    current_hour_minute = now_dt.strftime("%H%M")
    base_time_to_use = None
    
    # 현재 시간보다 이전에 발표된 시간 중 가장 가까운 것을 찾음
    for bt in reversed(KMA_FORECAST_BASE_TIMES):
        if current_hour_minute >= bt:
            base_time_to_use = bt
            break
            
    if base_time_to_use is None: # 현재 시간이 0200 이전이면, 전날 2300 데이터를 사용
        base_time_to_use = "2300"
        now_dt -= datetime.timedelta(days=1) # 날짜도 전날로 변경
        
    return now_dt.strftime("%Y%m%d"), base_time_to_use

# 비/눈 예보를 확인하는 함수
def check_weather_forecast(nx, ny, detection_time):
    # 감지 시점부터 다음 날 오전 3시까지의 기간 설정
    today_03am = detection_time.replace(hour=3, minute=0, second=0, microsecond=0)
    target_end_time = (detection_time + datetime.timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)

    # 만약 감지 시간이 오늘 03:00am을 지났다면, 내일 03:00am까지를 의미
    if detection_time >= today_03am:
        # 이미 오늘 03시를 지났으니, 내일 03시까지로 설정
        target_end_time = (detection_time + datetime.timedelta(days=1)).replace(hour=3, minute=0, second=0, microsecond=0)
    else:
        # 아직 오늘 03시 이전이라면, 오늘 03시까지로 설정
        target_end_time = today_03am

    # API 호출을 위한 base_date, base_time 설정
    base_date, base_time = get_kma_base_time(detection_time)
    
    url = f"http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst?serviceKey={api_key}&pageNo=1&numOfRows=1000&dataType=JSON&base_date={base_date}&base_time={base_time}&nx={nx}&ny={ny}"

    response = requests.get(url)
    data = response.json()
    
    rain_snow_forecasted = False
    
    if 'response' in data and 'body' in data['response'] and 'items' in data['response']['body']:
        items = data['response']['body']['items']['item']
        for item in items:
            # 예보 시간 (fcstDate, fcstTime) 조합하여 datetime 객체 생성
            fcst_datetime_str = item.get('fcstDate') + item.get('fcstTime')
            try:
                fcst_datetime = datetime.datetime.strptime(fcst_datetime_str, "%Y%m%d%H%M")
            except ValueError:
                continue # 시간 형식이 올바르지 않으면 건너뛰기

            # 센서 감지 시간부터 타겟 종료 시간까지의 예보만 필터링
            if detection_time <= fcst_datetime < target_end_time:
                if item['category'] == 'PTY': # PTY: 강수 형태
                    pty_code = int(item['fcstValue'])
                    # PTY 코드: 0(없음), 1(비), 2(비/눈), 3(눈), 4(소나기), 5(빗방울), 6(빗방울눈날림), 7(눈날림)
                    if pty_code in [1, 2, 3, 4, 5, 6, 7]: # 비/눈과 관련된 코드 
                        print(f"Rain/Snow forecast found at {fcst_datetime.strftime('%Y-%m-%d %H:%M')}, PTY: {pty_code}")
                        rain_snow_forecasted = True
                        break # 하나라도 찾으면 더 이상 확인할 필요 없음
    
    return rain_snow_forecasted

last_temp_detection_time = None
human_detected_on_arduino = False # 아두이노에서 사람 감지 여부 플래그
                                    # 파이썬은 이 플래그가 True일 때만 날씨 API 호출

while True:
    try:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8').strip()
            # print(f"Received from Arduino: {line}") # 디버깅용

            if line.startswith("TEMP:"):
                temperature_str = line.split(":")[1]
                try:
                    current_temp = float(temperature_str)
                    # print(f"Current Temperature: {current_temp}°C")

                    # 사람으로 판단되는 온도 감지 (확실한 온도 측정을 위해 평균 체온 보다 낮은 온도로 설정)
                    if current_temp >= 28.0:
                        if not human_detected_on_arduino: # 새로 사람이 감지되었다면
                            print(f"Human-like temperature detected! Current Temp: {current_temp}°C")
                            human_detected_on_arduino = True
                            last_temp_detection_time = datetime.datetime.now() # 감지 시간 기록
                            
                            # #-------------------(작동 시연을 위해 날씨가 맑을 경우 작동)-----------------------------------
                            # if check_weather_forecast(weather_nx, weather_ny, last_temp_detection_time):
                            #     print("--- [데모 모드] 비/눈 예보 감지. 작동 시연을 위해 'C' 명령 전송 ---")
                            #     ser.write(b'C')
                            # else:
                            #     print("--- [데모 모드] 비/눈 예보 없음. 작동 시연을 위해 'R' 명령 전송 ---")
                            #     ser.write(b'R')
                            # #------------------------------------------------------------------------------------------
                            
                            # 비/눈 예보 확인 -------------------------------------------------------------------------
                            print(f"Checking weather forecast from {last_temp_detection_time.strftime('%Y-%m-%d %H:%M')}")
                            if check_weather_forecast(weather_nx, weather_ny, last_temp_detection_time):
                                print("비/눈 예보가 있음. 아두이노에 'R' 명령 전송.")
                                ser.write(b'R')
                            else:
                                print("비/눈 예보가 없음. 아두이노에 'C' 명령 전송.")
                                ser.write(b'C') 
                            # ---------------------------------------------------------------------------------------
                    else: # 온도가 30도 미만으로 떨어지면
                        if human_detected_on_arduino: # 이전에 사람이 감지되었다가 사라진 경우
                            print(f"Temperature dropped below human threshold. Current Temp: {current_temp}°C")
                            ser.write(b'C') # 아두이노에 'C' 명령 전송하여 LED 끄고 부저 정지
                            human_detected_on_arduino = False

                except ValueError:
                    print(f"Failed to parse temperature: {temperature_str}")
            else:
                # 아두이노에서 오는 다른 메시지도 출력 (디버깅)
                pass # print(f"Arduino says: {line}") 

    except serial.SerialException as e:
        print(f"Serial port error: {e}")
        break
    except requests.exceptions.RequestException as e:
        print(f"KMA API request error: {e}")
        # API 오류 발생 시 아두이노 비활성화
        ser.write(b'C')
        # 일정 시간 후 다시 시도하거나, 재연결 로직 추가 고려
        time.sleep(10) # 10초 대기 후 다시 시도
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        ser.write(b'C')
        # 심각한 오류 시 스크립트 종료하거나 복구 로직 추가
        break 

    time.sleep(0.1) # 파이썬 루프 딜레이 (조정 가능)
