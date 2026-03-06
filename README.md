#  BBANGEE – 인원 관리 · 출입 기록 시스템

FastAPI(Backend) + React/Vite(Frontend) 기반의 **군 인원 출입관리 시스템**입니다.  
협업 개발을 위해 아키텍처, 실행 방법, 코드 규칙 등을 상세히 정리했습니다.

---

#  Table of Contents
1. 프로젝트 소개
2. 전체 아키텍처
3. 기술 스택
4. 디렉토리 구조
5. 개발 환경 세팅
6. 실행 방법 (Backend / Frontend)
7. 환경 변수 설정
8. 데이터베이스 구조
9. API 명세
10. 브랜치 전략(Git Flow)
11. 코드 컨벤션
12. Trouble Shooting

---

# 1.  프로젝트 소개

BBANGEE는 군 내 인원 관리 및 출입 기록 자동화를 목표로 하는 시스템입니다.

주요 기능:
- 인원 등록 (사진 포함)
- 인원 검색 (군번 기반)
- 출입 관리 (CHECK-IN / CHECK-OUT)
- 사용자별 출입 이력 조회
- 실시간 로그 업데이트 (2초 주기)

---

# 2.  전체 아키텍처

Frontend (Vite + React)
↓ REST API
Backend (FastAPI)
↓ ORM
SQLite Database

yaml


향후 확장 시 PostgreSQL 또는 MySQL로 교체 가능.

---

# 3.  기술 스택

### **Frontend**
- React + TypeScript
- Vite
- Axios (API 통신)
- CSS Modules / Custom UI

### **Backend**
- FastAPI
- SQLAlchemy ORM
- SQLite
- Pydantic v2

---

# 4.  디렉토리 구조

bbangee/
├── backend/
│ ├── app/
│ │ ├── routers/ # API 라우트
│ │ ├── models.py # DB 모델
│ │ ├── schemas.py # Pydantic 스키마
│ │ ├── crud.py # CRUD 로직
│ │ ├── database.py # DB 연결
│ │ └── main.py # FastAPI 엔트리포인트
│ ├── coffee.db # SQLite DB 파일
│ └── requirements.txt
│
├── frontend/
│ ├── src/
│ │ ├── api/ # axios wrapper
│ │ ├── components/
│ │ ├── hooks/
│ │ └── pages/
│ ├── public/
│ ├── package.json
│ └── vite.config.ts
│
└── README.md



# 5.  개발 환경 세팅

### 1) Clone

```bash
git clone https://github.com/your-team/bbangee.git
cd bbangee
2) Python & Node 버전
Python 3.10+

Node 18+

6.  실행 방법
Backend (FastAPI)


cd backend
python3 -m venv venv
source venv/bin/activate          # Windows → venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
실행 주소:
http://localhost:8000
Swagger 문서:
http://localhost:8000/docs

Frontend (Vite + React)

cd frontend
npm install
npm run dev
실행 주소:
http://localhost:5173

7.  환경 변수 설정 (.env)

본 프로젝트는 프론트엔드와 백엔드가 분리된 구조이므로
프론트엔드에서 접근할 백엔드 서버 주소를 환경 변수로 관리합니다.

 .env 파일은 Git에 커밋되지 않으므로
각 개발자는 로컬 환경에 맞게 직접 생성해야 합니다.

 .env 파일 생성 위치
bbangee/
└── frontend/
    └── .env

 .env 파일 내용
VITE_API_BASE_URL=http://<BACKEND_IP>:8000

예시
VITE_API_BASE_URL=http://172.30.1.55:8000


<BACKEND_IP> : 백엔드(FastAPI)가 실행 중인 PC의 로컬 IP

포트 8000 : FastAPI 기본 포트

 로컬 IP 확인 방법 (Linux / macOS)
ip addr


출력 예시:

inet 172.30.1.55/24


→ 이 경우 .env는 다음과 같이 설정합니다:

VITE_API_BASE_URL=http://172.30.1.55:8000

 주의 사항 (매우 중요)

와이파이/네트워크가 변경되면 로컬 IP도 변경될 수 있습니다.

이 경우 .env 파일의 IP를 반드시 수정 후 프론트엔드를 재시작해야 합니다.

npm run dev

API_BASE_URL=http://localhost:8000
프론트엔드의 axios 클라이언트는 이 값을 읽습니다.

8.  데이터베이스 구조
People Table
| Column          | Type     | Desc           |
| --------------- | -------- | -------------- |
| id              | int      | PK             |
| military_serial | str      | 군번             |
| name            | str      | 이름             |
| department      | str      | 소속             |
| rank            | str      | 계급             |
| picture         | blob     | Base64 변환용 RAW |
| created_at      | datetime | 등록일            |


AccessLog Table
| Column          | Type            |
| --------------- | --------------- |
| id              | int             |
| military_serial | FK(People)      |
| in_time         | datetime        |
| out_time        | datetime / null |


9.  API 명세
 GET /people
전체 인원 조회

 GET /people/search/{serial}
군번 검색

 POST /people/register
사진 포함 등록

 POST /access/{serial}/entry
입실 처리

 POST /access/{serial}/exit
퇴실 처리

 GET /access/logs/{serial}
해당 인원의 출입 이력 조회

10.  Git 브랜치 전략 (팀 협업용)
main      → 운영 배포용  
develop   → 개발 통합
feature/* → 기능 개발
fix/*     → 버그 수정
hotfix/*  → 운영 긴급 패치

11.  코드 컨벤션
Frontend
React Hooks 기반 함수형 컴포넌트

커스텀 훅으로 로직 분리 (usePersonnel)

axios API는 /src/api로 통일

TypeScript Interface 적극 사용

Backend
라우트는 routers/ 폴더에 분리

DB 작업은 모두 crud.py에서 처리

응답 검증은 반드시 Pydantic 스키마 사용

함수명은 snake_case

12.  Trouble Shooting
 프론트에서 CORS 에러 발생
→ 백엔드가 먼저 실행되었는지 확인
→ axios baseURL 확인

 CHECK-IN / CHECK-OUT 버튼이 잘못 비활성화됨
→ 최신 로그가 잘못 로딩되는 경우
→ usePersonnel() 훅에서 selectedSerialRef 확인

