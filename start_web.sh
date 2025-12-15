#!/bin/bash
# ==========================================
# bbangee 웹 서버 실행 스크립트
# Ctrl+C로 종료하면 자동으로 모든 프로세스 정리
# ==========================================

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# PID 저장용
BACKEND_PID=""
FRONTEND_PID=""

# 종료 시 정리 함수
cleanup() {
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  서버 종료 중...${NC}"
    echo -e "${RED}========================================${NC}"
    
    # 백엔드 종료
    if [ -n "$BACKEND_PID" ] && kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${YELLOW}백엔드 종료 (PID: $BACKEND_PID)${NC}"
        kill $BACKEND_PID 2>/dev/null
    fi
    
    # 프론트엔드 종료
    if [ -n "$FRONTEND_PID" ] && kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${YELLOW}프론트엔드 종료 (PID: $FRONTEND_PID)${NC}"
        kill $FRONTEND_PID 2>/dev/null
    fi
    
    # 혹시 남아있는 프로세스 정리
    pkill -f "uvicorn app.main:app" 2>/dev/null
    pkill -f "vite" 2>/dev/null
    
    echo -e "${GREEN}✅ 모든 서버 종료 완료!${NC}"
    exit 0
}

# Ctrl+C (SIGINT) 및 종료 시그널 처리
trap cleanup SIGINT SIGTERM EXIT

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  bbangee 웹 서버 시작${NC}"
echo -e "${GREEN}========================================${NC}"

# 기존 프로세스 종료
echo -e "${YELLOW}기존 서버 종료 중...${NC}"
pkill -f "uvicorn app.main:app" 2>/dev/null
pkill -f "vite" 2>/dev/null
sleep 1

# 백엔드 시작
echo -e "${YELLOW}백엔드 서버 시작 (포트 8000)...${NC}"
cd /home/rokey/ros2_ws/src/bbangee/bbangee/backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
echo "  → 백엔드 PID: $BACKEND_PID"

# 프론트엔드 시작
echo -e "${YELLOW}프론트엔드 서버 시작 (포트 5173)...${NC}"
cd /home/rokey/ros2_ws/src/bbangee/bbangee/frontend
npm run dev -- --host 0.0.0.0 > /tmp/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "  → 프론트엔드 PID: $FRONTEND_PID"

sleep 2

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  서버 실행 완료!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  📡 백엔드 API:  http://localhost:8000"
echo -e "  🌐 프론트엔드:  http://localhost:5173"
echo ""
echo -e "  📋 로그 확인:"
echo -e "     tail -f /tmp/backend.log"
echo -e "     tail -f /tmp/frontend.log"
echo ""
echo -e "${YELLOW}  ⏹️  Ctrl+C 를 누르면 모든 서버가 자동 종료됩니다${NC}"
echo ""

# 프로세스가 살아있는 동안 대기
# 둘 중 하나라도 죽으면 종료
while kill -0 $BACKEND_PID 2>/dev/null && kill -0 $FRONTEND_PID 2>/dev/null; do
    sleep 1
done

echo -e "${RED}서버 프로세스가 예기치 않게 종료되었습니다.${NC}"
cleanup
echo ""
