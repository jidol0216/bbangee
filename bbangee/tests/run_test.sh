#!/bin/bash
# 시나리오 테스트 실행 스크립트

cd "$(dirname "$0")"

echo "====================================="
echo "  시나리오 테스트 도구"
echo "====================================="
echo ""

# 서버 체크
if ! curl -s http://localhost:8000/scenario/status > /dev/null 2>&1; then
    echo "❌ 백엔드 서버가 실행 중이 아닙니다!"
    echo ""
    echo "다음 명령으로 서버를 먼저 시작하세요:"
    echo ""
    echo "  cd /home/rokey/ros2_ws/src/bbangee/bbangee/backend"
    echo "  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
    echo ""
    exit 1
fi

echo "✅ 서버 연결 확인됨"
echo ""

python3 test_scenario.py "$@"
