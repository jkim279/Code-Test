#!/usr/bin/env python3
"""
뉴스 클리핑 에이전트
매일 관심 주제의 최신 뉴스를 자동으로 수집하고 요약합니다.

API 키 없이 Claude Code 계정으로 실행됩니다.

사용법:
    python news_agent.py                    # 기본 실행
    python news_agent.py --save             # 결과를 파일로 저장
    python news_agent.py --config my.yaml   # 다른 설정 파일 사용
"""

import anyio
import yaml
import os
import sys
import argparse
from datetime import date
from pathlib import Path

from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage


def load_config(config_path: str = "config.yaml") -> dict:
    """설정 파일을 로드합니다."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


async def run_news_agent(config: dict) -> str:
    """Claude Agent SDK를 사용해 뉴스를 검색하고 요약합니다."""
    topics = config.get("topics", [])
    language = config.get("language", "Korean")
    articles_per_topic = config.get("articles_per_topic", 3)

    today_str = date.today().strftime("%Y년 %m월 %d일")
    topics_str = ", ".join(topics)
    lang_note = "한국어로 작성해주세요." if language == "Korean" else "Please write in English."

    prompt = f"""오늘({today_str}) 다음 주제들의 최신 뉴스 클리핑을 만들어주세요.

관심 주제: {topics_str}

각 주제별로 웹 검색을 통해 최신 뉴스를 찾고, 주제마다 상위 {articles_per_topic}개 뉴스를 선별해서 다음 형식으로 정리해주세요:

## 📰 일일 뉴스 클리핑 - {today_str}

### [주제명]

**[뉴스 제목]**
- 요약: [3-5줄 요약]
- 출처: [출처명] | [날짜]

---
## 📊 오늘의 주요 트렌드
[전반적인 트렌드 분석 1-2 단락]

{lang_note}"""

    result = ""
    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            allowed_tools=["WebSearch"],
        ),
    ):
        if isinstance(message, ResultMessage):
            result = message.result

    return result


def save_digest(content: str, output_dir: str) -> Path:
    """뉴스 클리핑 결과를 마크다운 파일로 저장합니다."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    filename = f"news_digest_{date.today().strftime('%Y%m%d')}.md"
    filepath = output_path / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def main():
    parser = argparse.ArgumentParser(
        description="일일 뉴스 클리핑 에이전트 (API 키 불필요)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python news_agent.py                    기본 실행
  python news_agent.py --save             결과 파일 저장 (./digests/)
  python news_agent.py --config my.yaml   다른 설정 파일 사용
        """,
    )
    parser.add_argument("--config", default="config.yaml", help="설정 파일 경로")
    parser.add_argument("--save", action="store_true", help="결과를 파일로 저장")
    parser.add_argument("--output-dir", default=None, help="저장 디렉토리")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    today_str = date.today().strftime("%Y년 %m월 %d일")
    topics = config.get("topics", [])

    print()
    print("=" * 60)
    print("  📰 일일 뉴스 클리핑 에이전트")
    print(f"  📅 {today_str}")
    if topics:
        print(f"  🔖 관심 주제: {', '.join(topics)}")
    print("=" * 60)
    print()
    print("🔍 뉴스 검색 중...\n")

    try:
        digest = anyio.run(run_news_agent, config)
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        sys.exit(1)

    print(digest)

    output_dir = args.output_dir or config.get("output_dir", "./digests")
    if args.save or config.get("auto_save", False):
        try:
            filepath = save_digest(digest, output_dir)
            print(f"\n✅ 저장 완료: {filepath}")
        except OSError as e:
            print(f"⚠️  파일 저장 실패: {e}")


if __name__ == "__main__":
    main()
