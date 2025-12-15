from tts.TTS import TTS

class ClassifyVoice:
    def __init__(self):
        print("ClassifyVoice 초기화 중...")
        self.tts = TTS(engine_type="openai", voice_id="onyx")
        print("✓ TTS 준비 완료")

    def speak_result(self, is_ally: bool):
        message = "아군입니다" if is_ally else "적군입니다"
        return self.tts.speak(message)
