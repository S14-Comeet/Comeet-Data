# Comeet-Data

서울 스페셜티 카페 데이터 수집 및 처리 파이프라인

## 프로젝트 개요

Comeet 서비스를 위한 스페셜티 카페 데이터셋 구축 프로젝트입니다. 두 가지 데이터 소스를 결합하여 카페-메뉴-원두-플레이버의 연결 구조를 생성합니다.

### 데이터 소스

| 소스 | 수집 방법 | 데이터 내용 |
| --- | --- | --- |
| **네이버 지도** | Selenium 크롤링 | 서울 스페셜티 카페 정보 (가게명, 주소, 메뉴, 가격) |
| **Kaggle Dataset** | CSV 다운로드 | 원두 평가 데이터 (원산지, 품종, 로스팅, 향미 설명, 점수) |

### 데이터 통계

| 테이블 | 레코드 수 | 설명 |
| --- | --- | --- |
| roasteries | 231 | 로스터리 정보 |
| stores | 246 | 카페 매장 정보 |
| beans | 1,000 | 커피 원두 정보 |
| menus | 1,355 | 메뉴 정보 (커피만) |
| bean_flavor_notes | 4,823 | 원두별 플레이버 노트 |
| menu_bean_mappings | 270 | 메뉴-원두 매핑 |

---

## 데이터 파이프라인

### 전체 플로우

```
[네이버 지도]                        [Kaggle Dataset]
     │                                    │
     ▼                                    ▼
1_crawl_cafes.py                  data/raw/coffee_clean.csv
     │                                    │
     ▼                                    ▼
data/raw/stores.csv              2_process_beans.py (GPT-4o-mini)
data/raw/menus.csv                        │
     │                                    ▼
     │                            data/beans.csv
     │                            data/bean_flavor_notes.csv
     │                                    │
     └────────────────┬───────────────────┘
                      ▼
           3_preprocess_for_db.py
                      │
                      ▼
           data/final/roasteries.csv
           data/final/stores.csv
           data/final/beans.csv
                      │
                      ▼
           4_map_menu_beans.py
                      │
                      ▼
           data/final/menu_bean_mappings.csv
                      │
                      ▼
           5_generate_sql.py
                      │
                      ▼
           sql/data_import.sql
```

---

## 스크립트 상세 설명

### 1. 카페 크롤링 (`1_crawl_cafes.py`)

네이버 지도에서 서울 스페셜티 카페 정보를 수집합니다.

#### 크롤링 전략

- **검색어**: 지역별 스페셜티/로스터리 키워드 조합 (50개+)
  ```
  "서울 스페셜티 커피", "강남 로스터리", "성수 스페셜티", ...
  ```

- **데이터 추출**: `window.__APOLLO_STATE__`에서 JSON 파싱
  - 가게 정보: `PlaceDetailBase:*` 패턴
  - 메뉴 정보: `Menu:*` 패턴

- **봇 감지 우회**:
  - `webdriver` 속성 숨김
  - 랜덤 대기 시간 (2~5초)
  - User-Agent 설정

#### 메뉴 필터링 (블랙리스트 방식)

비커피 메뉴만 제외하고 나머지는 모두 포함:

```python
EXCLUDE_KEYWORDS = [
    # 디저트: 케이크, 쿠키, 스콘, 크로아상, ...
    # 음식: 샌드위치, 토스트, 버거, ...
    # 차류: 녹차, 홍차, 허브티, ...
    # 과일음료: 에이드, 스무디, 주스, ...
    # 빙수/아이스크림, 주류, 상품/굿즈, ...
]

# 가격 범위: 2,000원 ~ 15,000원
```

**커피 메뉴가 1개 이상 있는 가게만 저장**

---

### 2. 원두 전처리 (`2_process_beans.py`)

Kaggle 원두 데이터를 GPT-4o-mini로 정제하고 SCA Flavor Wheel에 매핑합니다.

#### LLM 활용 방식

```python
# LangChain + SSAFY GMS API 프록시
os.environ["OPENAI_API_BASE"] = "https://gms.ssafy.io/gmsapi/api.openai.com/v1"
model = init_chat_model("gpt-4o-mini", model_provider="openai")
```

#### 프롬프트 구조

**입력**: 원두 원본 데이터
```
- 로스터리: Blue Bottle Coffee
- 이름: Ethiopia Yirgacheffe Konga
- 원산지: Ethiopia
- 로스팅: Light
- 향미 설명: Floral, bergamot, stone fruit, honey sweetness...
```

**RAG 컨텍스트**: `data/debug/flavors_rag.json`
- SCA Flavor Wheel 3단계 계층 구조 (Level 1 → 2 → 3)
- 각 플레이버별 키워드 매핑
- 국가/품종/가공법별 일반적 프로파일

**출력**: 정제된 JSON
```json
{
  "name": "에티오피아 예가체프 콩가",
  "country": "에티오피아",
  "farm": "Konga",
  "variety": "Heirloom",
  "processing_method": "Washed",
  "flavor_ids": [90203, 10307, 80104, 902]
}
```

#### 플레이버 매핑 규칙

1. **Level 3 (5자리 ID) 우선 선택** - 가장 구체적인 레벨
2. **자식 선택 시 부모 제외** - 블루베리(10103) 선택 시 베리류(101) 미선택
3. **키워드 매칭** - 향미 설명의 단어와 `keywords` 필드 비교

#### 스킵 규칙

마케팅/브랜딩 네임은 제외:
```
"Morning Glory", "Velvet Dream", "Signature Blend", "House Special"
```

#### 비용 최적화

- 1,000개 랜덤 샘플링
- 10개마다 중간 저장 (API 중단 대비)
- 0.3초 Rate limiting

---

### 3. 메뉴-원두 매핑 (`4_map_menu_beans.py`)

메뉴와 원두를 자동으로 연결합니다.

#### 매핑 전략

**1순위: 메뉴명에서 국가/지역 추출**
```
"에티오피아 예가체프" → 에티오피아 대표 원두 매핑
"콜롬비아 게이샤"     → 콜롬비아 게이샤 품종 원두 매핑
```

**2순위: 가게 description에서 국가 추출**
```
가게 설명: "에티오피아 원두를 직접 로스팅합니다"
→ 해당 가게의 전체 메뉴에 에티오피아 원두 매핑
```

#### 국가별 원두 사전

```python
COUNTRY_BEANS = {
    "에티오피아": {
        "default": [4, 36, 68],      # 구지 함벨라, 예가체프 내추럴
        "예가체프": [36, 42, 70],    # 예가체프 관련 원두
        "시다모": [65, 81, 128],     # 시다모 관련 원두
        "게이샤": [4, 36],           # 게이샤 품종
    },
    "콜롬비아": {
        "default": [1, 11, 85],
        "게이샤": [94, 168, 215],
        "핑크": [63, 150, 252],      # 핑크 부르봉
    },
    # ... 17개국 지원
}
```

#### 국가명 별칭 처리

```python
COUNTRY_ALIASES = {
    "예가체프": "에티오피아",
    "시다모": "에티오피아",
    "수마트라": "인도네시아",
    "만델링": "인도네시아",
    "타라주": "코스타리카",
    "코나": "하와이",
    # ...
}
```

---

### 4. SQL 생성 (`5_generate_sql.py`)

CSV 파일을 MySQL INSERT문으로 변환합니다.

#### 메뉴 카테고리 자동 분류

Java enum과 동일한 값 사용 (우선순위 순서):

| 순위 | 카테고리 | 매칭 키워드 |
| --- | --- | --- |
| 1 | FLAT_WHITE | 플랫화이트, flat white |
| 2 | CAPPUCCINO | 카푸치노, cappuccino |
| 3 | COLD_BREW | 콜드브루, 더치커피 |
| 4 | HAND_DRIP | 핸드드립, 브루잉, 싱글오리진, 에티오피아, 게이샤... |
| 5 | ESPRESSO | 에스프레소, 아인슈페너, 마끼아또... |
| 6 | AMERICANO | 아메리카노, 롱블랙 |
| 7 | LATTE | 라떼, 카페라떼, 모카 |

**가게 대표 카테고리**: 해당 가게 메뉴 중 가장 빈도 높은 카테고리

---

## SCA Flavor Wheel 데이터

`data/debug/flavors_rag.json` 기반 3단계 계층 구조:

```
Level 1 (대분류)     Level 2 (중분류)      Level 3 (소분류)
─────────────────────────────────────────────────────────
FRUITY (과일향)  →  BERRY (베리류)   →  BLUEBERRY (블루베리)
                    │                    RASPBERRY (라즈베리)
                    │                    STRAWBERRY (딸기)
                    │
                    CITRUS (감귤류)  →  LEMON (레몬)
                                        ORANGE (오렌지)
                                        GRAPEFRUIT (자몽)

FLORAL (꽃향)    →  FLORAL_SUB      →  JASMINE (자스민)
                                        ROSE (장미)
                                        CHAMOMILE (카모마일)

SWEET (단맛)     →  BROWN_SUGAR     →  HONEY (꿀)
                                        CARAMELIZED (캐러멜)
                                        MAPLE_SYRUP (메이플)

NUTTY_COCOA      →  COCOA           →  CHOCOLATE (초콜릿)
(견과/코코아)                           DARK_CHOCOLATE (다크초콜릿)
```

총 9개 대분류, 30개 중분류, 60개+ 소분류

---

## 폴더 구조

```
Comeet-Data/
├── scripts/
│   ├── 1_crawl_cafes.py        # 네이버 지도 크롤링
│   ├── 2_process_beans.py      # 원두 전처리 (GPT-4o-mini)
│   ├── 3_preprocess_for_db.py  # DB 스키마 맞춤 전처리
│   ├── 4_map_menu_beans.py     # 메뉴-원두 매핑
│   ├── 5_generate_sql.py       # CSV → SQL 변환
│   ├── 6_import_bean_scores.py # 추천용 점수 데이터
│   └── .deprecated/            # 미사용 스크립트
│
├── data/
│   ├── raw/                    # 원본 데이터
│   │   ├── coffee_clean.csv    # Kaggle 원두 데이터셋
│   │   └── stores.csv          # 크롤링된 카페 데이터
│   ├── beans/                  # 원두 처리 결과
│   ├── stores/                 # 가게/메뉴 처리 결과
│   ├── final/                  # DB Import용 최종 데이터
│   └── debug/                  # 디버그용 (flavors_rag.json 등)
│
├── sql/
│   ├── schema.sql              # DB 스키마 (DDL)
│   ├── flavor_prod.sql         # SCA Flavor Wheel 데이터
│   ├── scores_and_preferences.sql  # 추천 시스템 테이블
│   └── data_import.sql         # 생성된 INSERT문
│
└── docs/                       # 문서
```

---

## 사용법

### 1. 의존성 설치

```bash
pip install selenium webdriver_manager pandas langchain langchain-openai
```

### 2. 스크립트 실행

```bash
# 1. 네이버 지도에서 카페 크롤링
python scripts/1_crawl_cafes.py

# 2. 원두 데이터 전처리 (GPT-4o-mini 사용, API 키 필요)
export OPENAI_API_KEY="your-key"  # 또는 GMS_KEY
python scripts/2_process_beans.py

# 3. DB 스키마에 맞게 전처리
python scripts/3_preprocess_for_db.py

# 4. 메뉴-원두 매핑 생성
python scripts/4_map_menu_beans.py

# 5. SQL 파일 생성
python scripts/5_generate_sql.py

# 6. (선택) 추천용 점수 데이터
python scripts/6_import_bean_scores.py
```

### 3. DB Import

```bash
# 스키마 생성
mysql -u <user> -p <database> < sql/schema.sql

# Flavor 데이터 (SCA Flavor Wheel)
mysql -u <user> -p <database> < sql/flavor_prod.sql

# 전체 데이터
mysql -u <user> -p <database> < sql/data_import.sql

# 추천 시스템 (선택)
mysql -u <user> -p <database> < sql/scores_and_preferences.sql
```

---

## 데이터베이스 스키마

### 주요 테이블

| 테이블 | 설명 | 비고 |
| --- | --- | --- |
| roasteries | 로스터리 | id=1은 Admin Roastery (출처 미상) |
| stores | 카페 매장 | roastery_id FK |
| beans | 원두 | country, variety, processing_method, roasting_level |
| menus | 메뉴 | category enum, store_id FK |
| menu_bean_mappings | 메뉴-원두 매핑 | N:M 관계 |
| bean_flavor_notes | 원두-플레이버 매핑 | N:M 관계 |
| flavors | SCA Flavor Wheel | 3단계 계층 (parent_id) |

### 추천 시스템 테이블

| 테이블 | 설명 |
| --- | --- |
| bean_scores | 정규화된 감각 속성 (acidity, body, sweetness 등) |
| user_preferences | 사용자 취향 프로필 |

---

## 특이사항

- **roastery_id = 1**: Admin Roastery (Kaggle 원두 등 출처 미상)
- **owner_id = 1**: 기본 관리자
- **Flavor 계층**: 자식 선택 시 부모는 자동 포함 (DB에서 처리)
- **메뉴 category**: Java enum과 동일한 문자열 값 사용
