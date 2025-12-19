# AuthStatus.msg
# 암구호 인증 상태 브로드캐스트용

# 상태 상수
uint8 IDLE = 0           # 대기 중
uint8 LISTENING = 1      # 녹음 중
uint8 PROCESSING = 2     # STT 처리 중
uint8 SUCCESS = 3        # 인증 성공
uint8 FAILED = 4         # 인증 실패
uint8 ERROR = 5          # 오류 발생

# 현재 상태
uint8 status

# 인식된 텍스트 (STT 결과)
string recognized_text

# 설정된 암구호 (마스킹 가능)
string expected_passphrase

# 타임스탬프
builtin_interfaces/Time stamp
