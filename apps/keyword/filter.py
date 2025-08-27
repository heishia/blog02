"""
텍스트 필터링 및 단어 추출 모듈
- KPF-BERT-NER을 사용한 게임 브랜드/제품명 추출
- 로컬 한국어 불용어 파일 사용 (data/stopwords-ko/)
"""

import re
import os
from typing import List, Set, Optional, Tuple, Dict
from collections import Counter
from pathlib import Path

# ============================================================================
# 📋 필터링 설정값들
# ============================================================================

# 🎯 검색 키워드 설정 (여기만 바꾸면 됨!)
KEYWORD_SUBJECT = "게임"  # 🔍 분석할 키워드

# 🎯 정확도 임계값 설정
CONFIDENCE_THRESHOLD = 0.8  # 정확도 0.8 이상만 시드키워드로 등록


# 🚫 로컬 파일에서 한국어 불용어 로드
def _load_auto_stopwords() -> Set[str]:
    """로컬 stopwords-ko 파일에서 불용어 로드"""
    auto_stopwords = set()

    # 프로젝트 루트 기준 경로들
    project_root = Path(__file__).parent.parent.parent  # PPOP_keyword/
    possible_paths = [
        project_root / "data" / "stopwords-ko" / "stopwords-ko.txt",
        project_root / "stopwords-ko" / "stopwords-ko.txt",
        Path("data/stopwords-ko/stopwords-ko.txt"),
        Path("stopwords-ko/stopwords-ko.txt"),
    ]

    for path in possible_paths:
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.read().strip().split("\n")
                    for line in lines:
                        word = line.strip()
                        if word and not word.startswith("#"):  # 주석 제외
                            auto_stopwords.add(word)

                if auto_stopwords:
                    return auto_stopwords

        except Exception:
            continue

    return set()


# 자동 불용어 로드
AUTO_STOPWORDS = _load_auto_stopwords()

# ============================================================================
# 📋 Subject별 라벨 관리 함수
# ============================================================================


def _load_subject_labels_config() -> dict:
    """Subject별 라벨 설정을 JSON에서 로드"""
    import json

    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / "data" / "subject_labels.json"

    try:
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ subject_labels.json 로드 실패: {e}")

    # fallback: 기본 설정 반환
    return {
        "subject_label_mapping": {},
        "default_target_labels": [
            "B-AFW_OTHER_PRODUCTS",
            "I-AFW_OTHER_PRODUCTS",
            "B-TMIG_GENRE",
            "I-TMIG_GENRE",
            "B-TMI_SERVICE",
            "I-TMI_SERVICE",
            "B-TMI_SW",
            "I-TMI_SW",
            "B-OGG_MEDIA",
            "I-OGG_MEDIA",
        ],
    }


def get_target_labels_for_subject(subject: str) -> set:
    """
    Subject에 맞는 타겟 라벨들을 반환

    Args:
        subject: 키워드 주제 (예: "SNS", "GAME")

    Returns:
        set: 해당 subject에서 사용할 라벨들
    """
    config = _load_subject_labels_config()
    subject_mapping = config.get("subject_label_mapping", {})

    if subject in subject_mapping:
        return set(subject_mapping[subject])
    else:
        return set(config.get("default_target_labels", []))


# ============================================================================

# Transformers (KPF-BERT-NER) import
try:
    from transformers import pipeline

    HAS_TRANSFORMERS = True
except ImportError:
    pipeline = None
    HAS_TRANSFORMERS = False

# KPF-BERT-NER 라벨 매핑 임포트
try:
    import sys
    from pathlib import Path

    # 프로젝트 루트를 sys.path에 추가
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    # 이제 data 패키지에서 직접 import
    from data.kobert_label import labels, id2label, label2id

    HAS_LABEL_MAPPING = True
except ImportError:
    id2label = {}
    HAS_LABEL_MAPPING = False

# 글로벌 모델 캐시
_NER_MODEL_CACHE = None


def _try_load_kpf_ner() -> Optional[object]:
    """KPF-BERT-NER 모델 로드"""
    global _NER_MODEL_CACHE

    if _NER_MODEL_CACHE is not None:
        return _NER_MODEL_CACHE

    if HAS_TRANSFORMERS:
        try:
            _NER_MODEL_CACHE = pipeline(
                "ner",
                model="KPF/KPF-bert-ner",
                tokenizer="KPF/KPF-bert-ner",
                aggregation_strategy="max",  # 서브워드 잘 합치기
            )
            print(f"KoBERT 모델 로드 완료")
            return _NER_MODEL_CACHE

        except Exception:
            return None
    return None


def _extract_with_kpf_ner(text: str, ner_model) -> List[Tuple[str, float, str]]:
    """KPF-BERT-NER로 게임 브랜드/제품명 추출 (정확도, 라벨 포함)"""
    try:
        # 🚫 검색 키워드 기반 제외 단어 생성
        exclude_words = set()
        if KEYWORD_SUBJECT:
            exclude_words.add(KEYWORD_SUBJECT)
            keyword_parts = KEYWORD_SUBJECT.split()
            exclude_words.update(keyword_parts)

        if len(text) > 500:
            text = text[:500]

        entities = ner_model(text)

        # 🕐 시간 관련 단어들 (제거용)
        time_words = {
            "어제",
            "오늘",
            "내일",
            "지금",
            "방금",
            "나중에",
            "이따가",
            "최근",
            "예전",
            "월요일",
            "화요일",
            "수요일",
            "목요일",
            "금요일",
            "토요일",
            "일요일",
            "월",
            "화",
            "수",
            "목",
            "금",
            "토",
            "일",
            "아침",
            "점심",
            "저녁",
            "밤",
            "새벽",
            "오전",
            "오후",
            "낮",
            "밤중",
            "봄",
            "여름",
            "가을",
            "겨울",
            "주말",
            "평일",
            "휴일",
            "연휴",
            "방학",
            "과거",
            "현재",
            "미래",
            "당시",
            "그때",
            "이때",
            "요즘",
            "근래",
        }

        # 🎮 Subject별 타겟 라벨 가져오기 (JSON에서 로드)
        target_labels = get_target_labels_for_subject(KEYWORD_SUBJECT)

        meaningful_words = []
        for entity in entities:
            entity_group = entity["entity_group"]
            score = entity["score"]
            word = entity["word"].strip()

            # 🔥 LABEL_숫자를 실제 라벨명으로 변환
            display_label = entity_group
            actual_label = entity_group

            if entity_group.startswith("LABEL_") and HAS_LABEL_MAPPING:
                try:
                    label_id = int(entity_group.split("_")[1])
                    actual_label = id2label.get(label_id, entity_group)
                    display_label = actual_label
                except:
                    pass

            # 🎯 타겟 라벨만 필터링
            if actual_label not in target_labels:
                continue

            # 🚫 서브워드 토큰 제거
            if word.startswith("##"):
                continue

            # 🚫 너무 짧거나 이상한 단어 제거
            if len(word) < 2:
                continue

            # 🚫 숫자가 포함된 단어 제거
            if any(c.isdigit() for c in word):
                continue

            # 🚫 시간 관련 단어 제거
            if word in time_words:
                continue

            # 🚫 특수문자만 있는 단어 제거
            if not any(c.isalnum() or c in "가-힣" for c in word):
                continue

            # 🚫 영어단어 제거 (한글이 포함되지 않은 경우)
            if not any(c in "가-힣" for c in word):
                continue

            # 🚫 너무 긴 텍스트 (잘못 추출된 것) 제거
            if len(word) > 15:
                continue

            # 🚫 불용어 제거
            if word in AUTO_STOPWORDS:
                continue

            # 🚫 검색 키워드와 정확히 일치하는 단어 제외
            if word in exclude_words:
                continue

            # ✅ 정확도 0.8 이상만 시드키워드로 등록
            if score > CONFIDENCE_THRESHOLD:
                meaningful_words.append((word, score, display_label))  # 3개 값 반환

        return meaningful_words

    except Exception:
        return []


def extract_game_brands(
    texts: List[str],
    min_len: int = 2,
    max_len: int = 15,
) -> List[Tuple[str, float, str]]:

    # KPF-BERT-NER 모델 로드
    ner_model = _try_load_kpf_ner()

    if not ner_model:
        print("❌ KPF-BERT-NER 로드 실패")
        return []

    all_words = []

    # 10% 단위로 진행 상황 표시
    total = len(texts)
    for i, text in enumerate(texts):
        if not text:
            continue

        # 10% 단위로만 진행 상황 표시
        if total > 100 and (i + 1) % (total // 10) == 0:
            percent = int(((i + 1) / total) * 100)
            print(f"  📊 키워드 추출 진행: {percent}%")

        # KPF-NER로 게임 브랜드/제품명 추출 (정확도, 라벨 포함)
        words_with_scores = _extract_with_kpf_ner(text, ner_model)
        all_words.extend(words_with_scores)

    print(" KoBERT 모델로 시드키워드 추출 완료")

    # 최종 길이 필터링만 적용
    filtered_words = []
    for word, score, label in all_words:
        word = word.strip()
        if min_len <= len(word) <= max_len:
            filtered_words.append((word, score, label))

    return filtered_words


def get_top_confidence_keywords(
    texts: List[str],
    min_len: int = 2,
    max_len: int = 15,
    top_k: int = 100,
) -> List[Dict]:
    """
    정확도 기준으로 상위 키워드 추출 (중복 제거)

    Args:
        texts: 입력 텍스트 목록
        min_len: 최소 단어 길이
        max_len: 최대 단어 길이
        top_k: 상위 K개 반환

    Returns:
        List[Dict]: 키워드 상세 정보 리스트
    """
    # 게임 브랜드/제품명 추출 (정확도, 라벨 포함)
    # _extract_with_kpf_ner에서 이미 영어, 숫자, 특수문자 필터링 완료
    keywords_with_data = extract_game_brands(
        texts=texts,
        min_len=min_len,
        max_len=max_len,
    )

    # 키워드별 최고 정확도와 라벨 수집
    keyword_best = {}
    for keyword, score, label in keywords_with_data:
        # float32를 일반 float로 변환
        score = float(score)

        if keyword not in keyword_best:
            keyword_best[keyword] = {"confidence": score, "labels": {label}}
        else:
            # 더 높은 정확도로 업데이트
            if score > keyword_best[keyword]["confidence"]:
                keyword_best[keyword]["confidence"] = score
            # 라벨 추가
            keyword_best[keyword]["labels"].add(label)

    # 결과 리스트 생성
    keyword_results = []
    for keyword, data in keyword_best.items():
        keyword_results.append(
            {
                "keyword": keyword,
                "confidence": round(data["confidence"], 3),
                "labels": list(data["labels"]),
            }
        )

    # 정확도 기준으로 정렬
    keyword_results.sort(key=lambda x: x["confidence"], reverse=True)

    return keyword_results[:top_k]


def print_filtering_stats(texts: List[str], final_ranking: List[Tuple[str, int]]):
    """필터링 통계 출력"""
    print(
        f"📊 분석 결과: {len(texts)}개 텍스트 → {len(final_ranking)}개 게임 브랜드/제품명"
    )


def save_seed_keywords_json(keyword_subject: str, seed_keywords: List[Dict]) -> str:
    """시드키워드를 JSON으로 저장 (기존 파일에 새 키워드만 추가)"""
    import json
    from datetime import datetime

    # data/keywords/ 폴더에 저장
    project_root = Path(__file__).parent.parent.parent
    save_dir = project_root / "data" / "keywords"
    save_dir.mkdir(exist_ok=True)

    # 🎮 게임 관련 서브젝트는 모두 "게임.json"에 저장
    if "게임" in keyword_subject:
        filename = "게임.json"
    else:
        filename = f"{keyword_subject.replace(' ', '_')}.json"
    
    file_path = save_dir / filename

    # 기존 파일이 있으면 로드
    existing_keywords = set()
    existing_data = {"keyword_subject": keyword_subject, "seed_keywords": []}

    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                # 기존 키워드들을 set으로 저장
                existing_keywords = {
                    item["keyword"] for item in existing_data["seed_keywords"]
                }
        except:
            pass

    # 새로운 키워드만 필터링 (순서대로 추가)
    new_keywords = []
    added_count = 0
    current_order = len(existing_data["seed_keywords"])

    for keyword_info in seed_keywords:
        keyword = keyword_info["keyword"]
        if keyword not in existing_keywords:
            # 추가 순서 기록
            keyword_info["added_order"] = current_order + added_count + 1
            new_keywords.append(keyword_info)
            added_count += 1

    # 기존 키워드와 새 키워드 합치기 (순서대로)
    all_keywords = existing_data["seed_keywords"] + new_keywords

    # 정확도 기준으로 정렬 (기존 순서는 유지)
    # 기존 키워드들은 원래 순서 유지, 새 키워드들만 정확도 순으로 정렬
    existing_keywords_list = existing_data["seed_keywords"]
    new_keywords_sorted = sorted(new_keywords, key=lambda x: x.get("confidence", 0), reverse=True)
    
    all_keywords = existing_keywords_list + new_keywords_sorted

    # 저장할 데이터
    data = {
        "keyword_subject": keyword_subject,
        "last_updated": datetime.now().isoformat(),
        "total_keywords": len(all_keywords),
        "seed_keywords": all_keywords,
    }

    # JSON 파일 저장
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"새로운 키워드 {added_count}개 추가됨 (전체: {len(all_keywords)}개)")
    return str(file_path)


if __name__ == "__main__":
    # 이제 전역 변수 KEYWORD_SUBJECT 사용

    import sys
    from pathlib import Path

    # 프로젝트 루트 경로 설정
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    from common.config import load_merged
    from apps.keyword.crawlers import crawl_all_sources

    # 설정 로드 (API 자격증명만)
    try:
        cfg = load_merged("config/base.yaml")
        cred = cfg["credentials"]["naver_openapi"]
    except Exception as e:
        print(f"⚠️ 설정 로드 실패: {e}")
        cred = {}

    # 1단계: 크롤링 실행
    texts = crawl_all_sources(
        keyword=KEYWORD_SUBJECT,
        limit_per_source=500,  # 각 소스별 수집 문서 수
        cred=cred,
    )

    if not texts:
        print("❌ 수집된 텍스트가 없습니다. 네이버 API 설정을 확인하세요.")
        sys.exit(1)

    # 2단계: 정확도 기준 키워드 추출
    final_ranking = get_top_confidence_keywords(
        texts=texts,
        min_len=2,  # 최소 2글자
        max_len=15,  # 최대 15글자
        top_k=200,  # 상위 100개
    )

    # 3단계: 결과 출력 및 저장
    print(f"📊 분석 결과: {len(texts)}개 텍스트 → {len(final_ranking)}개 고품질 키워드")

    # 시드키워드 JSON 저장 (새 키워드만 추가)
    if final_ranking:
        save_path = save_seed_keywords_json(KEYWORD_SUBJECT, final_ranking)
