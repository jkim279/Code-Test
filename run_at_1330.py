#!/usr/bin/env python3
"""오후 1시 30분에 뉴스 클리핑을 실행하는 스케줄러"""

import time
import subprocess
import sys
from datetime import datetime, date

TARGET_HOUR = 13
TARGET_MINUTE = 30

def seconds_until_target():
    now = datetime.now()
    target = now.replace(hour=TARGET_HOUR, minute=TARGET_MINUTE, second=0, microsecond=0)
    if target <= now:
        # 이미 지났으면 내일
        from datetime import timedelta
        target += timedelta(days=1)
    return (target - now).total_seconds()

def main():
    wait_sec = seconds_until_target()
    target_time = datetime.now().replace(
        hour=TARGET_HOUR, minute=TARGET_MINUTE, second=0, microsecond=0
    )
    print(f"[스케줄러] 현재 시각: {datetime.now().strftime('%H:%M:%S')}")
    print(f"[스케줄러] 실행 예정: {target_time.strftime('%H:%M')} (대기: {int(wait_sec//3600)}시간 {int((wait_sec%3600)//60)}분)")
    sys.stdout.flush()

    time.sleep(wait_sec)

    print(f"\n[스케줄러] 오후 1시 30분 도달 - 뉴스 클리핑 시작!")
    sys.stdout.flush()

    result = subprocess.run(
        [sys.executable, "/home/user/Code-Test/news_agent.py", "--save"],
        cwd="/home/user/Code-Test",
        capture_output=False,
    )
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
