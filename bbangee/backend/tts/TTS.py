from openai import OpenAI
import sounddevice as sd
import numpy as np

class TTS:
    def __init__(self, engine_type="openai", voice_id="onyx"):
        self.client = OpenAI()
        self.voice_id = voice_id

    def speak(self, text: str) -> bool:
        response = self.client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice=self.voice_id,
            input=text
        )

        audio = np.frombuffer(response.read(), dtype=np.int16)
        sd.play(audio, samplerate=24000)
        sd.wait()
        return True
