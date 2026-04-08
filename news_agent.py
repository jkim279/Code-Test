#!/usr/bin/env python3
"""
뉴스 클리핑 에이전트
매일 관심 주제의 최신 뉴스를 자동으로 수집하고 요약합니다.

사용법:
    python news_agent.py                    # 기본 실행
    python news_agent.py --save             # 결과를 파일로 저장
    python news_agent.py --config my.yaml   # 다른 설정 파일 사용
    python news_agent.py --mode rss         # RSS 피드 모드로 실행
"""

import anthropic
import yaml
import os
import sys
import argparse
import json
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# RSS 피드 지원 여부 확인 (선택적 의존성)
try:
    import feedparser
    RSS_AVAILABLE = True
except ImportError:
    RSS_AVAILABLE = False


# ─────────────────────────────────────────────
# 설정 로드
# ─────────────────────────────────────────────

def load_config(config_path: str = "config.yaml") -> dict:
    """설정 파일을 로드합니다."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────
# 웹 검색 모드 (Claude web_search 도구 사용)
# ─────────────────────────────────────────────

def build_system_prompt_web_search(config: dict, today_str: str) -> str:
    """웹 검색 모드용 시스템 프롬프트를 생성합니다."""
    topics = config.get("topics", [])
    language = config.get("language", "Korean")
    articles_per_topic = config.get("articles_per_topic", 3)
    topics_str = ", ".join(topics)

    lang_note = "한국어로 작성해주세요." if language == "Korean" else "Please write in English."

    return f"""당신은 전문 뉴스 큐레이터입니다. 웹 검색을 통해 최신 뉴스를 수집하고 일일 클리핑을 제공합니다.

오늘 날짜: {today_str}
관심 주제: {topics_str}

각 주제별로 웹 검색을 수행하여 오늘 가장 중요한 뉴스를 찾아주세요.
주제마다 최소 1회 이상 검색하고, 각 주제별 상위 {articles_per_topic}개 뉴스를 선별하세요.

다음 형식으로 일일 뉴스 클리핑을 작성하세요:

## 📰 일일 뉴스 클리핑 - {today_str}

### [주제명]

**[뉴스 제목]**
- 요약: [3-5줄 요약]
- 출처: [출처명] | [날짜]

(다음 뉴스...)

---
## 📊 오늘의 주요 트렌드
[전반적인 트렌드 분석 1-2 단락]

{lang_note}"""


def run_web_search_mode(config: dict) -> str:
    """Claude의 web_search 도구를 사용해 뉴스를 수집하고 요약합니다."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.\n.env 파일에 API 키를 설정해주세요.")

    client = anthropic.Anthropic(api_key=api_key)

    today_str = date.today().strftime("%Y년 %m월 %d일")
    topics = config.get("topics", [])
    topics_str = ", ".join(topics)

    system = build_system_prompt_web_search(config, today_str)
    user_message = f"오늘({today_str}) 다음 주제들의 최신 뉴스 클리핑을 만들어주세요: {topics_str}"

    tools = [{"type": "web_search_20260209", "name": "web_search"}]
    messages = [{"role": "user", "content": user_message}]

    all_text = []
    max_continuations = 5

    for iteration in range(max_continuations):
        if iteration == 0:
            print("🔍 뉴스 검색 중... (잠시 기다려 주세요)\n")
            print("-" * 60)
        else:
            print(f"\n🔄 추가 검색 진행 중... (반복 {iteration + 1})\n")

        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=system,
            tools=tools,
            messages=messages,
        ) as stream:
            iteration_text = []

            for event in stream:
                # 텍스트 청크만 출력 (thinking 블록 제외)
                if (
                    hasattr(event, "type")
                    and event.type == "content_block_delta"
                    and hasattr(event, "delta")
                    and hasattr(event.delta, "type")
                    and event.delta.type == "text_delta"
                ):
                    chunk = event.delta.text
                    print(chunk, end="", flush=True)
                    iteration_text.append(chunk)

            final_msg = stream.get_final_message()
            all_text.extend(iteration_text)

        if final_msg.stop_reason == "end_turn":
            break
        elif final_msg.stop_reason == "pause_turn":
            # 서버 사이드 도구 반복 횟수 초과 → 대화를 이어서 계속
            messages = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": final_msg.content},
            ]
        else:
            break

    print("\n")
    return "".join(all_text)


# ─────────────────────────────────────────────
# RSS 피드 모드
# ─────────────────────────────────────────────

def fetch_rss_articles(feeds: list[dict], max_per_feed: int = 10) -> list[dict]:
    """RSS 피드에서 기사를 수집합니다."""
    if not RSS_AVAILABLE:
        raise ImportError(
            "RSS 모드를 사용하려면 feedparser가 필요합니다.\n"
            "pip install feedparser 로 설치해주세요."
        )

    articles = []
    for feed_cfg in feeds:
        url = feed_cfg.get("url", "")
        name = feed_cfg.get("name", url)
        if not url:
            continue

        print(f"  📡 피드 수집 중: {name}")
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_feed]:
                summary = entry.get("summary", entry.get("description", ""))
                # HTML 태그 제거 (간단한 방식)
                if summary:
                    import re
                    summary = re.sub(r"<[^>]+>", "", summary).strip()

                articles.append({
                    "title": entry.get("title", "제목 없음"),
                    "summary": summary[:500],  # 길이 제한
                    "link": entry.get("link", ""),
                    "published": entry.get("published", "날짜 불명"),
                    "source": name,
                })
        except Exception as e:
            print(f"  ⚠️  {name} 피드 수집 실패: {e}")

    return articles


def run_rss_mode(config: dict) -> str:
    """RSS 피드에서 기사를 수집하고 Claude로 요약합니다."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.")

    client = anthropic.Anthropic(api_key=api_key)

    feeds = config.get("rss_feeds", [])
    if not feeds:
        raise ValueError("RSS 모드에서는 config.yaml의 rss_feeds 목록이 필요합니다.")

    topics = config.get("topics", [])
    language = config.get("language", "Korean")
    articles_per_topic = config.get("articles_per_topic", 3)
    today_str = date.today().strftime("%Y년 %m월 %d일")
    lang_note = "한국어로 작성해주세요." if language == "Korean" else "Please write in English."

    print("📡 RSS 피드 수집 중...\n")
    articles = fetch_rss_articles(feeds, max_per_feed=15)

    if not articles:
        raise RuntimeError("수집된 기사가 없습니다. RSS 피드 URL을 확인해주세요.")

    print(f"\n✅ {len(articles)}개 기사 수집 완료\n")
    print("-" * 60)

    articles_json = json.dumps(articles, ensure_ascii=False, indent=2)

    topics_str = ", ".join(topics) if topics else "전반적인 뉴스"
    system = f"""당신은 전문 뉴스 큐레이터입니다.
관심 주제: {topics_str}
오늘 날짜: {today_str}
{lang_note}"""

    user_message = f"""다음은 오늘 수집된 뉴스 기사들입니다.

{articles_json}

위 기사들을 분석하여 일일 뉴스 클리핑을 작성해주세요:

1. 관심 주제({topics_str})와 관련된 중요 뉴스 {articles_per_topic}개를 선별
2. 각 뉴스를 3-5줄로 요약, 출처 포함
3. 전체 트렌드 요약 (1-2 단락)

## 📰 일일 뉴스 클리핑 - {today_str} 형식으로 작성해주세요."""

    print("🤖 Claude가 기사를 분석 중...\n")

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        result_parts = []
        for event in stream:
            if (
                hasattr(event, "type")
                and event.type == "content_block_delta"
                and hasattr(event, "delta")
                and hasattr(event.delta, "type")
                and event.delta.type == "text_delta"
            ):
                chunk = event.delta.text
                print(chunk, end="", flush=True)
                result_parts.append(chunk)

    print("\n")
    return "".join(result_parts)


# ─────────────────────────────────────────────
# 결과 저장
# ─────────────────────────────────────────────

def save_digest(content: str, output_dir: str) -> Path:
    """뉴스 클리핑 결과를 마크다운 파일로 저장합니다."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    filename = f"news_digest_{date.today().strftime('%Y%m%d')}.md"
    filepath = output_path / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="일일 뉴스 클리핑 에이전트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python news_agent.py                    기본 실행
  python news_agent.py --save             결과 파일 저장
  python news_agent.py --mode rss         RSS 피드 모드
  python news_agent.py --config my.yaml   다른 설정 파일 사용
        """,
    )
    parser.add_argument("--config", default="config.yaml", help="설정 파일 경로 (기본값: config.yaml)")
    parser.add_argument("--mode", choices=["web_search", "rss"], help="수집 모드 (설정 파일의 mode 값 덮어쓰기)")
    parser.add_argument("--save", action="store_true", help="결과를 파일로 저장")
    parser.add_argument("--output-dir", default=None, help="저장 디렉토리 (기본값: ./digests)")
    args = parser.parse_args()

    # 설정 로드
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # 모드 결정 (CLI 인수 > 설정 파일 > 기본값)
    mode = args.mode or config.get("mode", "web_search")

    # 헤더 출력
    today_str = date.today().strftime("%Y년 %m월 %d일")
    topics = config.get("topics", [])
    print()
    print("=" * 60)
    print("  📰 일일 뉴스 클리핑 에이전트")
    print(f"  📅 {today_str}")
    if topics:
        print(f"  🔖 관심 주제: {', '.join(topics)}")
    print(f"  ⚙️  모드: {'웹 검색' if mode == 'web_search' else 'RSS 피드'}")
    print("=" * 60)
    print()

    # 에이전트 실행
    try:
        if mode == "web_search":
            digest = run_web_search_mode(config)
        elif mode == "rss":
            digest = run_rss_mode(config)
        else:
            print(f"❌ 알 수 없는 모드: {mode}")
            sys.exit(1)
    except (ValueError, RuntimeError, ImportError) as e:
        print(f"\n❌ 오류: {e}")
        sys.exit(1)
    except anthropic.APIError as e:
        print(f"\n❌ API 오류: {e}")
        sys.exit(1)

    # 결과 저장
    output_dir = args.output_dir or config.get("output_dir", "./digests")
    if args.save or config.get("auto_save", False):
        try:
            filepath = save_digest(digest, output_dir)
            print(f"✅ 저장 완료: {filepath}")
        except OSError as e:
            print(f"⚠️  파일 저장 실패: {e}")


if __name__ == "__main__":
    main()
