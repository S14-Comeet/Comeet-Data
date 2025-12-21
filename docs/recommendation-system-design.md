# 추천 시스템 설계 문서

> 최종 수정: 2025-12-21
> 관련 스키마: `sql/schema/scores_and_preferences.sql`

---

## 1. 설계 전략: 데이터 이원화

### 개요

UI 표시용 원본 데이터와 추천 알고리즘용 인덱스 데이터를 분리하여 관리합니다.

| 레이어 | 테이블 | 용도 |
| ------ | ------ | ---- |
| 원본 데이터 | `beans`, `cupping_notes` | 상세 정보 표시, 원본 보존 |
| 인덱스 데이터 | `bean_scores` | Vector Search 메타데이터, Soft Scoring |
| 사용자 프로필 | `user_preferences` | 온보딩 결과, Cold Start 해결 |

---

## 2. 필터링 전략

### 2.1 하드 필터링 vs Soft Scoring

| 항목 | 방식 | 설명 |
| ---- | ---- | ---- |
| `preferred_roast_levels` | **하드 필터링** | WHERE 절로 제외 |
| `disliked_tags` | **하드 필터링** | 해당 태그 원두 완전 제외 |
| `pref_acidity`, `pref_body` 등 | **Soft Scoring** | 유사도 점수 계산에 활용 |
| `liked_tags` | **Soft Scoring** | 가산점 부여 |

### 2.2 결정 근거

**감각속성을 하드 필터링에서 제외한 이유:**

```
현재 데이터 분포:
acidity: 97%가 8-9 범위
body:    99%가 8-9 범위
```

- 데이터가 좁은 범위에 편중되어 하드 필터링 시 변별력 없음
- Soft Scoring으로 유사도 점수에 반영하는 것이 효과적

**disliked_tags를 하드 필터링하는 이유:**

- "싫어하는 것"은 강한 거부감 → 아예 안 보여주는 게 UX상 좋음
- 알러지(견과류 향 등)는 반드시 제외해야 함

---

## 3. 테이블 설계

### 3.1 bean_scores (검색/추천용 정제 테이블)

```sql
CREATE TABLE bean_scores (
    bean_id         BIGINT NOT NULL UNIQUE,  -- beans FK (1:1)

    -- 감각 속성 (원본 스케일 유지, 정규화 안 함)
    acidity         TINYINT NOT NULL,  -- 실제 범위: 6-10
    body            TINYINT NOT NULL,  -- 실제 범위: 7-10
    sweetness       TINYINT NOT NULL,  -- 기본값 5
    bitterness      TINYINT NOT NULL,  -- 기본값 5
    aroma           TINYINT NOT NULL,  -- 실제 범위: 7-10
    flavor          TINYINT NOT NULL,  -- 실제 범위: 7-10
    aftertaste      TINYINT NOT NULL,  -- 실제 범위: 7-9

    total_score     TINYINT NOT NULL,  -- 0-100
    roast_level     ENUM('LIGHT', 'MEDIUM', 'HEAVY'),
    flavor_tags     JSON,              -- Redis 임베딩용
    data_source     ENUM('CUPPING_NOTES', 'EXTERNAL_CSV', 'AGGREGATED')
);
```

### 3.2 user_preferences (사용자 취향 프로필)

```sql
CREATE TABLE user_preferences (
    user_id         BIGINT NOT NULL UNIQUE,  -- users FK (1:1)

    -- 감각속성 선호도 (단일값, Soft Scoring용)
    pref_acidity    TINYINT DEFAULT 5,  -- 1=부드러움, 10=강렬함
    pref_body       TINYINT DEFAULT 5,  -- 1=가벼움, 10=묵직함
    pref_sweetness  TINYINT DEFAULT 5,  -- 1=드라이, 10=달콤함
    pref_bitterness TINYINT DEFAULT 5,  -- 1=거의없음, 10=강함

    -- 하드 필터링용
    preferred_roast_levels  JSON,   -- ["LIGHT", "MEDIUM", "HEAVY"]
    disliked_tags           JSON,   -- 제외할 플레이버 (알러지 등)

    -- Soft Scoring용
    liked_tags              JSON,   -- 선호 플레이버 (가산점)

    is_onboarding_completed BOOLEAN DEFAULT FALSE
);
```

---

## 4. 추천 파이프라인

### 4.1 전체 흐름

```
[1] 하드 필터링 (SQL)
    └─ roast_level IN (preferred_roast_levels)
    └─ NOT JSON_OVERLAPS(flavor_tags, disliked_tags)
           ↓
[2] Vector Search (Redis)
    └─ flavor_embedding 코사인 유사도
    └─ KNN으로 상위 N개 후보 추출
           ↓
[3] Soft Scoring (Re-ranking)
    └─ 감각속성 유사도 점수
    └─ liked_tags 매칭 가산점
           ↓
[4] 최종 결과 반환
```

### 4.2 하드 필터링 쿼리 예시

```sql
SELECT bs.*
FROM bean_scores bs
WHERE
    -- 배전도 필터
    JSON_CONTAINS(
        '["LIGHT", "MEDIUM"]',  -- user.preferred_roast_levels
        CONCAT('"', bs.roast_level, '"')
    )
    -- disliked_tags 제외
    AND NOT JSON_OVERLAPS(
        bs.flavor_tags,
        '["smoky", "earthy"]'   -- user.disliked_tags
    );
```

### 4.3 Soft Scoring 로직 (Python 예시)

```python
def calculate_preference_score(user_pref, bean_score):
    """
    사용자 선호도와 원두 점수의 유사도 계산
    차이가 작을수록 높은 점수 (최대 10점)
    """
    score = 0

    # 감각속성 유사도 (각 속성당 최대 10점)
    score += 10 - abs(user_pref.acidity - bean_score.acidity)
    score += 10 - abs(user_pref.body - bean_score.body)
    score += 10 - abs(user_pref.sweetness - bean_score.sweetness)
    score += 10 - abs(user_pref.bitterness - bean_score.bitterness)

    # liked_tags 가산점 (태그당 5점)
    if user_pref.liked_tags:
        matched = set(user_pref.liked_tags) & set(bean_score.flavor_tags or [])
        score += len(matched) * 5

    return score
```

---

## 5. 온보딩 가이드

### 5.1 감각속성 (Soft Scoring용)

온보딩 UI에서 슬라이더 또는 5단계 선택으로 수집합니다.

```
질문: "어떤 산미를 선호하시나요?"

UI 표시        | DB 저장값 | 설명
---------------|----------|------------------
"부드러운"      | 3        | 낮은 산미 선호
"밸런스"        | 5        | 중간
"밝고 강렬한"   | 8        | 높은 산미 선호
```

### 5.2 배전도 (하드 필터링용)

복수 선택 가능한 체크박스로 수집합니다.

```
질문: "선호하는 로스팅 정도를 선택해주세요 (복수 선택 가능)"

[ ] 라이트 - 산미 강조, 과일향
[x] 미디엄 - 밸런스
[x] 다크   - 쓴맛, 고소함

→ DB 저장: ["MEDIUM", "HEAVY"]
```

### 5.3 비선호 태그 (하드 필터링용)

싫어하거나 알러지가 있는 향을 선택합니다.

```
질문: "피하고 싶은 향이 있나요? (알러지 포함)"

[ ] 견과류 (nutty)
[x] 흙/흙냄새 (earthy)
[x] 훈연향 (smoky)
[ ] 발효향 (fermented)

→ DB 저장: ["earthy", "smoky"]
→ 해당 태그가 있는 원두는 추천에서 완전 제외
```

---

## 6. 점수 정규화 결정

### 결정 사항: 정규화 하지 않음

#### 현재 데이터 분포 (bean_scores.csv 기준)

```
총 레코드: 1,000개

컬럼        | 범위   | 분포 특성
------------|--------|------------------
rating      | 84-98  | 0-100 스케일
aroma       | 7-10   | 90%가 9.0
acidity     | 6-10   | 97%가 8-9
body        | 7-10   | 99%가 8-9
flavor      | 7-10   | 95%가 9-10
aftertaste  | 7-9    | 94%가 8
```

> 데이터가 6-10 상위권에 편중된 이유:
> SCA 스페셜티 커피 기준 (80점 이상 고품질 원두) 데이터이기 때문

#### 선택 근거

1. **외부 데이터 호환성**: 다른 데이터 소스와 스케일 통일 유지
2. **원본 의미 보존**: SCA 기준 점수 그대로 저장
3. **단순성**: 변환 로직 불필요, 디버깅 용이
4. **Soft Scoring 활용**: 하드 필터링 대신 유사도 점수로 활용

---

## 7. 데이터 동기화

### 7.1 cupping_notes → bean_scores 변환

`cupping_notes` 테이블은 SCA 커핑 스케일 (0-15)을 사용합니다.
`bean_scores`로 동기화 시 1-10 스케일로 변환합니다.

```sql
-- 변환 공식
normalized = ROUND((original_score / 15) * 9) + 1

-- 예시
0.00  → 1
7.50  → 6 (중간)
15.00 → 10
```

### 7.2 외부 CSV 데이터

현재 `bean_scores.csv`는 이미 적절한 스케일이므로 ROUND() 후 직접 저장.

```sql
SET acidity = ROUND(@acidity),  -- 8.0 → 8
    body = ROUND(@body),
    ...
```

---

## 8. Redis Vector Index

### 8.1 인덱스 구조

```redis
FT.CREATE idx:beans ON HASH PREFIX 1 bean:
SCHEMA
    -- 하드 필터링용
    roast_level TAG

    -- Soft Scoring 참조용 (Redis에서 직접 필터링 안 함)
    acidity NUMERIC SORTABLE
    body NUMERIC SORTABLE

    -- 시맨틱 검색용 (1536차원, OpenAI embedding)
    flavor_embedding VECTOR HNSW 6 TYPE FLOAT32 DIM 1536 DISTANCE_METRIC COSINE
```

### 8.2 Hybrid Search 예시

```redis
FT.SEARCH idx:beans
    "(@roast_level:{LIGHT|MEDIUM})=>[KNN 20 @flavor_embedding $vec AS similarity]"
    PARAMS 2 vec <embedding_blob>
    RETURN 5 bean_id acidity body roast_level similarity
    SORTBY similarity ASC
```

> 감각속성(acidity, body)은 Redis에서 필터링하지 않고,
> 결과를 가져온 후 애플리케이션에서 Soft Scoring 수행

---

## 9. 추후 고려 사항

1. **데이터 확장 시**: 새로운 데이터 소스가 다른 스케일을 사용할 경우, `data_source`별 변환 로직 추가 검토
2. **A/B 테스트**: Soft Scoring 가중치 최적화를 위한 사용자 행동 분석
3. **동적 범위**: 데이터가 충분히 쌓이면 Percentile 기반 동적 스코어링 고려

---

## 변경 이력

| 날짜 | 변경 내용 |
| ---- | --------- |
| 2025-12-21 | 초안 작성 |
| 2025-12-21 | 로스팅 레벨 3단계로 확정 (LIGHT, MEDIUM, HEAVY) |
| 2025-12-21 | 감각속성 하드 필터링 → Soft Scoring으로 변경 |
| 2025-12-21 | user_preferences min/max 범위 → 단일값으로 변경 |
| 2025-12-21 | disliked_tags 하드 필터링 결정 |
