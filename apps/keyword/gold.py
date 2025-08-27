import hashlib
import hmac
import time
import requests
import urllib.request
import urllib.parse
import json
from typing import List, Dict
import yaml
import pandas as pd
from datetime import datetime
import os

# 테스트용 키워드 (디버깅 시 쉽게 수정 가능)
TEST_KEYWORDS = [
    "운빨존많겜", "게임아이템", "RPG장비", "온라인게임", "모바일게임",  # 1-5
    "액션게임", "시뮬레이션", "전략게임", "블로그팁", "일기쓰기"  # 6-10 (더 작은 검색량 키워드 추가)
]

# 키워드 주제 (엑셀 파일명으로 사용)
KEYWORD_SUBJECT = "게임"

# 블로그 스테이지 모드 설정
# MODE: "BASIC" (기본모드) 또는 "AUTO" (자동모드)
MODE = "AUTO"

# 기본모드일 때만 사용되는 스테이지 레벨 (1-5단계 중 선택)
BLOG_STAGES = 4

class NaverAdsClient:
    """네이버 광고 API 클라이언트 - 검색량 조회 전용"""
    
    def __init__(self, config_path: str = "config/base.yaml"):
        self.config = self._load_config(config_path)
        self.base_url = "https://api.searchad.naver.com"  # 올바른 API URL
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
        """
        키워드 검색량 조회 (5개 이하 배치)
        
        Args:
            keywords: 검색할 키워드 리스트 (최대 5개)
        
        Returns:
            키워드별 검색량 정보
        """
        if len(keywords) > 5:
            raise ValueError("배치당 키워드는 최대 5개까지 입력 가능합니다.")
        
        # 키워드에서 공백 제거 및 정리
        cleaned_keywords = [keyword.strip().replace(' ', '') for keyword in keywords]
        
        # API 엔드포인트
        uri = "/keywordstool"
        params = {
            'hintKeywords': ','.join(cleaned_keywords),
            'showDetail': 0
        }
        
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        full_uri = f"{uri}?{query_string}"
        
        headers = self._get_headers('GET', full_uri)
        
        try:
            response = requests.get(
                f"{self.base_url}{full_uri}",
                headers=headers
            )
            
            response.raise_for_status()
            
            result = response.json()
            
            # 검색량만 추출
            keyword_stats = {}
            
            # 응답이 리스트인지 확인
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        keyword = item.get('relKeyword', '')
                        if keyword:
                            keyword_stats[keyword] = {
                                'pc_search_volume': item.get('monthlyPcQcCnt', '0'),
                                'mobile_search_volume': item.get('monthlyMobileQcCnt', '0')
                            }
            elif isinstance(result, dict) and 'keywordList' in result:
                # keywordList 형태의 응답 처리
                for item in result['keywordList']:
                    if isinstance(item, dict):
                        keyword = item.get('relKeyword', '')
                        if keyword:
                            keyword_stats[keyword] = {
                                'pc_search_volume': item.get('monthlyPcQcCnt', '0'),
                                'mobile_search_volume': item.get('monthlyMobileQcCnt', '0')
                            }
            else:
                print(f"⚠️ 예상과 다른 응답 형식: {type(result)}")
                return {}
            
            return keyword_stats
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"API 요청 실패: {e}")
        except Exception as e:
            raise Exception(f"데이터 처리 실패: {e}")

    def get_search_volume(self, keywords: List[str] = None) -> Dict[str, Dict[str, str]]:
        """
        키워드 검색량 조회 (자동 배치 처리)
        
        Args:
            keywords: 검색할 키워드 리스트 (None이면 TEST_KEYWORDS 사용)
        
        Returns:
            키워드별 검색량 정보
        """
        if keywords is None:
            keywords = TEST_KEYWORDS
            
        # 5개씩 배치로 나누기
        batches = [keywords[i:i+5] for i in range(0, len(keywords), 5)]
        print(f"📊 총 {len(keywords)}개 키워드를 {len(batches)}개 배치로 처리합니다.")
        
        all_results = {}
        
        for i, batch in enumerate(batches, 1):
            print(f"🔄 배치 {i}/{len(batches)} 처리 중... ({len(batch)}개 키워드)")
            
            try:
                batch_result = self._get_search_volume_batch(batch)
                all_results.update(batch_result)
                
                # API 호출 간격 (과도한 요청 방지)
                if i < len(batches):
                    print("⏱️ API 호출 간격 대기 중...")
                    time.sleep(1)
                    
            except Exception as e:
                print(f"❌ 배치 {i} 처리 실패: {e}")
                continue
        
        print(f"✅ 배치 처리 완료: {len(all_results)}개 키워드 검색량 조회")
        return all_results
    
    def get_keyword_stage(self, doc_count: int, total_search: int) -> int:
        """
        키워드의 스테이지 단계 확인
        
        Args:
            doc_count: 문서수
            total_search: 총 검색량
        
        Returns:
            해당하는 스테이지 단계 (1-5, 해당 없으면 0)
        """
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

    def filter_keywords_by_stage(self, analysis_result: Dict[str, Dict[str, any]], stage: int = None) -> Dict[str, Dict[str, any]]:
        """
        블로그 스테이지 조건에 맞는 키워드만 필터링
        
        Args:
            analysis_result: 키워드 분석 결과
            stage: 블로그 스테이지 (None이면 BLOG_STAGES 상수 사용)
        
        Returns:
            필터링된 키워드 분석 결과 (스테이지 정보 포함)
        """
        if stage is None:
            stage = BLOG_STAGES
        
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
    
    def filter_keywords_auto_mode(self, analysis_result: Dict[str, Dict[str, any]]) -> Dict[str, Dict[str, any]]:
        """
        자동모드: 1-5단계에 해당하는 키워드만 분류하여 저장 (해당없음 제외)
        
        Args:
            analysis_result: 키워드 분석 결과
        
        Returns:
            1-5단계에 해당하는 키워드만 포함된 분석 결과 (스테이지 정보 포함)
        """
        if not self.blog_stages_config or 'blog_stages' not in self.blog_stages_config:
            print("⚠️ 블로그 스테이지 설정을 찾을 수 없습니다.")
            return analysis_result
        
        print("🔍 자동모드: 1-5단계에 해당하는 키워드만 분류하여 저장...")
        
        auto_result = {}
        total_count = len(analysis_result)
        stage_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 0: 0}  # 0은 해당없음
        
        for keyword, stats in analysis_result.items():
            doc_count = stats['blog_count']
            total_search = stats['total_search_volume']
            
            # 키워드가 속하는 스테이지 확인
            keyword_stage = self.get_keyword_stage(doc_count, total_search)
            
            # 단계별 카운트 (전체 통계용)
            stage_counts[keyword_stage] += 1
            
            # 1-5단계에 해당하는 키워드만 저장 (0단계 제외)
            if keyword_stage > 0:
                stats['stage'] = keyword_stage
                auto_result[keyword] = stats
        
        print("📊 자동 분류 결과:")
        for stage in range(1, 6):
            count = stage_counts[stage]
            if count > 0:
                print(f"   {stage}단계: {count}개")
        
        no_stage_count = stage_counts[0]
        if no_stage_count > 0:
            print(f"   해당없음: {no_stage_count}개 (엑셀 저장 제외)")
        
        saved_count = sum(stage_counts[i] for i in range(1, 6))
        print(f"✅ 자동 분류 완료: 총 {total_count}개 중 {saved_count}개 키워드 저장")
        return auto_result
    
    def search_keywords(self, keywords: List[str] = None) -> Dict[str, Dict[str, str]]:
        """get_search_volume의 별칭"""
        return self.get_search_volume(keywords)
    
    def get_blog_count(self, keyword: str) -> int:
        """
        키워드의 블로그 문서량 조회
        
        Args:
            keyword: 검색할 키워드
        
        Returns:
            블로그 문서 개수
        """
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
                print(f"❌ 블로그 API 오류 코드: {rescode}")
                return 0
                
        except Exception as e:
            print(f"❌ 블로그 문서량 조회 실패: {e}")
            return 0
    
    def get_keyword_analysis(self, keywords: List[str] = None) -> Dict[str, Dict[str, any]]:
        """
        키워드 통합 분석 (검색량 + 문서량 + 경쟁도)
        
        Args:
            keywords: 분석할 키워드 리스트 (None이면 TEST_KEYWORDS 사용)
        
        Returns:
            키워드별 통합 분석 결과
        """
        if keywords is None:
            keywords = TEST_KEYWORDS
        
        # 검색량 조회
        search_volume_result = self.get_search_volume(keywords)
        
        # 통합 결과 생성
        analysis_result = {}
        
        # 키워드 정리 (공백 제거)
        cleaned_keywords = [keyword.strip().replace(' ', '') for keyword in keywords]
        
        for i, original_keyword in enumerate(keywords):
            cleaned_keyword = cleaned_keywords[i]
            if cleaned_keyword in search_volume_result:
                # 블로그 문서량 조회 (원본 키워드로)
                blog_count = self.get_blog_count(original_keyword)
                
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
        
        return analysis_result
    
    def save_to_excel(self, analysis_result: Dict[str, Dict[str, any]], filename: str = None) -> str:
        """
        분석 결과를 엑셀 파일로 저장 (기존 데이터에 추가/업데이트)
        
        Args:
            analysis_result: 키워드 분석 결과
            filename: 저장할 파일명 (None이면 KEYWORD_SUBJECT 사용)
        
        Returns:
            저장된 파일 경로
        """
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
                    print(f"📁 기존 파일 로드: {len(existing_df)}개 키워드")
                except Exception as e:
                    print(f"⚠️ 기존 파일 읽기 실패: {e}")
            
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
                        print(f"📁 기존 파일에서 0단계 키워드 제거 후: {len(existing_df)}개 키워드")
                
                # 기존 데이터와 새 데이터 병합
                # 키워드가 중복되면 새 데이터로 업데이트
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                
                # 중복 키워드 제거 (마지막 데이터 유지)
                combined_df = combined_df.drop_duplicates(subset=['키워드'], keep='last')
                
                print(f"📊 데이터 병합 완료: 기존 {len(existing_df)}개 + 새로 {len(new_data)}개 = 총 {len(combined_df)}개")
            else:
                combined_df = new_df
                print(f"📊 새 파일 생성: {len(new_data)}개 키워드")
            
            # 경쟁도(비율)가 낮은 순서대로 정렬
            combined_df = combined_df.sort_values('경쟁도', ascending=True)
            
            # 엑셀 파일 저장
            combined_df.to_excel(filepath, index=False, engine='openpyxl')
            
            return filepath
            
        except Exception as e:
            raise Exception(f"엑셀 저장 실패: {e}")


# ==================== 실행 스크립트 ====================

def main():
    """네이버 광고 API + 검색 API 통합 테스트"""
    try:
        # 클라이언트 초기화
        client = NaverAdsClient()
        print("✅ 네이버 API 클라이언트 초기화 완료")
        
        # 테스트 키워드 표시
        print(f"\n🔍 테스트 키워드: {', '.join(TEST_KEYWORDS)}")
        
        # 통합 분석 실행
        print("\n📊 키워드 통합 분석 중...")
        result = client.get_keyword_analysis()
        
        # 모드에 따른 키워드 필터링/분류
        if MODE == "BASIC":
            # 기본모드: 설정된 스테이지 조건에 맞는 키워드만 필터링
            print(f"\n🔍 기본모드: 스테이지 {BLOG_STAGES} 조건에 맞는 키워드 필터링 중...")
            filtered_result = client.filter_keywords_by_stage(result)
            result_to_save = filtered_result
        else:
            # 자동모드: 모든 키워드를 1-5단계로 자동 분류
            print(f"\n🔍 자동모드: 모든 키워드를 1-5단계로 자동 분류 중...")
            filtered_result = client.filter_keywords_auto_mode(result)
            result_to_save = filtered_result
        
        print("\n📊 분석 결과:")
        print("=" * 130)
        print(f"{'키워드':<15} {'PC 검색량':<10} {'모바일 검색량':<12} {'총검색량':<10} {'문서량':<12} {'경쟁도':<10} {'단계':<5}")
        print("-" * 130)
        
        if filtered_result:
            for keyword, stats in filtered_result.items():
                stage = stats.get('stage', 0)
                stage_text = f"{stage}단계" if stage > 0 else "해당없음"
                print(f"🔑 {keyword}")
                print(f"   PC 검색량: {stats['pc_search_volume']}")
                print(f"   모바일 검색량: {stats['mobile_search_volume']}")
                print(f"   총검색량: {stats['total_search_volume']}")
                print(f"   문서량: {stats['blog_count']}")
                print(f"   경쟁도: {stats['competition_ratio']}")
                print(f"   단계: {stage_text}")
                print()
        else:
            if MODE == "BASIC":
                print("❌ 설정된 스테이지 조건에 맞는 키워드가 없습니다.")
            else:
                print("❌ 1-5단계에 해당하는 키워드가 없습니다.")
        
        # 엑셀 파일 저장
        try:
            if MODE == "BASIC":
                filename = client.save_to_excel(result_to_save)
                print(f"\n💾 필터링된 결과가 엑셀 파일로 저장되었습니다: {filename}")
            else:
                filename = client.save_to_excel(result_to_save)
                print(f"\n💾 모든 키워드가 단계별로 분류되어 엑셀 파일로 저장되었습니다: {filename}")
        except Exception as e:
            print(f"⚠️ 엑셀 저장 실패: {e}")
        
        print("\n✅ 키워드 통합 분석 완료!")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())