# backend/app/routers/people.py
import base64
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import crud
from app.schemas import PeopleResponse

router = APIRouter(prefix="/people", tags=["People"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


#  사람 목록 반환 + Base64 변환
@router.get("/", response_model=list[PeopleResponse])
def list_people(db: Session = Depends(get_db)):
    people = crud.get_people(db)

    # binary → base64 변환
    for p in people:
        if p.picture:
            p.picture = base64.b64encode(p.picture).decode("utf-8")

    return people

#  군번으로 사람 조회 + Base64 변환
@router.get("/search/{serial}", response_model=PeopleResponse)
def search_person(serial: str, db: Session = Depends(get_db)):
    person = crud.get_person_by_serial(db, serial)
    if not person:
        raise HTTPException(404, "Person not found")
    if person.picture:
        person.picture = base64.b64encode(person.picture).decode("utf-8")

    return person

#  JSON 방식 등록 (백워드 호환)
@router.post("/json")
def create_person_json(data: dict, db: Session = Depends(get_db)):
    return crud.create_person(db, data)


#  사진 지원 Form-data 방식 등록 엔드포인트
@router.post("/register", response_model=PeopleResponse)
async def register_person(
    military_serial: str = Form(...),
    name: str = Form(...),
    department: str = Form(...),
    rank: str = Form(...),
    picture: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    # 파일 binary 읽기
    picture_bytes = None
    if picture:
        picture_bytes = await picture.read()

    person = crud.create_person(
        db,
        {
            "military_serial": military_serial,
            "name": name,
            "department": department,
            "rank": rank,
            "picture": picture_bytes,
        },
    )

    # Response 변환 시 Base64 처리
    if person.picture:
        person.picture = base64.b64encode(person.picture).decode("utf-8")

    return person


#  삭제 API (기존 그대로 유지)
@router.delete("/{serial}")
def delete(serial: str, db: Session = Depends(get_db)):
    deleted = crud.delete_person(db, serial)
    if not deleted:
        raise HTTPException(404, "Person not found")
    return {"message": "Deleted"}
