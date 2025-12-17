#!/usr/bin/env python3
"""
시나리오 테스트 스크립트

4가지 시나리오를 테스트:
1. ALLY_PASS - 아군 + 암구호 정답
2. ALLY_ALERT - 아군 + 암구호 오답  
3. ENEMY_CRITICAL - 적군 + 암구호 정답
4. ENEMY_ENGAGE - 적군 + 암구호 오답

사용법:
  python test_scenario.py              # 대화형 메뉴
  python test_scenario.py 1            # 시나리오 1 직접 실행
  python test_scenario.py --all        # 모든 시나리오 순차 실행
"""

import requests
import time
import sys

BASE_URL = "http://localhost:8000"

# 색상 코드
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text:^60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")

def print_step(step, text):
    print(f"{Colors.CYAN}[Step {step}]{Colors.ENDC} {text}")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")

def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.ENDC}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.ENDC}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.ENDC}")


def check_server():
    """서버 연결 확인"""
    try:
        r = requests.get(f"{BASE_URL}/scenario/status", timeout=2)
        return r.status_code == 200
    except:
        return False


def get_status():
    """현재 시나리오 상태 조회"""
    r = requests.get(f"{BASE_URL}/scenario/status")
    return r.json()


def reset_scenario():
    """시나리오 리셋"""
    r = requests.post(f"{BASE_URL}/scenario/reset")
    return r.json()


def trigger_detection():
    """얼굴 감지 트리거 (IDLE → DETECTED)"""
    r = requests.post(f"{BASE_URL}/scenario/detect")
    return r.json()


def identify_person(is_ally: bool):
    """피아 식별 (DETECTED → PASSWORD_CHECK)"""
    r = requests.post(f"{BASE_URL}/scenario/identify", json={"is_ally": is_ally})
    return r.json()


def submit_password(password: str):
    """암구호 제출"""
    r = requests.post(f"{BASE_URL}/scenario/password", json={"password": password})
    return r.json()


def get_current_password():
    """현재 암구호 조회"""
    r = requests.get(f"{BASE_URL}/scenario/password")
    return r.json()


def run_scenario(scenario_num: int, delay: float = 1.0):
    """
    시나리오 실행
    
    1: ALLY_PASS - 아군 + 정답
    2: ALLY_ALERT - 아군 + 오답
    3: ENEMY_CRITICAL - 적군 + 정답
    4: ENEMY_ENGAGE - 적군 + 오답
    """
    
    scenarios = {
        1: ("ALLY_PASS", True, True, "아군 + 암구호 정답 → 통과 승인"),
        2: ("ALLY_ALERT", True, False, "아군 + 암구호 오답 → 경고"),
        3: ("ENEMY_CRITICAL", False, True, "적군 + 암구호 정답 → 기밀유출!"),
        4: ("ENEMY_ENGAGE", False, False, "적군 + 암구호 오답 → 침입자 대응"),
    }
    
    if scenario_num not in scenarios:
        print_error(f"잘못된 시나리오 번호: {scenario_num}")
        return False
    
    name, is_ally, correct_password, description = scenarios[scenario_num]
    
    print_header(f"시나리오 {scenario_num}: {name}")
    print_info(description)
    print()
    
    # 1. 리셋
    print_step(1, "시나리오 리셋...")
    result = reset_scenario()
    if result.get("success"):
        print_success(f"상태: {result.get('state')}")
    else:
        print_error("리셋 실패")
        return False
    time.sleep(delay)
    
    # 2. 현재 암구호 확인
    print_step(2, "현재 암구호 확인...")
    pw_info = get_current_password()
    challenge = pw_info.get("challenge", "로키")
    response = pw_info.get("response", "협동")
    print_info(f"Challenge: {challenge} / Response: {response}")
    time.sleep(delay * 0.5)
    
    # 3. 얼굴 감지
    print_step(3, "얼굴 감지 트리거...")
    result = trigger_detection()
    if result.get("success"):
        print_success(f"상태: {result.get('state')}")
        print_info("TTS: '정지! 신원을 확인합니다.'")
    else:
        print_warning(f"이미 감지 상태: {result.get('message')}")
    time.sleep(delay)
    
    # 4. 피아 식별
    person_type = "아군" if is_ally else "적군"
    print_step(4, f"피아 식별: {person_type}...")
    result = identify_person(is_ally)
    if result.get("success"):
        print_success(f"상태: {result.get('state')} / 식별: {result.get('person_type')}")
        print_info(f"TTS: '암구호! {challenge}!'")
    else:
        print_error(f"식별 실패: {result.get('message')}")
        return False
    time.sleep(delay)
    
    # 5. 암구호 제출
    password_to_submit = response if correct_password else "틀린암구호"
    correct_str = "정답" if correct_password else "오답"
    print_step(5, f"암구호 제출 ({correct_str}): '{password_to_submit}'...")
    result = submit_password(password_to_submit)
    
    if result.get("success"):
        state = result.get("state")
        is_correct = result.get("is_correct")
        message = result.get("message")
        
        # 결과 출력
        print()
        if state == "ALLY_PASS":
            print_success(f"🎖️  결과: {state}")
            print_info("TTS: '확인되었습니다. 통과하세요.'")
            print_info("로봇: 경례 모션")
        elif state == "ALLY_ALERT":
            print_warning(f"⚠️  결과: {state}")
            print_info("TTS: '암구호가 틀렸습니다. 움직이지 마세요.'")
            print_info("로봇: High Ready 유지")
        elif state == "ENEMY_CRITICAL":
            print_error(f"🚨 결과: {state}")
            print_info("TTS: '경고! 기밀 유출 의심! 비상 알림 발령!'")
            print_info("로봇: 추적 속도 1.5배 가속")
        elif state == "ENEMY_ENGAGE":
            print_error(f"🔴 결과: {state}")
            print_info("TTS: '침입자 발견! 대응 조치!'")
            print_info("로봇: 추적 속도 1.5배 가속")
        
        print()
        print_success(f"시나리오 {scenario_num} ({name}) 완료!")
        return True
    else:
        print_error(f"암구호 제출 실패: {result.get('message')}")
        return False


def test_ocr_auto_identify():
    """OCR 자동 피아식별 테스트"""
    print_header("OCR 자동 피아식별 테스트")
    
    # 리셋
    print_step(1, "시나리오 리셋...")
    reset_scenario()
    time.sleep(0.5)
    
    # 감지 트리거
    print_step(2, "얼굴 감지 트리거...")
    trigger_detection()
    time.sleep(0.5)
    
    # OCR 결과 시뮬레이션 (연속 3회)
    print_step(3, "OCR 결과 시뮬레이션 (아군 3회 연속)...")
    
    for i in range(3):
        r = requests.post(f"{BASE_URL}/scenario/ocr", json={
            "armband_detected": True,
            "faction": "ALLY",
            "confidence": 0.85
        })
        result = r.json()
        print_info(f"  [{i+1}/3] {result.get('message', result)}")
        
        if result.get("auto_identified"):
            print_success(f"🎯 자동 피아식별 완료! 상태: {result.get('state')}")
            break
        
        time.sleep(0.3)
    
    # 현재 상태 확인
    status = get_status()
    print_info(f"최종 상태: {status.get('state')}")


def test_ocr_fail_tts():
    """OCR 실패 TTS 테스트"""
    print_header("OCR 실패 TTS 안내 테스트")
    
    # 리셋
    print_step(1, "시나리오 리셋...")
    reset_scenario()
    time.sleep(0.5)
    
    # 감지 트리거
    print_step(2, "얼굴 감지 트리거...")
    trigger_detection()
    time.sleep(0.5)
    
    # OCR 실패 시뮬레이션 (10회 이상)
    print_step(3, "OCR 실패 시뮬레이션 (완장감지O + OCR실패 12회)...")
    
    for i in range(12):
        r = requests.post(f"{BASE_URL}/scenario/ocr", json={
            "armband_detected": True,
            "faction": "UNKNOWN",
            "confidence": 0.0
        })
        result = r.json()
        
        if i == 9:  # 10번째에서 TTS가 나와야 함
            print_info(f"  [{i+1}/12] {result.get('message', result)}")
            if result.get('ocr_fail_count', 0) >= 10:
                print_warning("TTS: '카메라 렌즈에 피아식별띠를 잘 보이게 위치시키십시오.'")
        
        time.sleep(0.1)
    
    print_success("OCR 실패 TTS 테스트 완료!")


def interactive_menu():
    """대화형 메뉴"""
    while True:
        print_header("시나리오 테스트 메뉴")
        print("  1. ALLY_PASS    - 아군 + 암구호 정답 → 통과 승인")
        print("  2. ALLY_ALERT   - 아군 + 암구호 오답 → 경고")
        print("  3. ENEMY_CRITICAL - 적군 + 암구호 정답 → 기밀유출")
        print("  4. ENEMY_ENGAGE - 적군 + 암구호 오답 → 침입자 대응")
        print()
        print("  5. OCR 자동 피아식별 테스트")
        print("  6. OCR 실패 TTS 테스트")
        print()
        print("  a. 모든 시나리오 순차 실행 (1~4)")
        print("  s. 현재 상태 확인")
        print("  r. 리셋")
        print("  q. 종료")
        print()
        
        choice = input(f"{Colors.CYAN}선택 > {Colors.ENDC}").strip().lower()
        
        if choice == 'q':
            print_info("테스트 종료")
            break
        elif choice == 's':
            status = get_status()
            print_info(f"현재 상태: {status.get('state')}")
            print_info(f"피아 유형: {status.get('person_type')}")
        elif choice == 'r':
            reset_scenario()
            print_success("리셋 완료")
        elif choice == 'a':
            for i in range(1, 5):
                run_scenario(i, delay=1.5)
                time.sleep(2)
                print("\n" + "="*60 + "\n")
        elif choice == '5':
            test_ocr_auto_identify()
        elif choice == '6':
            test_ocr_fail_tts()
        elif choice in ['1', '2', '3', '4']:
            run_scenario(int(choice))
        else:
            print_warning("잘못된 입력입니다")
        
        print()
        input(f"{Colors.BLUE}Enter를 눌러 계속...{Colors.ENDC}")


def main():
    print_header("시나리오 테스트 시작")
    
    # 서버 연결 확인
    print_step(0, "백엔드 서버 연결 확인...")
    if not check_server():
        print_error("백엔드 서버에 연결할 수 없습니다!")
        print_info("다음 명령으로 서버를 시작하세요:")
        print()
        print(f"  cd /home/rokey/ros2_ws/src/bbangee/bbangee/backend")
        print(f"  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
        print()
        return
    
    print_success("서버 연결 성공!")
    
    # 명령줄 인자 처리
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == '--all':
            for i in range(1, 5):
                run_scenario(i)
                time.sleep(2)
        elif arg == '--ocr':
            test_ocr_auto_identify()
        elif arg == '--ocr-fail':
            test_ocr_fail_tts()
        elif arg.isdigit():
            run_scenario(int(arg))
        else:
            print_warning(f"알 수 없는 인자: {arg}")
            print_info("사용법: python test_scenario.py [1-4|--all|--ocr|--ocr-fail]")
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
