from fastapi import APIRouter
from pydantic import BaseModel
from tts.classify_real import ClassifyVoice

router = APIRouter(prefix="/voice", tags=["Voice"])
voice = ClassifyVoice()

class VoiceRequest(BaseModel):
    is_ally: bool

@router.post("/classify")
def speak_classify(req: VoiceRequest):
    success = voice.speak_result(req.is_ally)
    return {"success": success}
