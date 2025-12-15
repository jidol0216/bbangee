from tts.TTS import TTS

class ClassifyVoice:
    def __init__(self):
        print("ClassifyVoice 초기화 중...")
        # gTTS 사용 (무료, API 키 불필요)
        self.tts = TTS(engine_type="gtts")
        print("✓ TTS 준비 완료 (gTTS)")

    def speak_result(self, is_ally: bool):
        message = "아군입니다" if is_ally else "적군입니다"
        return self.tts.speak(message)
    
    def ask_password(self):
        """적군 감지 시 암구호 질문"""
        message = "정지. 신원을 확인합니다. 암구호를 말씀해주세요."
        return self.tts.speak(message)
    
    def password_correct(self):
        """암구호 정답"""
        message = "확인되었습니다. 통과하세요."
        return self.tts.speak(message)
    
    def password_wrong(self):
        """암구호 오답"""
        message = "암구호가 틀렸습니다. 움직이지 마세요."
        return self.tts.speak(message)
    
    def welcome(self, name: str = None):
        """환영 인사"""
        if name:
            message = f"{name}님, 반갑습니다. 출입이 승인되었습니다."
        else:
            message = "반갑습니다. 출입이 승인되었습니다."
        return self.tts.speak(message)
    
    def access_denied(self):
        """출입 거부"""
        message = "출입이 거부되었습니다. 관리자에게 문의하세요."
        return self.tts.speak(message)
