"""
황금키워드 통합 도구 (total_gold.py)
- 연관키워드 확장 + 검색량/문서량 분석 + 필터링을 하나의 파일로 통합
- related.py + gold.py 기능을 독립적으로 실행
"""

import hashlib
import hmac
import time
import requests
import urllib.request
import urllib.parse
import json
from typing import List, Dict, Set, Tuple
import yaml
import pandas as pd
from datetime import datetime
import os
from collections import deque
from pathlib import Path
import random
from threading import Thread
import sys
import logging

# ================================================================================
# 🔧 설정 상수값들 (여기서 모든 설정 관리)
# ================================================================================

# 📌 로깅 설정
def setup_logging():
    """로깅 설정 - 터미널과 파일에 동시 출력"""
    # 로그 디렉토리 생성
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # 로그 파일명 (타임스탬프 포함)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"{log_dir}/total_gold_{timestamp}.log"
    
    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),  # 파일에 저장
            logging.StreamHandler(sys.stdout)  # 터미널에 출력
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"로그 파일 생성: {log_file}")
    return logger

# 전역 로거 설정
logger = setup_logging()

# print 함수를 logger로 대체하는 함수
def log_print(message):
    """print 대신 사용할 로깅 함수"""
    logger.info(message)
    
# 📌 키워드 주제 설정
KEYWORD_SUBJECT = "게임"
CUSTOM_SEED_KEYWORDS = ["게임"]  # 직접 지정할 시드키워드 (빈 리스트면 JSON 파일에서 로드)
# 예시: ["게임"], ["SNS"], ["쇼핑"], ["여행"] 등 자유롭게 변경 가능

# 📌 연관키워드 확장 설정
MAX_KEYWORDS = 1000  # 최대 연관키워드 수 (API 제한 고려하여 200개로 조정)
MAX_SEED_KEYWORDS = 1  # 사용할 시드키워드 1개로 제한
DELAY_BETWEEN_REQUESTS = 0.05  # API 요청 간 간격 (초) - 초고속 처리

# 📌 황금키워드 분석 설정
MODE = "BASIC"  # "BASIC" (기본모드), "AUTO" (자동모드), "BACKGROUND" (백그라운드 자동모드)
TARGET_STAGES = [1, 2, 3, 4, 5]  # 목표로 하는 스테이지 이내 (1-3단계 이내)

# 📌 백그라운드 자동모드 설정
AUTO_CYCLE_MINUTES = 30  # 자동모드 실행 주기 (분)
AUTO_RANDOM_SUBJECTS = ["게임", "SNS"]  # 랜덤 선택할 주제 목록 (빈 리스트면 모든 available 주제)

# 📌 네이버 자동완성 API 설정
NAVER_AC_URL = "https://mac.search.naver.com/mobile/ac"
NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0 Mobile Safari/537.36",
    "Referer": "https://m.search.naver.com/"
}

# ================================================================================
# 🔍 연관키워드 확장 로직 (related.py 기반)
# ================================================================================

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
        
        return suggestions  # 모든 연관키워드 반환 (제한 없음)
            
    except Exception as e:
        print(f"❌ {keyword} API 호출 실패: {e}")
        return []


def expand_keywords_recursive(seed_keywords: List[str], max_keywords: int = MAX_KEYWORDS) -> List[str]:
    """재귀적으로 키워드 확장하여 연관키워드 리스트 생성"""
    
    # 결과 저장
    processed_keywords = set()  # 이미 처리한 키워드들
    all_keywords = set(seed_keywords)  # 전체 키워드 풀
    
    # 큐를 사용한 BFS 방식으로 확장 (원본 related.py 로직)
    queue = deque()
    
    # 시드키워드들을 큐에 추가 (키워드, 원본시드) 튜플 형태로
    for seed in seed_keywords:
        queue.append((seed, seed))
    
    # 진행률 표시용
    total_processed = 0
    
    consecutive_empty_results = 0  # 연속으로 빈 결과가 나온 횟수
    max_empty_tolerance = 50  # 연속 50번 빈 결과까지 허용
    
    while queue and len(all_keywords) < max_keywords:
        current_keyword, original_seed = queue.popleft()
        
        # 이미 처리한 키워드는 건너뛰기
        if current_keyword in processed_keywords:
            continue
        
        processed_keywords.add(current_keyword)
        total_processed += 1
        
        # 네이버 자동완성 API 호출
        related_keywords = get_naver_autocomplete(current_keyword)
        
        if related_keywords:
            consecutive_empty_results = 0  # 성공하면 리셋
            
            # 새로운 키워드들만 추가
            new_keywords = []
            for kw in related_keywords:
                if kw not in all_keywords:
                    all_keywords.add(kw)
                    new_keywords.append(kw)
                    
                    # 다음 확장을 위해 큐에 추가 (키워드, 원본시드) 튜플로
                    if len(all_keywords) < max_keywords:
                        queue.append((kw, original_seed))
        else:
            consecutive_empty_results += 1
            # 너무 많은 빈 결과가 연속으로 나오면 중단 (API 문제일 가능성)
            if consecutive_empty_results >= max_empty_tolerance:
                print(f"⚠️ 연속 {max_empty_tolerance}번 빈 결과 - 확장 중단")
                break
        
        # API 제한 방지를 위한 딜레이
        if queue:  # 마지막이 아닌 경우에만 딜레이
            try:
                time.sleep(DELAY_BETWEEN_REQUESTS)
            except KeyboardInterrupt:
                break
        
        # 최대 키워드 수 도달 시 중단
        if len(all_keywords) >= max_keywords:
            break
    
    return list(all_keywords)


def load_seed_keywords_from_json(keyword_subject: str) -> List[str]:
    """시드키워드 로드 (상수에서 우선, 없으면 JSON 파일에서)"""
    
    # 1. 상수로 직접 지정된 시드키워드가 있으면 우선 사용
    if CUSTOM_SEED_KEYWORDS:
        print(f"🔧 상수에서 시드키워드 로드: {CUSTOM_SEED_KEYWORDS}")
        # 시드키워드 개수 제한
        if len(CUSTOM_SEED_KEYWORDS) > MAX_SEED_KEYWORDS:
            limited_keywords = CUSTOM_SEED_KEYWORDS[:MAX_SEED_KEYWORDS]
            print(f"⚠️ 시드키워드 개수 제한: {len(CUSTOM_SEED_KEYWORDS)}개 → {len(limited_keywords)}개")
            return limited_keywords
        return CUSTOM_SEED_KEYWORDS
    
    # 2. 상수가 비어있으면 JSON 파일에서 로드
    print(f"📁 JSON 파일에서 시드키워드 로드: {keyword_subject}.json")
    data_dir = Path(__file__).parent.parent.parent / "data" / "keywords"
    json_file = data_dir / f"{keyword_subject}.json"
    
    if not json_file.exists():
        print(f"❌ 키워드 파일을 찾을 수 없습니다: {json_file}")
        return []
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 시드키워드 배열에서 순서대로 추출
        seed_keywords = []
        for item in data.get("seed_keywords", []):
            keyword = item.get("keyword", "")
            if keyword:
                seed_keywords.append(keyword)
        
        return seed_keywords[:MAX_SEED_KEYWORDS]  # 최대 개수 제한
        
    except Exception as e:
        print(f"❌ 키워드 파일 로드 실패: {e}")
        return []


# ================================================================================
# 💰 황금키워드 분석 로직 (gold.py 기반)
# ================================================================================

class NaverAdsClient:
    """네이버 광고 API 클라이언트 - 검색량 조회 전용"""
    
    def __init__(self, config_path: str = "config/base.yaml"):
        self.config = self._load_config(config_path)
        self.base_url = "https://api.searchad.naver.com"
        self.customer_id = self.config['credentials']['naver_ads']['customer_id']
        self.api_key = self.config['credentials']['naver_ads']['api_key']
        self.secret_key = self.config['credentials']['naver_ads']['secret_key']
        
        # 블로그 스테이지 설정 로드
        self.blog_stages_config = self._load_blog_stages_config()
    
    def _load_config(self, config_path: str) -> Dict:
        """설정 파일 로드"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _load_blog_stages_config(self) -> Dict:
        """블로그 스테이지 설정 로드"""
        try:
            with open("config/keyword.yaml", 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"⚠️ 블로그 스테이지 설정 로드 실패: {e}")
            return {}
    
    def _generate_signature(self, timestamp: str, method: str, uri: str) -> str:
        """서명 생성"""
        # URI에서 쿼리 파라미터 제거 (서명용)
        clean_uri = uri.split('?')[0] if '?' in uri else uri
        message = f"{timestamp}.{method}.{clean_uri}"
        
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        # base64 인코딩으로 변경 (네이버 API 요구사항)
        import base64
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        return signature_b64
    
    def _get_headers(self, method: str, uri: str) -> Dict[str, str]:
        """API 요청 헤더 생성"""
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, method, uri)
        
        headers = {
            'X-Timestamp': timestamp,
            'X-API-KEY': self.api_key,
            'X-Customer': str(self.customer_id),
            'X-Signature': signature,
            'Content-Type': 'application/json'
        }
        
        return headers
    
    def _get_search_volume_batch(self, keywords: List[str]) -> Dict[str, Dict[str, str]]:
        """키워드 검색량 조회 (5개 이하 배치) - 디버깅 강화"""
        if len(keywords) > 5:
            raise ValueError("배치당 키워드는 최대 5개까지 입력 가능합니다.")
        
        # 키워드에서 공백 제거 및 정리
        cleaned_keywords = [keyword.strip().replace(' ', '') for keyword in keywords]
        
        log_print(f"🔍 API 요청 키워드: {cleaned_keywords}")
        
        # API 엔드포인트
        uri = "/keywordstool"
        params = {
            'hintKeywords': ','.join(cleaned_keywords),
            'showDetail': 1
        }
        
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        full_uri = f"{uri}?{query_string}"
        
        headers = self._get_headers('GET', full_uri)
        
        try:
            response = requests.get(
                f"{self.base_url}{full_uri}",
                headers=headers
            )
            
            log_print(f"📡 API 응답 상태: {response.status_code}")
            
            response.raise_for_status()
            
            result = response.json()
            log_print(f"📊 API 응답 데이터: {result}")
            
            # 검색량만 추출
            keyword_stats = {}
            
            # 응답이 리스트인지 확인
            if isinstance(result, list):
                log_print(f"✅ 리스트 형태 응답 - {len(result)}개 항목")
                for item in result:
                    if isinstance(item, dict):
                        keyword = item.get('relKeyword', '')
                        if keyword:
                            keyword_stats[keyword] = {
                                'pc_search_volume': item.get('monthlyPcQcCnt', '0'),
                                'mobile_search_volume': item.get('monthlyMobileQcCnt', '0')
                            }
                            log_print(f"   ✓ {keyword}: PC={item.get('monthlyPcQcCnt')}, 모바일={item.get('monthlyMobileQcCnt')}")
            elif isinstance(result, dict) and 'keywordList' in result:
                # keywordList 형태의 응답 처리
                log_print(f"✅ keywordList 형태 응답 - {len(result['keywordList'])}개 항목")
                for item in result['keywordList']:
                    if isinstance(item, dict):
                        keyword = item.get('relKeyword', '')
                        if keyword:
                            keyword_stats[keyword] = {
                                'pc_search_volume': item.get('monthlyPcQcCnt', '0'),
                                'mobile_search_volume': item.get('monthlyMobileQcCnt', '0')
                            }
                            log_print(f"   ✓ {keyword}: PC={item.get('monthlyPcQcCnt')}, 모바일={item.get('monthlyMobileQcCnt')}")
            else:
                log_print(f"⚠️ 예상과 다른 응답 형식: {type(result)}")
                log_print(f"응답 내용: {result}")
                return {}
            
            log_print(f"🎯 최종 추출된 키워드: {len(keyword_stats)}개")
            log_print(f"   요청: {cleaned_keywords}")
            log_print(f"   응답: {list(keyword_stats.keys())}")
            
            # 누락된 키워드 확인
            missing = set(cleaned_keywords) - set(keyword_stats.keys())
            if missing:
                log_print(f"❌ 누락된 키워드: {missing}")
            
            return keyword_stats
            
        except requests.exceptions.RequestException as e:
            log_print(f"❌ API 요청 실패: {e}")
            raise Exception(f"API 요청 실패: {e}")
        except Exception as e:
            log_print(f"❌ 데이터 처리 실패: {e}")
            raise Exception(f"데이터 처리 실패: {e}")

    def get_search_volume(self, keywords: List[str]) -> Dict[str, Dict[str, str]]:
        """키워드 검색량 조회 (자동 배치 처리)"""
        # 5개씩 배치로 나누기
        batches = [keywords[i:i+5] for i in range(0, len(keywords), 5)]
        
        all_results = {}
        
        for i, batch in enumerate(batches, 1):
            try:
                batch_result = self._get_search_volume_batch(batch)
                all_results.update(batch_result)
                
                # API 호출 간격 (과도한 요청 방지)
                if i < len(batches):
                    time.sleep(0.05)  # 0.05초로 초단축
                    
            except Exception as e:
                continue
        
        return all_results
    
    def get_blog_count(self, keyword: str) -> int:
        """키워드의 블로그 문서량 조회 (재시도 로직 포함)"""
        max_retries = 1  # 재시도 1회만
        retry_delay = 0.1  # 0.1초 대기로 초단축
        
        for attempt in range(max_retries):
            try:
                # 네이버 검색 API 설정
                client_id = self.config['credentials']['naver_openapi']['client_id']
                client_secret = self.config['credentials']['naver_openapi']['client_secret']
                
                # URL 인코딩
                enc_text = urllib.parse.quote(keyword)
                url = f"https://openapi.naver.com/v1/search/blog?query={enc_text}&display=1&start=1"
                
                # 요청 생성
                request = urllib.request.Request(url)
                request.add_header("X-Naver-Client-Id", client_id)
                request.add_header("X-Naver-Client-Secret", client_secret)
                
                # API 호출
                response = urllib.request.urlopen(request)
                rescode = response.getcode()
                
                if rescode == 200:
                    response_body = response.read()
                    result = json.loads(response_body.decode('utf-8'))
                    
                    # 총 검색 결과 개수 반환
                    total_count = result.get('total', 0)
                    return total_count
                else:
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        continue
                    return 0
                    
            except urllib.error.HTTPError as e:
                if e.code == 429:  # Too Many Requests
                    time.sleep(0.1)  # 빠른 재시도
                    continue
                else:
                    return 0
            except Exception as e:
                return 0  # 바로 포기
        
        return 0
    
    def get_keyword_stage(self, doc_count: int, total_search: int) -> int:
        """키워드의 스테이지 단계 확인"""
        if not self.blog_stages_config or 'blog_stages' not in self.blog_stages_config:
            return 0
        
        # 1단계부터 5단계까지 순서대로 확인
        for stage_num in range(1, 6):
            stage_key = str(stage_num)
            if stage_key in self.blog_stages_config['blog_stages']:
                stage_config = self.blog_stages_config['blog_stages'][stage_key]
                d_max = stage_config.get('D_max', float('inf'))
                s_min = stage_config.get('S_min', 0)
                s_max = stage_config.get('S_max', float('inf'))
                
                # 기본 조건 확인
                if (doc_count <= d_max and s_min <= total_search <= s_max):
                    # 2~5단계에서는 추가 조건: 검색량 >= 문서수
                    if stage_num == 1:
                        # 1단계는 기본 조건만 확인
                        return stage_num
                    else:
                        # 2~5단계는 검색량이 문서수보다 높거나 같아야 함
                        if total_search >= doc_count:
                            return stage_num
                        # 조건에 맞지 않으면 다음 단계 확인
                        continue
        
        return 0  # 어떤 단계에도 해당하지 않음

    def get_keyword_analysis(self, keywords: List[str]) -> Dict[str, Dict[str, any]]:
        """키워드 통합 분석 (검색량 + 문서량 + 경쟁도) - 배치 처리"""
        
        # 검색량 조회
        search_volume_result = self.get_search_volume(keywords)
        
        # 통합 결과 생성
        analysis_result = {}
        
        # 키워드 정리 (공백 제거)
        cleaned_keywords = [keyword.strip().replace(' ', '') for keyword in keywords]
        
        # 배치 단위로 처리 (50개씩)
        batch_size = 50
        total_batches = (len(keywords) + batch_size - 1) // batch_size
        
        for batch_idx in range(0, len(keywords), batch_size):
            batch_keywords = keywords[batch_idx:batch_idx + batch_size]
            batch_num = (batch_idx // batch_size) + 1
            
            for i, original_keyword in enumerate(batch_keywords):
                global_i = batch_idx + i
                cleaned_keyword = cleaned_keywords[global_i]
                
                if cleaned_keyword in search_volume_result:
                    # 블로그 문서량 조회 (원본 키워드로)
                    blog_count = self.get_blog_count(original_keyword)
                    
                    # API 제한 방지를 위한 간격
                    time.sleep(0.02)  # 각 키워드마다 0.02초만 대기
                    
                    # PC와 모바일 검색량을 정수로 변환 (< 10 같은 문자열 처리)
                    def parse_volume(volume_str):
                        if isinstance(volume_str, int):
                            return volume_str
                        if isinstance(volume_str, str):
                            if volume_str.startswith('<'):
                                return 5  # "< 10"인 경우 5로 처리
                            try:
                                return int(volume_str)
                            except:
                                return 0
                        return 0
                    
                    pc_volume = parse_volume(search_volume_result[cleaned_keyword]['pc_search_volume'])
                    mobile_volume = parse_volume(search_volume_result[cleaned_keyword]['mobile_search_volume'])
                    
                    # 총검색량 계산
                    total_search_volume = pc_volume + mobile_volume
                    
                    # 경쟁도 계산 (문서수 ÷ 총검색량)
                    competition_ratio = round(blog_count / total_search_volume, 3) if total_search_volume > 0 else 0
                    
                    analysis_result[original_keyword] = {
                        'pc_search_volume': pc_volume,
                        'mobile_search_volume': mobile_volume,
                        'total_search_volume': total_search_volume,
                        'blog_count': blog_count,
                        'competition_ratio': competition_ratio
                    }
            
            # 배치 간 대기 (배치 처리 완료 후)
            if batch_num < total_batches:
                time.sleep(0.1)  # 0.1초로 초단축
        
        return analysis_result
    
    def get_keyword_analysis_with_save(self, keywords: List[str]) -> Dict[str, Dict[str, any]]:
        """키워드 통합 분석 - 점진적 저장 (강제종료 시 안전)"""
        
        # 검색량 조회
        search_volume_result = self.get_search_volume(keywords)
        
        # 통합 결과 저장
        analysis_result = {}
        
        # 키워드 정리 (공백 제거)
        cleaned_keywords = [keyword.strip().replace(' ', '') for keyword in keywords]
        
        # 배치 단위로 처리 (20개씩으로 줄여서 더 자주 저장)
        batch_size = 20
        total_batches = (len(keywords) + batch_size - 1) // batch_size
        
        try:
            for batch_idx in range(0, len(keywords), batch_size):
                batch_keywords = keywords[batch_idx:batch_idx + batch_size]
                batch_num = (batch_idx // batch_size) + 1
                
                for i, original_keyword in enumerate(batch_keywords):
                    global_i = batch_idx + i
                    cleaned_keyword = cleaned_keywords[global_i]
                    
                    # 블로그 문서량 조회 (원본 키워드로) - 모든 키워드에 대해 실행
                    blog_count = self.get_blog_count(original_keyword)
                    
                    # API 제한 방지를 위한 간격
                    time.sleep(0.02)  # 각 키워드마다 0.02초만 대기
                    
                    # PC와 모바일 검색량을 정수로 변환 (< 10 같은 문자열 처리)
                    def parse_volume(volume_str):
                        if isinstance(volume_str, int):
                            return volume_str
                        if isinstance(volume_str, str):
                            if volume_str.startswith('<'):
                                return 5  # "< 10"인 경우 5로 처리
                            try:
                                return int(volume_str)
                            except:
                                return 0
                        return 0
                    
                    # 검색량 데이터가 있으면 사용, 없으면 0으로 설정
                    if cleaned_keyword in search_volume_result:
                        pc_volume = parse_volume(search_volume_result[cleaned_keyword]['pc_search_volume'])
                        mobile_volume = parse_volume(search_volume_result[cleaned_keyword]['mobile_search_volume'])
                    else:
                        pc_volume = 0
                        mobile_volume = 0
                    
                    # 총검색량 계산
                    total_search_volume = pc_volume + mobile_volume
                    
                    # 경쟁도 계산 (문서수 ÷ 총검색량)
                    competition_ratio = round(blog_count / total_search_volume, 3) if total_search_volume > 0 else 0
                    
                    analysis_result[original_keyword] = {
                        'pc_search_volume': pc_volume,
                        'mobile_search_volume': mobile_volume,
                        'total_search_volume': total_search_volume,
                        'blog_count': blog_count,
                        'competition_ratio': competition_ratio
                    }
                
                # 배치마다 중간 저장 (황금키워드가 있으면)
                if analysis_result:
                    self._save_intermediate_results(analysis_result)
                
                # 배치 간 대기 (배치 처리 완료 후)
                if batch_num < total_batches:
                    time.sleep(0.1)  # 0.1초로 초단축
            
            return analysis_result
            
        except KeyboardInterrupt:
            print(f"\n🛑 분석 중단됨 - 지금까지 분석된 {len(analysis_result)}개 키워드 저장 중...")
            if analysis_result:
                self._save_final_results(analysis_result)
            raise
    
    def _save_intermediate_results(self, analysis_result: Dict[str, Dict[str, any]]):
        """중간 결과 저장 (황금키워드만)"""
        try:
            # 타겟 스테이지 이내 필터링 (기본/자동 모드 공통)
            filtered_result = self.filter_keywords_by_target_stages(analysis_result, TARGET_STAGES)
            
            # 황금키워드가 있으면 저장
            if filtered_result:
                self.save_to_excel(filtered_result)
        except:
            pass  # 중간 저장 실패해도 계속 진행
    
    def _save_final_results(self, analysis_result: Dict[str, Dict[str, any]]):
        """최종 결과 저장 (강제 종료 시)"""
        try:
            # 타겟 스테이지 이내 필터링 (기본/자동 모드 공통)
            filtered_result = self.filter_keywords_by_target_stages(analysis_result, TARGET_STAGES)
            
            # 결과 저장
            if filtered_result:
                filename = self.save_to_excel(filtered_result)
                print(f"✅ 중단 시점까지 {len(filtered_result)}개 황금키워드 저장 완료: {filename}")
            else:
                print("❌ 저장할 황금키워드가 없습니다.")
        except Exception as e:
            print(f"❌ 최종 저장 실패: {e}")
    
    def filter_keywords_by_stage(self, analysis_result: Dict[str, Dict[str, any]], stage: int = None) -> Dict[str, Dict[str, any]]:
        """블로그 스테이지 조건에 맞는 키워드만 필터링"""
        if stage is None:
            # 기본모드에서는 TARGET_STAGES를 사용 (더 이상 단일 stage가 아님)
            return self.filter_keywords_by_target_stages(analysis_result, TARGET_STAGES)
        
        if not self.blog_stages_config or 'blog_stages' not in self.blog_stages_config:
            print("⚠️ 블로그 스테이지 설정을 찾을 수 없습니다.")
            return analysis_result
        
        stage_key = str(stage)
        if stage_key not in self.blog_stages_config['blog_stages']:
            print(f"⚠️ 스테이지 {stage} 설정을 찾을 수 없습니다.")
            return analysis_result
        
        stage_config = self.blog_stages_config['blog_stages'][stage_key]
        d_max = stage_config.get('D_max', float('inf'))  # 문서수 최대값
        s_min = stage_config.get('S_min', 0)            # 검색량 최소값
        s_max = stage_config.get('S_max', float('inf')) # 검색량 최대값
        
        print(f"🔍 스테이지 {stage} 필터링 조건:")
        print(f"   📄 문서수: ≤ {d_max}")
        print(f"   🔍 검색량: {s_min} ~ {s_max}")
        
        filtered_result = {}
        total_count = len(analysis_result)
        passed_count = 0
        
        for keyword, stats in analysis_result.items():
            doc_count = stats['blog_count']
            total_search = stats['total_search_volume']
            
            # 키워드가 속하는 스테이지 확인
            keyword_stage = self.get_keyword_stage(doc_count, total_search)
            
            # 현재 설정된 스테이지 조건에 맞는지 확인
            if (doc_count <= d_max and 
                s_min <= total_search <= s_max):
                # 스테이지 정보 추가
                stats['stage'] = keyword_stage
                filtered_result[keyword] = stats
                passed_count += 1
        
        print(f"✅ 필터링 완료: {total_count}개 중 {passed_count}개 키워드 통과")
        return filtered_result
    
    def filter_keywords_auto_mode(self, analysis_result: Dict[str, Dict[str, any]], target_stages: List[int] = None) -> Dict[str, Dict[str, any]]:
        """자동모드: 지정된 단계에 해당하는 키워드만 분류하여 저장"""
        if not self.blog_stages_config or 'blog_stages' not in self.blog_stages_config:
            return analysis_result
        
        # 기본값은 TARGET_STAGES 사용
        if target_stages is None:
            target_stages = TARGET_STAGES
        
        auto_result = {}
        
        for keyword, stats in analysis_result.items():
            doc_count = stats['blog_count']
            total_search = stats['total_search_volume']
            
            # 키워드가 속하는 스테이지 확인
            keyword_stage = self.get_keyword_stage(doc_count, total_search)
            
            # 목표 단계에 해당하는 키워드만 저장
            if keyword_stage in target_stages:
                stats['stage'] = keyword_stage
                auto_result[keyword] = stats
        
        return auto_result
    
    def filter_keywords_by_target_stages(self, analysis_result: Dict[str, Dict[str, any]], target_stages: List[int] = None) -> Dict[str, Dict[str, any]]:
        """타겟 스테이지 이내 키워드 필터링 (기본/자동 모드 공통)"""
        if target_stages is None:
            target_stages = TARGET_STAGES
        
        if not self.blog_stages_config or 'blog_stages' not in self.blog_stages_config:
            print("❌ 블로그 스테이지 설정을 불러올 수 없습니다.")
            return {}
        
        filtered_result = {}
        
        for keyword, data in analysis_result.items():
            # 해당 키워드의 스테이지 분류
            keyword_stage = self.get_keyword_stage(data['blog_count'], data['total_search_volume'])
            
            # 타겟 스테이지 이내에 포함되면 필터링
            if keyword_stage in target_stages:
                filtered_result[keyword] = data
                filtered_result[keyword]['stage'] = keyword_stage
        
        return filtered_result
    
    def save_to_excel(self, analysis_result: Dict[str, Dict[str, any]], filename: str = None) -> str:
        """분석 결과를 엑셀 파일로 저장 (기존 데이터에 추가/업데이트)"""
        try:
            # 저장 폴더 생성
            save_directory = "static/gold_keyword"
            os.makedirs(save_directory, exist_ok=True)
            
            # 파일명 설정
            if filename is None:
                filename = f"{KEYWORD_SUBJECT}.xlsx"
            
            # 전체 파일 경로 설정
            filepath = os.path.join(save_directory, filename)
            
            # 기존 파일이 있는지 확인
            existing_df = None
            if os.path.exists(filepath):
                try:
                    existing_df = pd.read_excel(filepath)
                except Exception as e:
                    pass
            
            # 새로운 데이터 준비
            new_data = []
            for keyword, stats in analysis_result.items():
                new_data.append({
                    '키워드': keyword,
                    'PC 검색량': stats['pc_search_volume'],
                    '모바일 검색량': stats['mobile_search_volume'],
                    '총검색량': stats['total_search_volume'],
                    '문서량': stats['blog_count'],
                    '경쟁도': stats['competition_ratio'],
                    '단계': stats.get('stage', 0)  # 스테이지 정보 추가
                })
            
            new_df = pd.DataFrame(new_data)
            
            if existing_df is not None:
                # 자동모드에서 기존 데이터의 0단계 키워드 제거
                if MODE == "AUTO":
                    # 기존 데이터에서 0단계나 NaN 단계 키워드 제거
                    if '단계' in existing_df.columns:
                        existing_df = existing_df[(existing_df['단계'] > 0) & (existing_df['단계'].notna())]
                
                # 기존 데이터와 새 데이터 병합
                # 키워드가 중복되면 새 데이터로 업데이트
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                
                # 중복 키워드 제거 (마지막 데이터 유지)
                combined_df = combined_df.drop_duplicates(subset=['키워드'], keep='last')
            else:
                combined_df = new_df
            
            # 경쟁도(비율)가 낮은 순서대로 정렬
            combined_df = combined_df.sort_values('경쟁도', ascending=True)
            
            # 엑셀 파일 저장
            combined_df.to_excel(filepath, index=False, engine='openpyxl')
            
            return filepath
            
        except Exception as e:
            raise Exception(f"엑셀 저장 실패: {e}")
    
    def save_all_keywords_to_test(self, analysis_result: Dict[str, Dict[str, any]], filename: str = None) -> str:
        """필터링 전 전체 연관키워드 데이터를 static/test/에 저장"""
        try:
            # 저장 폴더 생성
            save_directory = "static/test"
            os.makedirs(save_directory, exist_ok=True)
            
            # 파일명 설정 (타임스탬프 포함)
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{KEYWORD_SUBJECT}_전체연관키워드_{timestamp}.xlsx"
            
            # 전체 파일 경로 설정
            filepath = os.path.join(save_directory, filename)
            
            # 새로운 데이터 준비 (모든 키워드, 스테이지 정보 포함)
            all_data = []
            for keyword, stats in analysis_result.items():
                # 키워드의 스테이지 확인
                keyword_stage = self.get_keyword_stage(stats['blog_count'], stats['total_search_volume'])
                
                all_data.append({
                    '키워드': keyword,
                    'PC 검색량': stats['pc_search_volume'],
                    '모바일 검색량': stats['mobile_search_volume'],
                    '총검색량': stats['total_search_volume'],
                    '문서량': stats['blog_count'],
                    '경쟁도': stats['competition_ratio'],
                    '단계': keyword_stage
                })
            
            # 데이터프레임 생성
            df = pd.DataFrame(all_data)
            
            # 경쟁도(비율)가 낮은 순서대로 정렬
            df = df.sort_values('경쟁도', ascending=True)
            
            # 엑셀 파일 저장
            df.to_excel(filepath, index=False, engine='openpyxl')
            
            return filepath
            
        except Exception as e:
            raise Exception(f"전체 키워드 테스트 저장 실패: {e}")
    
    def debug_search_volume(self, test_keywords: List[str]) -> None:
        """특정 키워드들의 검색량 조회 디버깅"""
        log_print(f"\n🔧 검색량 조회 디버깅 시작 - {len(test_keywords)}개 키워드")
        log_print("=" * 60)
        
        for keyword in test_keywords:
            log_print(f"\n🎯 키워드: '{keyword}'")
            try:
                # 단일 키워드로 API 호출
                result = self._get_search_volume_batch([keyword])
                if result:
                    log_print(f"✅ 성공: {result}")
                else:
                    log_print("❌ 응답 없음")
            except Exception as e:
                log_print(f"❌ 오류: {e}")
            
            log_print("-" * 40)


# ================================================================================
# 🤖 백그라운드 자동모드 로직
# ================================================================================

def get_available_subjects() -> List[str]:
    """사용 가능한 키워드 주제 목록 가져오기"""
    data_dir = Path(__file__).parent.parent.parent / "data" / "keywords"
    available_subjects = []
    
    for json_file in data_dir.glob("*.json"):
        if json_file.stem not in ["", "template"]:  # 템플릿 파일 제외
            available_subjects.append(json_file.stem)
    
    return available_subjects


def select_random_subject() -> str:
    """랜덤 주제 선택"""
    if AUTO_RANDOM_SUBJECTS:
        # 지정된 주제 목록에서 선택
        return random.choice(AUTO_RANDOM_SUBJECTS)
    else:
        # 모든 사용 가능한 주제에서 선택
        available_subjects = get_available_subjects()
        if available_subjects:
            return random.choice(available_subjects)
        else:
            return KEYWORD_SUBJECT  # 기본값 사용


def run_single_analysis(subject: str) -> bool:
    """단일 주제에 대한 황금키워드 분석 실행"""
    analysis_result = None
    client = None
    
    try:
        print(f"\n🔍 주제 '{subject}' 분석 시작...")
        
        # 1단계: 시드키워드 로드
        seed_keywords = load_seed_keywords_from_json(subject)
        if not seed_keywords:
            print(f"❌ '{subject}' 시드키워드를 로드할 수 없습니다.")
            return False
        
        # 2단계: 연관키워드 확장
        all_keywords = expand_keywords_recursive(seed_keywords, max_keywords=MAX_KEYWORDS)
        if not all_keywords:
            print(f"❌ '{subject}' 연관키워드 확장에 실패했습니다.")
            return False
        
        # 2-1단계: 연관키워드 원본 저장 (분석 전)
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_keywords_filename = f"static/test/{subject}_연관키워드원본_{timestamp}.xlsx"
            os.makedirs("static/test", exist_ok=True)
            
            # 단순히 키워드 리스트만 저장
            raw_df = pd.DataFrame({'키워드': all_keywords})
            raw_df.to_excel(raw_keywords_filename, index=False, engine='openpyxl')
            print(f"💾 '{subject}' 연관키워드 원본 저장 완료: {raw_keywords_filename}")
            print(f"📊 연관키워드 원본 수: {len(all_keywords)}개")
        except Exception as e:
            print(f"⚠️ '{subject}' 연관키워드 원본 저장 실패: {e}")
        
        # 3단계: 황금키워드 분석
        client = NaverAdsClient()
        analysis_result = client.get_keyword_analysis(all_keywords)
        
        if not analysis_result:
            print(f"❌ '{subject}' 키워드 분석에 실패했습니다.")
            return False
        
        # 3-1단계: 필터링 전 전체 연관키워드 데이터 저장 (테스트용)
        try:
            test_filename = client.save_all_keywords_to_test(analysis_result, f"{subject}_전체연관키워드_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
            print(f"💾 '{subject}' 필터링 전 전체 연관키워드 저장 완료: {test_filename}")
            print(f"📊 전체 연관키워드 수: {len(analysis_result)}개")
        except Exception as e:
            print(f"⚠️ '{subject}' 전체 연관키워드 테스트 저장 실패: {e}")
        
        # 4단계: 스테이지 필터링 (타겟 스테이지 이내)
        filtered_result = client.filter_keywords_by_target_stages(analysis_result, TARGET_STAGES)
        
        # 5단계: 엑셀 파일 저장
        if filtered_result:
            filename = client.save_to_excel(filtered_result, f"{subject}.xlsx")
            print(f"✅ '{subject}' 황금키워드 저장 완료: {filename}")
            print(f"📊 황금키워드 수: {len(filtered_result)}개")
            return True
        else:
            print(f"❌ '{subject}' 황금키워드가 발견되지 않았습니다.")
            return False
            
    except KeyboardInterrupt:
        print(f"\n🛑 '{subject}' 분석이 중단되었습니다.")
        # 진행된 부분까지 저장
        if analysis_result and client:
            try:
                print(f"💾 진행된 '{subject}' 데이터 저장 중...")
                filtered_result = client.filter_keywords_by_target_stages(analysis_result, TARGET_STAGES)
                if filtered_result:
                    filename = client.save_to_excel(filtered_result, f"{subject}.xlsx")
                    print(f"✅ 중단된 '{subject}' 황금키워드 저장 완료: {filename}")
                    print(f"📊 저장된 키워드 수: {len(filtered_result)}개")
                else:
                    print(f"⚠️ '{subject}' 저장할 황금키워드가 없습니다.")
            except Exception as save_error:
                print(f"❌ '{subject}' 중단 후 저장 실패: {save_error}")
        raise  # KeyboardInterrupt를 다시 발생시켜 상위에서 처리
            
    except Exception as e:
        print(f"❌ '{subject}' 분석 중 오류: {e}")
        # 진행된 부분까지 저장 시도
        if analysis_result and client:
            try:
                print(f"💾 오류 발생, '{subject}' 진행된 데이터 저장 시도...")
                filtered_result = client.filter_keywords_auto_mode(analysis_result, TARGET_STAGES)
                if filtered_result:
                    filename = client.save_to_excel(filtered_result, f"{subject}.xlsx")
                    print(f"✅ 오류 후 '{subject}' 황금키워드 저장 완료: {filename}")
                    print(f"📊 저장된 키워드 수: {len(filtered_result)}개")
            except Exception as save_error:
                print(f"❌ '{subject}' 오류 후 저장 실패: {save_error}")
        return False


def background_auto_worker():
    """백그라운드 자동모드 워커 함수"""
    print(f"🤖 백그라운드 자동모드 시작 - {AUTO_CYCLE_MINUTES}분 주기로 실행")
    print(f"🎯 목표 스테이지: {TARGET_STAGES}단계")
    
    cycle_count = 0
    
    while True:
        try:
            cycle_count += 1
            print(f"\n{'='*60}")
            print(f"🔄 자동 사이클 #{cycle_count} 시작")
            print(f"{'='*60}")
            
            # 랜덤 주제 선택
            selected_subject = select_random_subject()
            print(f"🎲 선택된 주제: '{selected_subject}'")
            
            # 황금키워드 분석 실행
            success = run_single_analysis(selected_subject)
            
            if success:
                print(f"🎉 사이클 #{cycle_count} 완료: '{selected_subject}' 황금키워드 생성 성공!")
            else:
                print(f"⚠️ 사이클 #{cycle_count} 실패: '{selected_subject}' 황금키워드 생성 실패")
            
            # 다음 실행까지 대기
            print(f"\n😴 {AUTO_CYCLE_MINUTES}분 후 다음 사이클 실행...")
            time.sleep(AUTO_CYCLE_MINUTES * 60)
            
        except KeyboardInterrupt:
            print("\n🛑 백그라운드 자동모드 중단됨")
            break
        except Exception as e:
            print(f"❌ 백그라운드 자동모드 에러: {e}")
            print(f"⏱️ 5분 후 재시도...")
            time.sleep(300)  # 5분 대기 후 재시도


def background_auto_mode():
    """백그라운드 자동모드 시작"""
    print("🤖 백그라운드 자동모드 시작")
    print("🛑 종료하려면 Ctrl+C를 누르세요.")
    
    # 백그라운드 스레드로 실행
    worker_thread = Thread(target=background_auto_worker, daemon=True)
    worker_thread.start()
    
    try:
        worker_thread.join()
    except KeyboardInterrupt:
        print("\n🛑 백그라운드 자동모드를 중단합니다.")


# ================================================================================
# 🚀 통합 실행 로직
# ================================================================================

def main():
    """통합 황금키워드 도출 메인 함수"""
    
    # 명령행 인수 처리
    if len(sys.argv) > 1:
        mode_arg = sys.argv[1].lower()
        if mode_arg == "background":
            # 백그라운드 자동모드 실행
            background_auto_mode()
            return 0
    
    # 백그라운드 모드 설정이면 자동으로 백그라운드 실행
    if MODE == "BACKGROUND":
        background_auto_mode()
        return 0
    
    analysis_result = None
    client = None
    
    try:
        # 1. 선택한 시드키워드
        seed_keywords = load_seed_keywords_from_json(KEYWORD_SUBJECT)
        if not seed_keywords:
            print("❌ 시드키워드를 로드할 수 없습니다.")
            return 1
        
        print(f"1. 선택한 시드키워드: {seed_keywords[0]}")
        
        # 2. 연관키워드 확장
        all_keywords = expand_keywords_recursive(seed_keywords)
        if not all_keywords:
            print("❌ 연관키워드 확장에 실패했습니다.")
            return 1
        
        print(f"2. 연관키워드 개수: {len(all_keywords)}개")
        
        # 2-1. 연관키워드 원본 저장 (분석 전)
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_keywords_filename = f"static/test/{KEYWORD_SUBJECT}_연관키워드원본_{timestamp}.xlsx"
            os.makedirs("static/test", exist_ok=True)
            
            # 단순히 키워드 리스트만 저장
            raw_df = pd.DataFrame({'키워드': all_keywords})
            raw_df.to_excel(raw_keywords_filename, index=False, engine='openpyxl')
            print(f"💾 연관키워드 원본 저장 완료: {raw_keywords_filename}")
            print(f"📊 연관키워드 원본 수: {len(all_keywords)}개")
        except Exception as e:
            print(f"⚠️ 연관키워드 원본 저장 실패: {e}")
        
        # 3. 황금키워드 분석 (점진적 저장)
        client = NaverAdsClient()
        analysis_result = client.get_keyword_analysis_with_save(all_keywords)
        
        if not analysis_result:
            print("❌ 키워드 분석에 실패했습니다.")
            return 1
        
        # 3-1. 필터링 전 전체 연관키워드 데이터 저장 (테스트용)
        try:
            test_filename = client.save_all_keywords_to_test(analysis_result)
            print(f"💾 필터링 전 전체 연관키워드 저장 완료: {test_filename}")
            print(f"📊 전체 연관키워드 수: {len(analysis_result)}개")
        except Exception as e:
            print(f"⚠️ 전체 연관키워드 테스트 저장 실패: {e}")
        
        # 4. 스테이지 필터링 (기본/자동 모드 모두 동일하게 처리)
        filtered_result = client.filter_keywords_by_target_stages(analysis_result, TARGET_STAGES)
        
        # 3. 필터링 후 황금키워드 목록
        print(f"3. 필터링 후 황금키워드 목록 ({len(filtered_result)}개):")
        print("=" * 100)
        print(f"{'키워드':<20} {'총검색량':<10} {'문서량':<10} {'경쟁도':<10} {'단계':<5}")
        print("-" * 100)
        
        if filtered_result:
            # 경쟁도 낮은 순으로 정렬하여 출력
            sorted_keywords = sorted(filtered_result.items(), key=lambda x: x[1]['competition_ratio'])
            
            for keyword, stats in sorted_keywords:
                stage = stats.get('stage', 0)
                stage_text = f"{stage}단계" if stage > 0 else "해당없음"
                print(f"{keyword:<20} {stats['total_search_volume']:<10} {stats['blog_count']:<10} {stats['competition_ratio']:<10} {stage_text:<5}")
        else:
            print("❌ 황금키워드가 발견되지 않았습니다.")
        
        # 엑셀 파일 저장
        try:
            filename = client.save_to_excel(filtered_result)
            print(f"\n✅ 엑셀 저장 완료: {filename}")
        except Exception as e:
            print(f"⚠️ 엑셀 저장 실패: {e}")
        
        return 0
        
    except KeyboardInterrupt:
        print(f"\n🛑 분석이 중단되었습니다.")
        # 진행된 부분까지 저장
        if analysis_result and client:
            try:
                print(f"💾 진행된 '{KEYWORD_SUBJECT}' 데이터 저장 중...")
                # 타겟 스테이지 이내 필터링 (기본/자동 모드 공통)
                filtered_result = client.filter_keywords_by_target_stages(analysis_result, TARGET_STAGES)
                
                if filtered_result:
                    filename = client.save_to_excel(filtered_result)
                    print(f"✅ 중단된 '{KEYWORD_SUBJECT}' 황금키워드 저장 완료: {filename}")
                    print(f"📊 저장된 키워드 수: {len(filtered_result)}개")
                else:
                    print(f"⚠️ '{KEYWORD_SUBJECT}' 저장할 황금키워드가 없습니다.")
            except Exception as save_error:
                print(f"❌ '{KEYWORD_SUBJECT}' 중단 후 저장 실패: {save_error}")
        return 1
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        # 진행된 부분까지 저장 시도
        if analysis_result and client:
            try:
                print(f"💾 오류 발생, '{KEYWORD_SUBJECT}' 진행된 데이터 저장 시도...")
                if MODE == "BASIC":
                    filtered_result = client.filter_keywords_by_stage(analysis_result)
                elif MODE == "AUTO":
                    filtered_result = client.filter_keywords_auto_mode(analysis_result, TARGET_STAGES)
                else:
                    filtered_result = {}
                
                if filtered_result:
                    filename = client.save_to_excel(filtered_result)
                    print(f"✅ 오류 후 '{KEYWORD_SUBJECT}' 황금키워드 저장 완료: {filename}")
                    print(f"📊 저장된 키워드 수: {len(filtered_result)}개")
            except Exception as save_error:
                print(f"❌ '{KEYWORD_SUBJECT}' 오류 후 저장 실패: {save_error}")
        return 1


def debug_mode():
    """디버깅 모드 - 특정 키워드들의 검색량 조회 테스트"""
    log_print("🔧 네이버 광고 API 검색량 조회 디버깅 모드")
    
    # 테스트할 키워드들 (유의미해 보이는 키워드들로 설정)
    test_keywords = [
        "게임",
        "모바일게임", 
        "온라인게임",
        "게임추천",
        "RPG게임",
        "액션게임",
        "스마트폰게임",
        "PC게임",
        "무료게임",
        "인기게임"
    ]
    
    try:
        client = NaverAdsClient()
        client.debug_search_volume(test_keywords)
    except Exception as e:
        log_print(f"❌ 디버깅 실패: {e}")


if __name__ == "__main__":
    # 명령행 인수로 디버깅 모드 실행 가능
    if len(sys.argv) > 1 and sys.argv[1].lower() == "debug":
        debug_mode()
    else:
        exit(main())
