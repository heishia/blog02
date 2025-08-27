"""
네이버 검색광고 API(키워드도구) 키워드 확장 모듈
- I-AFW_OTHER_PRODUCTS 라벨이 달린 시드키워드에서만 키워드 확장 수집
- 각 시드키워드에서 상위 10개만 추출하여 정확도 유지
- 캐시를 사용하여 한번 사용된 시드키워드는 재사용 방지
- 확장된 키워드를 data/expand_keywords/{주제명}.json 파일에 자동 저장
"""

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple
import requests

# 네이버 검색광고 API 설정
API_HOST = "https://api.naver.com"
API_PATH = "/keywordstool"

# 키워드 주제 설정 (여기서 변경)
KEYWORD_SUBJECT = "게임"  # "SNS", "게임" 등으로 변경

# 타겟 라벨 설정 (filter.py에서 추출된 시드키워드만 사용)
TARGET_LABEL = "I-AFW_OTHER_PRODUCTS"

# 캐시 설정
CACHE_DIR = "cache"
CACHE_FILE = "expand_keyword_cache.json"

# 키워드 확장 설정
EXPANSION_LIMIT = 10  # 하나의 시드키워드에서 확장할 키워드 수 (상위 10개만)


def _make_signature(timestamp: str, method: str, path: str, secret_key: str) -> str:
    """네이버 API 요청 서명 생성"""
    message = f"{timestamp}.{method}.{path}"
    signature = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(signature).decode("utf-8")


def load_cache() -> Dict[str, int]:
    """캐시 파일 로드"""
    cache_path = Path(CACHE_DIR) / CACHE_FILE
    
    # 캐시 폴더가 없으면 생성
    cache_path.parent.mkdir(exist_ok=True)
    
    if cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_cache(cache: Dict[str, int]) -> None:
    """캐시 파일 저장"""
    try:
        cache_path = Path(CACHE_DIR) / CACHE_FILE
        cache_path.parent.mkdir(exist_ok=True)
        
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        pass


def update_keyword_usage(cache: Dict[str, int], keyword: str, success: bool = True, no_data: bool = False) -> None:
    """키워드 사용 횟수 업데이트 (성공한 경우만 기록, no data는 -1로 기록)"""
    if success:
        cache[keyword] = cache.get(keyword, 0) + 1
    elif no_data:
        cache[keyword] = -1  # no data 의미


def get_expand_keywords(keyword: str, cred: Dict, limit: int = 10) -> Tuple[List[str], bool, bool]:
    """특정 키워드의 확장키워드 수집 - (키워드리스트, 성공여부, no_data여부) 반환"""
    timestamp = str(int(time.time() * 1000))
    headers = {
        "X-Timestamp": timestamp,
        "X-API-KEY": cred["api_key"],
        "X-Customer": str(cred["customer_id"]),
        "X-Signature": _make_signature(timestamp, "GET", API_PATH, cred["secret_key"]),
    }
    
    # 키워드 정제 (특수문자, 공백 등 제거)
    cleaned_keyword = _clean_keyword(keyword)
    
    # 더 많은 결과를 가져오기 위한 파라미터 설정
    params = {
        "hintKeywords": cleaned_keyword, 
        "showDetail": 1,
        "items": 10  # 최대 결과 수
    }

    max_retries = 3
    retry_delay = 2  # 초
    
    for attempt in range(max_retries):
        try:
            response = requests.get(f"{API_HOST}{API_PATH}", headers=headers, params=params, timeout=15)
            
            if response.status_code == 429:  # Too Many Requests
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)  # 지수 백오프
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ {keyword}: API 제한으로 인한 최종 실패")
                    return [], False, False  # API 거절로 반환
            
            response.raise_for_status()
            data = response.json()
            
            # 상위 limit개만 추출
            keywords = []
            for item in data.get("keywordList", [])[:limit]:
                expand_keyword = item.get("relKeyword")
                if expand_keyword and expand_keyword != cleaned_keyword:
                    keywords.append(expand_keyword)
            
            # 키워드가 없는 경우 no_data로 처리
            if not keywords:
                return [], False, True  # no_data로 반환
            
            return keywords, True, False  # 성공으로 반환
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:  # Bad Request
                # 400 에러는 no_data로 처리 (키워드 자체에 문제)
                return [], False, True  # no_data로 반환
            elif e.response.status_code == 429:  # Too Many Requests
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ {keyword}: API 제한으로 인한 최종 실패")
                    return [], False, False  # API 거절로 반환
            else:
                return [], False, False  # 실패로 반환
                
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                time.sleep(wait_time)
                continue
            else:
                return [], False, False  # 실패로 반환
    
    return [], False, False  # 실패로 반환


def _clean_keyword(keyword: str) -> str:
    """키워드 정제 (API 호출을 위한 전처리)"""
    # 공백이 있는 경우 첫 번째 단어만 사용
    if ' ' in keyword:
        first_word = keyword.split()[0]
        return first_word
    
    # 특수문자나 숫자가 포함된 경우 원본 유지
    if any(char in keyword for char in ['+', '-', '&', '(', ')', '.', ',', '!', '?', ':', ';']):
        return keyword
    
    # 한글 + 영문 조합인 경우 원본 유지
    if any(c.isalpha() for c in keyword) and any(ord(c) > 127 for c in keyword):
        return keyword
    
    return keyword


def get_afw_seed_keywords(keyword_subject: str) -> List[str]:
    """I-AFW_OTHER_PRODUCTS 라벨이 달린 시드키워드만 추출 (순수 영어 제외, 기호 포함 제외)"""
    data_dir = Path(__file__).parent.parent.parent / "data" / "expand_keywords"
    json_file = data_dir / f"{keyword_subject}.json"
    
    if not json_file.exists():
        return []
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # I-AFW_OTHER_PRODUCTS 라벨이 달린 키워드만 추출 (순수 영어 제외, 기호 포함 제외)
        afw_keywords = []
        for item in data.get("seed_keywords", []):
            if TARGET_LABEL in item.get("labels", []):
                keyword = item["keyword"]
                # 순수 영어 키워드 제외 (한글이 포함되지 않은 경우)
                if not _has_korean_character(keyword):
                    continue
                # 기호가 포함된 키워드 제외 (시스템 인식 어려움)
                if _has_special_symbols(keyword):
                    continue
                # 의미를 알기 어려운 키워드 제외
                if _is_unclear_keyword(keyword):
                    continue
                afw_keywords.append(keyword)
        
        return afw_keywords
        
    except Exception as e:
        return []


def _has_korean_character(keyword: str) -> bool:
    """한글 문자가 포함되어 있는지 확인"""
    # 한글 유니코드 범위: 가(0xAC00) ~ 힣(0xD7A3)
    return any(0xAC00 <= ord(c) <= 0xD7A3 for c in keyword)


def _has_special_symbols(keyword: str) -> bool:
    """기호가 포함되어 있는지 확인 (시스템 인식 어려움)"""
    # 문제가 될 수 있는 기호들
    problematic_symbols = {':', ';', '|', '/', '\\', '(', ')', '[', ']', '{', '}', '<', '>', '=', '+', '*', '&', '^', '%', '$', '#', '@', '!', '?'}
    return any(symbol in keyword for symbol in problematic_symbols)


def _is_unclear_keyword(keyword: str) -> bool:
    """의미를 알기 어려운 키워드인지 확인"""
    # 너무 짧거나 긴 키워드
    if len(keyword) < 2 or len(keyword) > 20:
        return True
    
    # 숫자만 있는 키워드
    if keyword.isdigit():
        return True
    
    # 특수문자만 있는 키워드
    if not any(c.isalnum() or c in "가-힣" for c in keyword):
        return True
    
    # 의미를 알기 어려운 패턴들
    unclear_patterns = [
        # 콜론으로 구분된 패턴 (예: "킹덤 컴 : 딜리버런스")
        ' : ',
        # 슬래시로 구분된 패턴
        ' / ',
        # 파이프로 구분된 패턴
        ' | ',
        # 괄호로 감싸진 패턴
        '(', ')',
        # 대괄호로 감싸진 패턴
        '[', ']',
    ]
    
    for pattern in unclear_patterns:
        if pattern in keyword:
            return True
    
    return False


def get_available_afw_keywords(keyword_subject: str) -> List[Dict]:
    """사용 가능한 AFW 시드키워드 목록 반환 (캐시 확인 포함)"""
    afw_keywords = get_afw_seed_keywords(keyword_subject)
    cache = load_cache()
    
    available_keywords = []
    for keyword in afw_keywords:
        usage_count = cache.get(keyword, 0)
        # -1인 경우 no data로 처리하여 사용 가능하게 표시
        available_keywords.append({
            "keyword": keyword,
            "usage_count": usage_count,
            "available": usage_count == 0 or usage_count == -1  # 0이거나 -1인 경우 사용 가능
        })
    
    return available_keywords


def collect_keywords_for_subject(keyword_subject: str, cred: Dict, max_seeds: int = 5) -> Dict[str, List[str]]:
    """AFW 시드키워드에서 키워드 확장 수집 (성공한 키워드가 5개가 될 때까지 계속 진행)"""
    
    # 사용 가능한 AFW 시드키워드 확인
    available_seeds = get_available_afw_keywords(keyword_subject)
    unused_seeds = [seed for seed in available_seeds if seed["available"]]
    
    if not unused_seeds:
        print(f"❌ 사용 가능한 {TARGET_LABEL} 시드키워드가 없습니다")
        return {}
    
    # 캐시를 한 번만 로드
    cache = load_cache()
    
    results = {}
    total_expanded = 0
    processed_count = 0
    success_count = 0
    
    # 성공한 키워드가 max_seeds개가 될 때까지 계속 진행
    for seed_info in unused_seeds:
        if success_count >= max_seeds:
            break
            
        seed_keyword = seed_info["keyword"]
        processed_count += 1
        
        # 키워드 품질 검사
        if _has_special_symbols(seed_keyword) or _is_unclear_keyword(seed_keyword):
            # 기호가 포함되거나 의미를 알기 어려운 키워드는 -1로 등록하고 건너뛰기
            update_keyword_usage(cache, seed_keyword, success=False, no_data=True)
            continue
        
        # 네이버 검색광고 API로 키워드 확장 수집
        expanded_keywords, success, no_data = get_expand_keywords(seed_keyword, cred, EXPANSION_LIMIT)
        
        if success and expanded_keywords:
            results[seed_keyword] = expanded_keywords
            total_expanded += len(expanded_keywords)
            success_count += 1
            
            # 성공한 경우만 캐시에 기록
            update_keyword_usage(cache, seed_keyword, success=True)
        elif no_data:
            # no data인 경우 -1로 캐시에 기록 (400 응답 또는 키워드가 0개)
            update_keyword_usage(cache, seed_keyword, success=False, no_data=True)
        else:
            # API 거절(429) 등 실패한 경우는 캐시에 기록하지 않음
            pass
        
        # 키워드 간 간격 추가 (API 제한 방지)
        if processed_count < len(unused_seeds) and success_count < max_seeds:
            time.sleep(1)
        
        # 사용 가능한 키워드가 부족한 경우 경고
        if processed_count >= len(unused_seeds) and success_count < max_seeds:
            print(f"⚠️ 목표 {max_seeds}개에 도달하지 못함: 성공 {success_count}개, 총 {total_expanded}개 확장키워드")
            break
    
    # 캐시를 한 번만 저장
    save_cache(cache)
    
    return results


def save_expanded_keywords_to_json(keyword_subject: str, expanded_keywords: Dict[str, List[str]]) -> str:
    """확장된 키워드를 JSON 파일에 저장"""
    data_dir = Path(__file__).parent.parent.parent / "data" / "expand_keywords"
    json_file = data_dir / f"{keyword_subject}.json"
    
    if not json_file.exists():
        return ""
    
    try:
        # 기존 데이터 로드
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 새로운 확장 키워드들을 시드키워드에 순서대로 추가
        existing_keywords = {item["keyword"] for item in data.get("seed_keywords", [])}
        new_keywords = []
        
        for seed, expanded_list in expanded_keywords.items():
            for expanded_kw in expanded_list:
                if expanded_kw not in existing_keywords:
                    new_keywords.append({
                        "keyword": expanded_kw,
                        "confidence": 1.0,  
                        "labels": ["EXPANDED_KEYWORD"],
                        "source": f"expanded_from_{seed}",
                        "added_order": len(data["seed_keywords"]) + len(new_keywords) + 1  # 추가 순서 기록
                    })
                    existing_keywords.add(expanded_kw)
        
        # 기존 시드키워드에 새로운 키워드 추가 (순서대로)
        data["seed_keywords"].extend(new_keywords)
        
        # 파일 저장
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return str(json_file)
        
    except Exception as e:
        return ""


def main(keyword_subject: str = None, max_seeds: int = 5):
    """메인 실행 함수"""
    from common.config import load_merged
    
    # 설정 로드 (API 자격증명만)
    cfg = load_merged("config/base.yaml")
    ads_cred = cfg["credentials"]["naver_ads"]
    
    # 키워드 주제 설정 (파일 상단 설정값 우선, 없으면 파라미터)
    if keyword_subject is None:
        keyword_subject = KEYWORD_SUBJECT
    
    # 사용 가능한 AFW 시드키워드 목록 표시
    available_seeds = get_available_afw_keywords(keyword_subject)
    
    # 키워드 확장 수집
    result = collect_keywords_for_subject(keyword_subject, ads_cred, max_seeds)
    
    if result:
        # JSON 파일에 저장
        save_expanded_keywords_to_json(keyword_subject, result)
        
        # 확장 성공 키워드 정리
        success_keywords = list(result.keys())
        print(f"확장 성공 키워드: {', '.join(success_keywords)}")
        print(f"총 {len(success_keywords)}개 키워드")
    
    return result


if __name__ == "__main__":
    """테스트 실행"""
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent.parent))
    
    main()  # 파일 상단 KEYWORD_SUBJECT 설정값 사용
