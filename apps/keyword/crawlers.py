"""
네이버 블로그/카페 OpenAPI 크롤링 모듈
- 네이버 OpenAPI: 블로그/카페 최신 글 수집
- 블로그 문서수(D) 조회
"""

import re
import time
import html
from typing import List, Dict
import requests

# ============================================================================
# 📋 크롤링 설정값들
# ============================================================================

# 🕷️ 크롤링 설정
DEFAULT_LIMIT_PER_SOURCE = 100  # 각 소스별 기본 수집 문서 수
API_CALL_DELAY = 0.2  # 네이버 API 호출 간격 (초)
MAX_API_DISPLAY = 100  # 네이버 API 한 번에 가져올 최대 결과 수

# 🌐 HTTP 설정
HTTP_TIMEOUT = 10  # HTTP 요청 타임아웃 (초)

# ============================================================================


def _strip_html(s: str) -> str:
    """HTML 태그 제거 및 텍스트 정리"""
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def crawl_all_sources(
    keyword: str,
    limit_per_source: int = DEFAULT_LIMIT_PER_SOURCE,
    cred: Dict = None,
    sources: Dict = None,
) -> List[str]:
    """
    모든 소스에서 키워드로 크롤링

    Args:
        keyword: 검색할 키워드
        limit_per_source: 각 소스별 수집할 문서 수
        cred: 네이버 API 자격증명
        sources: 크롤링 소스 설정

    Returns:
        List[str]: 수집된 모든 텍스트 목록
    """
    if sources is None:
        sources = {"naver_blog": True, "naver_cafe": True}
    if cred is None:
        cred = {}

    print(f"🔍 '{keyword}' 키워드로 크롤링 시작...")
    all_texts = []

    # 네이버 블로그 크롤링
    if sources.get("naver_blog", False) and cred:
        print("📝 네이버 블로그 크롤링 중...")
        blog_texts = crawl_naver_blog(keyword, limit_per_source, cred)
        all_texts.extend(blog_texts)
        print(f"✓ 블로그: {len(blog_texts)}개 수집")

    # 네이버 카페 크롤링
    if sources.get("naver_cafe", False) and cred:
        print("☕ 네이버 카페 크롤링 중...")
        cafe_texts = crawl_naver_cafe(keyword, limit_per_source, cred)
        all_texts.extend(cafe_texts)
        print(f"✓ 카페: {len(cafe_texts)}개 수집")
        # DCInside 크롤링은 별도 모듈로 분리됨
    print(f"📊 총 {len(all_texts)}개 텍스트 수집 완료")
    return all_texts


def crawl_naver_blog(seed: str, limit: int, cred: Dict) -> List[str]:
    """네이버 블로그 OpenAPI로 최신 글 수집"""
    url = "https://openapi.naver.com/v1/search/blog.json"
    headers = {
        "X-Naver-Client-Id": cred["client_id"],
        "X-Naver-Client-Secret": cred["client_secret"],
    }
    params = {"query": seed, "display": min(limit, MAX_API_DISPLAY), "sort": "date"}

    out = []
    fetched = 0

    while fetched < limit:
        params["start"] = fetched + 1
        try:
            r = requests.get(url, headers=headers, params=params, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            items = r.json().get("items", [])

            for item in items:
                title = item.get("title", "")
                desc = item.get("description", "")
                text = _strip_html(f"{title} {desc}")
                if text:
                    out.append(text)

            got = len(items)
            if got == 0:
                break
            fetched += got
            time.sleep(API_CALL_DELAY)

        except Exception as e:
            print(f"블로그 크롤링 오류 ({seed}): {e}")
            break

    return out[:limit]


def crawl_naver_cafe(seed: str, limit: int, cred: Dict) -> List[str]:
    """네이버 카페 OpenAPI로 최신 글 수집"""
    url = "https://openapi.naver.com/v1/search/cafearticle.json"
    headers = {
        "X-Naver-Client-Id": cred["client_id"],
        "X-Naver-Client-Secret": cred["client_secret"],
    }
    params = {"query": seed, "display": min(limit, MAX_API_DISPLAY), "sort": "date"}

    out = []
    fetched = 0

    while fetched < limit:
        params["start"] = fetched + 1
        try:
            r = requests.get(url, headers=headers, params=params, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            items = r.json().get("items", [])

            for item in items:
                title = item.get("title", "")
                desc = item.get("description", "")
                text = _strip_html(f"{title} {desc}")
                if text:
                    out.append(text)

            got = len(items)
            if got == 0:
                break
            fetched += got
            time.sleep(API_CALL_DELAY)

        except Exception as e:
            print(f"카페 크롤링 오류 ({seed}): {e}")
            break

    return out[:limit]


def get_naver_blog_total(keyword: str, cred: Dict) -> int:
    """네이버 블로그 검색 API로 특정 키워드의 총 문서수(D) 조회"""
    url = "https://openapi.naver.com/v1/search/blog.json"
    headers = {
        "X-Naver-Client-Id": cred["client_id"],
        "X-Naver-Client-Secret": cred["client_secret"],
    }
    params = {"query": keyword, "display": 1}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        return int(r.json().get("total", 0))
    except Exception as e:
        print(f"문서수 조회 오류 ({keyword}): {e}")
        return 0


if __name__ == "__main__":
    # 🎯 키워드 설정 (여기만 바꾸면 됨!)
    SEARCH_KEYWORD = "모바일 게임"  # 🔍 검색할 키워드

    import sys
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    from common.config import load_merged

    # 설정 로드 (API 자격증명만)
    try:
        cfg = load_merged("config/base.yaml")
        cred = cfg["credentials"]["naver_openapi"]
    except:
        cred = {}

    # 크롤링 실행 (위에 설정된 상수값들 사용)
    texts = crawl_all_sources(SEARCH_KEYWORD, DEFAULT_LIMIT_PER_SOURCE, cred)

    # 각 소스별 제목 미리보기 (10개씩)
    print(f"\n📋 '{SEARCH_KEYWORD}' 수집 결과 미리보기:")

    # 네이버 블로그 제목
    if cred:
        print("\n📝 네이버 블로그 제목 (최신 10개):")
        blog_texts = crawl_naver_blog(SEARCH_KEYWORD, 10, cred)
        for i, text in enumerate(blog_texts[:10], 1):
            # 제목만 추출 (첫 번째 문장 또는 첫 50자)
            title = text.split(".")[0].split("!")[0].split("?")[0][:50]
            print(f"  {i:2d}. {title}...")

    # 네이버 카페 제목
    if cred:
        print("\n☕ 네이버 카페 제목 (최신 10개):")
        cafe_texts = crawl_naver_cafe(SEARCH_KEYWORD, 10, cred)
        for i, text in enumerate(cafe_texts[:10], 1):
            title = text.split(".")[0].split("!")[0].split("?")[0][:50]
            print(f"  {i:2d}. {title}...")

    print(f"\n✅ '{SEARCH_KEYWORD}' 크롤링 완료!")
    print("💡 키워드 분석은 apps/keyword/filter.py를 실행하세요")
