"""
네이버 자동완성 API를 활용한 연관키워드 추출 도구
- 지정된 시드키워드에서 직접 연관키워드 추출
"""

import json
import time
from pathlib import Path
from typing import Dict, List
import requests
import sys
import logging

# 키워드 주제 설정
KEYWORD_SUBJECT = "게임"  # "SNS", "게임" 등으로 변경 가능
SEED_KEYWORD = "게임"  # 사용할 단일 시드키워드

# 확장 설정
DELAY_BETWEEN_REQUESTS = 0.5  # API 요청 간 간격 (초)

# 네이버 자동완성 API 설정
NAVER_AC_URL = "https://mac.search.naver.com/mobile/ac"
NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0 Mobile Safari/537.36",
    "Referer": "https://m.search.naver.com/"
}

# 로그 설정
def setup_logger():
    """로그 설정 및 파일 생성"""
    # 로그 폴더 생성
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # 로그 파일명 생성 (related_YYYYMMDD_HHMM)
    timestamp = time.strftime("%Y%m%d_%H%M")
    log_file = log_dir / f"related_{timestamp}.log"
    
    # 로거 설정
    logger = logging.getLogger('related_keywords')
    logger.setLevel(logging.INFO)
    
    # 기존 핸들러 제거
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 파일 핸들러 생성
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # 포맷터 설정
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    
    print(f"📝 로그 파일 생성: {log_file}")
    return logger

# 전역 로거 초기화
response_logger = setup_logger()


def get_naver_autocomplete(keyword: str) -> List[str]:
    """네이버 자동완성 API 호출하여 연관키워드 추출"""
    try:
        params = {
            "q": keyword,
            "st": 1,
            "frm": "mobile_nv", 
            "r_format": "json",
            "r_enc": "UTF-8",
            "r_unicode": 0,
            "r_lt": "koreng",
            "enc": "UTF-8",
            "ans": 1,
            "run": 2,
            "rev": 4,
            "callback": "jsonp12345"
        }
        
        response = requests.get(NAVER_AC_URL, params=params, headers=NAVER_HEADERS, timeout=10)
        response.raise_for_status()
        
        # 응답 처리
        text = response.text
        
        # 전체 응답 로그에 기록
        response_logger.info(f"키워드: {keyword}")
        response_logger.info(f"요청 URL: {response.url}")
        response_logger.info(f"응답 상태: {response.status_code}")
        response_logger.info(f"응답 내용: {text}")
        response_logger.info("=" * 80)
        
        # JSONP 또는 JSON 형태 처리
        data = None
        if text.startswith("jsonp12345(") and text.endswith(");"):
            # JSONP 형태
            json_str = text[11:-2]
            data = json.loads(json_str)
        else:
            # 순수 JSON 형태
            data = json.loads(text)
        
        # 자동완성 결과 추출
        suggestions = []
        
        # items 배열에서 추출
        if "items" in data and len(data["items"]) > 0:
            for item in data["items"]:
                if isinstance(item, list) and len(item) > 0:
                    for sub_item in item:
                        if isinstance(sub_item, list) and len(sub_item) > 0:
                            suggestion = sub_item[0]
                            if suggestion and suggestion != keyword and suggestion not in suggestions:
                                suggestions.append(suggestion)
        

        
        return suggestions  # 모든 연관키워드 반환
            
    except Exception as e:
        print(f"❌ {keyword} API 호출 실패: {e}")
        return []
    
    return []


def expand_single_seed_simple(seed_keyword: str) -> List[str]:
    """단일 시드키워드에서 연관키워드 추출 (재귀 없음)"""
    print(f"🔍 '{seed_keyword}' 연관키워드 추출 중...")
    
    # 시드키워드에서 직접 연관키워드 추출
    related_keywords = get_naver_autocomplete(seed_keyword)
    
    if not related_keywords:
        print(f"❌ '{seed_keyword}': 연관키워드를 찾을 수 없습니다")
        return []
    
    print(f"✅ {len(related_keywords)}개 발견: {', '.join(related_keywords)}")
    
    return related_keywords







def save_related_keywords(keyword_subject: str, keyword_tree: Dict[str, List[str]], save_to_original: bool = True) -> str:
    """연관 키워드를 파일에 저장"""
    if not keyword_tree:
        return ""
    
    # rel_keywords 폴더 생성
    rel_keywords_dir = Path(__file__).parent.parent.parent / "data" / "rel_keywords"
    rel_keywords_dir.mkdir(exist_ok=True)
    
    # 주제별 파일로 저장/업데이트 (폴더 없이 바로 파일)
    result_file = rel_keywords_dir / f"{keyword_subject}.json"
    
    # 기존 파일이 있으면 로드, 없으면 새로 생성
    if result_file.exists():
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        except:
            existing_data = {
                "keyword_subject": keyword_subject,
                "created_at": time.strftime("%Y%m%d_%H%M%S"),
                "last_updated": time.strftime("%Y%m%d_%H%M%S"),
                "seed_keywords": {}  # {시드키워드: [연관키워드들]}
            }
    else:
        existing_data = {
            "keyword_subject": keyword_subject,
            "created_at": time.strftime("%Y%m%d_%H%M%S"),
            "last_updated": time.strftime("%Y%m%d_%H%M%S"),
            "seed_keywords": {}  # {시드키워드: [연관키워드들]}
        }
    
    # 시드키워드별로 연관키워드 업데이트 (중복 시 덮어쓰기)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    new_related_count = 0
    
    for seed_keyword, related_list in keyword_tree.items():
        # 기존 시드키워드가 있으면 덮어쓰기, 없으면 새로 추가
        existing_data["seed_keywords"][seed_keyword] = related_list
        new_related_count += len(related_list)
        print(f"📝 '{seed_keyword}': {len(related_list)}개 연관키워드 업데이트")
    
    existing_data["last_updated"] = timestamp
    
    # 전체 통계 계산
    total_seeds = len(existing_data["seed_keywords"])
    total_unique_keywords = set()
    for keywords in existing_data["seed_keywords"].values():
        total_unique_keywords.update(keywords)
    
    existing_data["total_seed_keywords"] = total_seeds
    existing_data["total_unique_keywords"] = len(total_unique_keywords)
    
    try:
        # 파일 저장
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 '{keyword_subject}.json' 파일 저장 완료")
        
        # 원본 파일에도 추가 (옵션)
        if save_to_original:
            original_keywords_dir = Path(__file__).parent.parent.parent / "data" / "keywords"
            original_file = original_keywords_dir / f"{keyword_subject}.json"
            if original_file.exists():
                try:
                    with open(original_file, 'r', encoding='utf-8') as f:
                        original_data = json.load(f)
                    
                    # 기존 키워드 중복 제거를 위한 집합
                    existing_keywords = {item["keyword"] for item in original_data.get("seed_keywords", [])}
                    
                    # 새로운 연관키워드들 추가
                    new_related_added = 0
                    for seed, related_list in keyword_tree.items():
                        for keyword in related_list:
                            if keyword not in existing_keywords:
                                original_data["seed_keywords"].append({
                                    "keyword": keyword,
                                    "confidence": 1.0,
                                    "labels": ["RELATED_EXTRACTED"],
                                    "source": f"naver_autocomplete_from_{seed}",
                                    "added_order": len(original_data["seed_keywords"]) + 1
                                })
                                existing_keywords.add(keyword)
                                new_related_added += 1
                    
                    # 메타데이터 업데이트
                    original_data["total_keywords"] = len(original_data["seed_keywords"])
                    original_data["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    
                    # 원본 파일 저장
                    with open(original_file, 'w', encoding='utf-8') as f:
                        json.dump(original_data, f, ensure_ascii=False, indent=2)
                    
                    print(f"📝 원본 파일에 {new_related_added}개 연관키워드 추가: {original_file}")
                    
                except Exception as e:
                    print(f"⚠️ 원본 파일 업데이트 실패: {e}")
        
        return str(result_file)
        
    except Exception as e:
        print(f"❌ 파일 저장 실패: {e}")
        return ""






def main():
    """메인 실행 함수"""
    print(f"🎯 시드키워드: {SEED_KEYWORD}")
    
    # 단일 시드키워드에서 연관키워드 추출
    try:
        related_keywords = expand_single_seed_simple(SEED_KEYWORD)
        
        if related_keywords:
            # 결과를 딕셔너리 형태로 변환 (기존 저장 함수 호환)
            keyword_tree = {SEED_KEYWORD: related_keywords}
            save_related_keywords(KEYWORD_SUBJECT, keyword_tree, save_to_original=False)
            
            print(f"📝 결과: {', '.join(related_keywords)}")
            
            return keyword_tree
        else:
            print(f"❌ '{SEED_KEYWORD}'에서 연관키워드를 찾을 수 없습니다")
            return {}
            
    except KeyboardInterrupt:
        print("\n🛑 연관키워드 추출 중단됨")
        return {}
    except Exception as e:
        print(f"❌ 연관키워드 추출 실패: {e}")
        return {}


if __name__ == "__main__":
    """실행 예시: python related.py"""
    
    # 스크립트 경로를 sys.path에 추가
    script_dir = Path(__file__).parent.parent.parent
    sys.path.append(str(script_dir))
    
    main()
