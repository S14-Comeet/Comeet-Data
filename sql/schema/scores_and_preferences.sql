-- ============================================================================
-- Recommendation System: Bean Scores & User Preferences Schema
-- ============================================================================
-- 설계 전략: "데이터 이원화 및 정규화"
-- - UI 표시용 원본 데이터 (beans, cupping_notes)와
-- - 추천 알고리즘용 인덱스 데이터 (bean_scores, user_preferences)를 분리하여 관리
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Bean Scores Table (검색/추천용 정제 테이블)
-- ----------------------------------------------------------------------------
-- 목적: SQL 하드 필터링 및 Vector Search의 메타데이터로 사용
-- 데이터 소스: cupping_notes(내부 데이터) + 외부 CSV 데이터 혼재
-- 연동: beans 테이블과 1:1 관계 (bean_id FK)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bean_scores
(
    id                     BIGINT AUTO_INCREMENT PRIMARY KEY,
    bean_id                BIGINT   NOT NULL UNIQUE COMMENT 'beans 테이블 FK (1:1 관계)',

    -- ========================================================================
    -- 감각 속성 점수 (Sensory Attribute Scores)
    -- 정규화 규칙: 모든 점수는 1-10 스케일의 TINYINT
    --
    -- [변환 공식 - cupping_notes (0-15) → bean_scores (1-10)]
    -- normalized = ROUND((original_score / 15) * 9) + 1
    -- 예: 6.0 → ROUND((6.0/15)*9)+1 = 5 (Medium)
    --     12.0 → ROUND((12.0/15)*9)+1 = 8 (High)
    --
    -- [변환 공식 - 외부 CSV (7-10 float) → bean_scores (1-10)]
    -- 이미 1-10 스케일이므로 ROUND() 후 그대로 사용
    -- ========================================================================
    acidity                TINYINT  NOT NULL DEFAULT 5 COMMENT '산미 (1-10): 1=Very Low, 5=Medium, 10=Very High',
    body                   TINYINT  NOT NULL DEFAULT 5 COMMENT '바디감 (1-10): 1=Very Light, 5=Medium, 10=Very Full',
    sweetness              TINYINT  NOT NULL DEFAULT 5 COMMENT '단맛 (1-10): 1=Very Low, 5=Medium, 10=Very High',
    bitterness             TINYINT  NOT NULL DEFAULT 5 COMMENT '쓴맛 (1-10): 1=Very Low, 5=Medium, 10=Very Strong',
    aroma                  TINYINT  NOT NULL DEFAULT 5 COMMENT '향 (1-10): 1=Weak, 5=Medium, 10=Intense',
    flavor                 TINYINT  NOT NULL DEFAULT 5 COMMENT '풍미 (1-10): 1=Simple, 5=Balanced, 10=Complex',
    aftertaste             TINYINT  NOT NULL DEFAULT 5 COMMENT '여운 (1-10): 1=Short, 5=Medium, 10=Long',

    -- ========================================================================
    -- 총점 및 배전도 (Total Score & Roast Level)
    -- ========================================================================
    total_score            TINYINT  NOT NULL DEFAULT 0 COMMENT '총점 (0-100): 외부 데이터 그대로 또는 cupping_notes 변환',

    roast_level            ENUM ('LIGHT', 'MEDIUM', 'HEAVY')
                                    NOT NULL DEFAULT 'MEDIUM' COMMENT '배전도 (라이트/미디엄/헤비)',

    -- ========================================================================
    -- Flavor Tags (Redis 임베딩 생성용)
    -- SCA Flavor Wheel 기반 태그 배열
    -- 예: ["fruity", "berry", "citrus", "floral", "chocolate"]
    -- ========================================================================
    flavor_tags            JSON              DEFAULT NULL COMMENT 'Redis 임베딩 생성용 태그 배열 (JSON Array)',

    -- ========================================================================
    -- 메타데이터
    -- ========================================================================
    data_source            ENUM ('CUPPING_NOTES', 'EXTERNAL_CSV', 'AGGREGATED')
                                    NOT NULL DEFAULT 'EXTERNAL_CSV' COMMENT '데이터 출처',
    source_id              BIGINT            DEFAULT NULL COMMENT '원본 데이터 ID (cupping_notes.id 등)',
    confidence_score       DECIMAL(3, 2)     DEFAULT 1.00 COMMENT '데이터 신뢰도 (0.00-1.00)',

    created_at             TIMESTAMP         DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP         DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- ========================================================================
    -- 제약조건 및 인덱스
    -- ========================================================================
    CONSTRAINT chk_acidity CHECK (acidity BETWEEN 1 AND 10),
    CONSTRAINT chk_body CHECK (body BETWEEN 1 AND 10),
    CONSTRAINT chk_sweetness CHECK (sweetness BETWEEN 1 AND 10),
    CONSTRAINT chk_bitterness CHECK (bitterness BETWEEN 1 AND 10),
    CONSTRAINT chk_aroma CHECK (aroma BETWEEN 1 AND 10),
    CONSTRAINT chk_flavor CHECK (flavor BETWEEN 1 AND 10),
    CONSTRAINT chk_aftertaste CHECK (aftertaste BETWEEN 1 AND 10),
    CONSTRAINT chk_total_score CHECK (total_score BETWEEN 0 AND 100),

    FOREIGN KEY (bean_id) REFERENCES beans (id) ON DELETE CASCADE,

    -- 필터링 쿼리 최적화용 복합 인덱스
    INDEX idx_filtering (roast_level, acidity, body, total_score),
    INDEX idx_total_score (total_score DESC)
);


-- ----------------------------------------------------------------------------
-- User Preferences Table (사용자 취향 프로필)
-- ----------------------------------------------------------------------------
-- 목적: 가입 직후 '커피 취향 설문(Onboarding Quiz)' 결과 저장 → Cold Start 해결
-- 활용: 감각속성은 하드 필터링에 사용하지 않고, Soft Scoring (유사도 계산)에 활용
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_preferences
(
    id                       BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id                  BIGINT  NOT NULL UNIQUE COMMENT 'users 테이블 FK (1:1 관계)',

    -- ========================================================================
    -- 감각 속성 선호도 (Sensory Preferences)
    -- 하드 필터링에 사용하지 않음 → Soft Scoring (유사도 계산)에 활용
    -- 온보딩 UI: 슬라이더 또는 5단계 선택
    --
    -- [Soft Scoring 활용 예시]
    -- preference_score = 10 - abs(user.pref_acidity - bean.acidity)
    -- 차이가 작을수록 높은 점수 → 추천 랭킹에 반영
    -- ========================================================================
    pref_acidity             TINYINT NOT NULL DEFAULT 5 COMMENT '선호 산미 (1-10): 1=부드러움, 10=강렬함',
    pref_body                TINYINT NOT NULL DEFAULT 5 COMMENT '선호 바디감 (1-10): 1=가벼움, 10=묵직함',
    pref_sweetness           TINYINT NOT NULL DEFAULT 5 COMMENT '선호 단맛 (1-10): 1=드라이, 10=달콤함',
    pref_bitterness          TINYINT NOT NULL DEFAULT 5 COMMENT '선호 쓴맛 (1-10): 1=거의없음, 10=강함',

    -- ========================================================================
    -- 선호 배전도 (Preferred Roast Levels)
    -- 하드 필터링에 사용 (WHERE roast_level IN ...)
    -- JSON 배열로 복수 선택 가능
    -- ========================================================================
    preferred_roast_levels   JSON             DEFAULT '["LIGHT", "MEDIUM", "HEAVY"]'
        COMMENT '선호 배전도 목록 (JSON Array): LIGHT, MEDIUM, HEAVY',

    -- ========================================================================
    -- 선호/비선호 태그 (Liked/Disliked Tags)
    -- liked_tags: Soft Scoring에 활용 (가산점)
    -- disliked_tags: 하드 필터링으로 제외 (WHERE NOT JSON_OVERLAPS)
    -- ========================================================================
    liked_tags               JSON             DEFAULT NULL COMMENT '선호 플레이버 태그 - Soft Scoring용',
    disliked_tags            JSON             DEFAULT NULL COMMENT '비선호 태그 - 하드 필터링으로 제외 (알러지 등)',

    -- ========================================================================
    -- 온보딩 상태 및 메타데이터
    -- ========================================================================
    is_onboarding_completed  BOOLEAN NOT NULL DEFAULT FALSE COMMENT '온보딩 완료 여부',
    onboarding_version       VARCHAR(10)      DEFAULT 'v1.0' COMMENT '온보딩 설문 버전 (향후 업데이트 대비)',
    last_preference_update   TIMESTAMP        DEFAULT NULL COMMENT '마지막 취향 설정 수정일',

    created_at               TIMESTAMP        DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP        DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- ========================================================================
    -- 제약조건 및 인덱스
    -- ========================================================================
    CONSTRAINT chk_pref_acidity CHECK (pref_acidity BETWEEN 1 AND 10),
    CONSTRAINT chk_pref_body CHECK (pref_body BETWEEN 1 AND 10),
    CONSTRAINT chk_pref_sweetness CHECK (pref_sweetness BETWEEN 1 AND 10),
    CONSTRAINT chk_pref_bitterness CHECK (pref_bitterness BETWEEN 1 AND 10),

    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,

    INDEX idx_onboarding (is_onboarding_completed)
);


-- ============================================================================
-- Redis Vector Index 설계 (FT.CREATE 명령어)
-- ============================================================================
-- 아래는 Redis Stack의 RediSearch 모듈을 사용한 인덱스 생성 명령어입니다.
-- Python redis-py 또는 redis-cli에서 실행하세요.
-- ============================================================================

/*
-- ----------------------------------------------------------------------------
-- Step 1: Redis Hash 데이터 구조 (HSET)
-- ----------------------------------------------------------------------------
-- Key Pattern: bean:{bean_id}
-- 예시:
-- HSET bean:1
--     bean_id 1
--     acidity 8
--     body 8
--     sweetness 7
--     bitterness 5
--     aroma 9
--     flavor 9
--     aftertaste 8
--     total_score 92
--     roast_level "MEDIUM"
--     flavor_tags "fruity,berry,citrus"
--     flavor_embedding <1536-dim float32 blob>

-- ----------------------------------------------------------------------------
-- Step 2: Vector Index 생성 (FT.CREATE)
-- ----------------------------------------------------------------------------
FT.CREATE idx:beans
    ON HASH
    PREFIX 1 bean:
    SCHEMA
        -- Numeric Fields (SQL 필터링 대체 또는 2차 필터링용)
        bean_id NUMERIC SORTABLE
        acidity NUMERIC SORTABLE
        body NUMERIC SORTABLE
        sweetness NUMERIC SORTABLE
        bitterness NUMERIC SORTABLE
        aroma NUMERIC SORTABLE
        flavor NUMERIC SORTABLE
        aftertaste NUMERIC SORTABLE
        total_score NUMERIC SORTABLE

        -- Tag Field (배전도 필터링용)
        roast_level TAG SEPARATOR ","

        -- Text Field (플레이버 태그 - 전문 검색용)
        flavor_tags TEXT WEIGHT 1.0

        -- Vector Field (시맨틱 유사도 검색용)
        -- 1536차원: OpenAI text-embedding-3-small 또는 ada-002 기준
        -- HNSW: 대규모 데이터에서 빠른 ANN (Approximate Nearest Neighbor) 검색
        -- FLAT: 소규모 데이터에서 정확한 검색 (brute-force)
        flavor_embedding VECTOR HNSW 6
            TYPE FLOAT32
            DIM 1536
            DISTANCE_METRIC COSINE

-- ----------------------------------------------------------------------------
-- Step 3: 검색 쿼리 예시 (FT.SEARCH)
-- ----------------------------------------------------------------------------
-- 3-1. Hybrid Search: 필터 + Vector 유사도
-- 사용자 취향에 맞는 원두 중 flavor_embedding이 가장 유사한 10개
FT.SEARCH idx:beans
    "(@acidity:[5 8] @body:[6 10] @roast_level:{LIGHT|MEDIUM})=>[KNN 10 @flavor_embedding $query_vec AS similarity]"
    PARAMS 2 query_vec <user_embedding_blob>
    RETURN 4 bean_id total_score roast_level similarity
    SORTBY similarity ASC
    DIALECT 2

-- 3-2. Pre-filter + KNN (성능 최적화)
-- SQL에서 1차 필터링 후 Redis에서 2차 유사도 검색
FT.SEARCH idx:beans
    "*=>[KNN 20 @flavor_embedding $query_vec AS score]"
    PARAMS 2 query_vec <user_embedding_blob>
    RETURN 3 bean_id flavor_tags score
    SORTBY score ASC
    LIMIT 0 10
    DIALECT 2

-- 3-3. Pure Filter Search (Vector 없이 필터만)
FT.SEARCH idx:beans
    "@acidity:[7 10] @roast_level:{LIGHT}"
    RETURN 5 bean_id acidity body total_score roast_level
    SORTBY total_score DESC
    LIMIT 0 20

*/


-- ============================================================================
-- 데이터 동기화 로직 (cupping_notes → bean_scores 변환)
-- ============================================================================
-- 아래는 cupping_notes (0-15 스케일) 데이터를 bean_scores (1-10 스케일)로
-- 변환하여 삽입하는 저장 프로시저입니다.
-- ============================================================================

DELIMITER //

CREATE PROCEDURE sync_cupping_to_bean_scores()
BEGIN
    -- ========================================================================
    -- 변환 공식 설명:
    -- cupping_notes: 0.00 ~ 15.00 (SCA 커핑 스케일)
    -- bean_scores: 1 ~ 10 (정규화된 필터링 스케일)
    --
    -- 변환식: normalized = ROUND((original / 15) * 9) + 1
    -- - 0.00 → ROUND(0 * 0.6) + 1 = 1
    -- - 7.50 → ROUND(4.5) + 1 = 6 (중간값)
    -- - 15.00 → ROUND(9) + 1 = 10
    --
    -- total_score 변환 (0-105 → 0-100):
    -- normalized_total = ROUND((original_total / 105) * 100)
    -- ========================================================================

    INSERT INTO bean_scores (
        bean_id,
        acidity,
        body,
        sweetness,
        bitterness,
        aroma,
        flavor,
        aftertaste,
        total_score,
        roast_level,
        data_source,
        source_id,
        confidence_score
    )
    SELECT
        mbm.bean_id,
        -- acidity_score 변환
        GREATEST(1, LEAST(10, ROUND((cn.acidity_score / 15) * 9) + 1)),
        -- mouthfeel_score → body 변환
        GREATEST(1, LEAST(10, ROUND((cn.mouthfeel_score / 15) * 9) + 1)),
        -- sweetness_score 변환
        GREATEST(1, LEAST(10, ROUND((cn.sweetness_score / 15) * 9) + 1)),
        -- bitterness는 cupping_notes에 없으므로 기본값 5 (중간)
        5,
        -- aroma_score 변환 (fragrance + aroma 평균 사용)
        GREATEST(1, LEAST(10, ROUND(((COALESCE(cn.fragrance_score, 0) + COALESCE(cn.aroma_score, 0)) / 2 / 15) * 9) + 1)),
        -- flavor_score 변환
        GREATEST(1, LEAST(10, ROUND((cn.flavor_score / 15) * 9) + 1)),
        -- aftertaste_score 변환
        GREATEST(1, LEAST(10, ROUND((cn.aftertaste_score / 15) * 9) + 1)),
        -- total_score 변환 (0-105 → 0-100)
        GREATEST(0, LEAST(100, ROUND((cn.total_score / 105) * 100))),
        -- roast_level 변환 (3단계: LIGHT, MEDIUM, HEAVY)
        CASE cn.roast_level
            WHEN 'Light' THEN 'LIGHT'
            WHEN 'Light-Medium' THEN 'LIGHT'
            WHEN 'Medium-Light' THEN 'MEDIUM'
            WHEN 'Medium' THEN 'MEDIUM'
            WHEN 'Medium-Dark' THEN 'HEAVY'
            WHEN 'Dark' THEN 'HEAVY'
            ELSE 'MEDIUM'
        END,
        'CUPPING_NOTES',
        cn.id,
        1.00  -- 내부 데이터이므로 신뢰도 100%
    FROM cupping_notes cn
    INNER JOIN reviews r ON cn.review_id = r.id
    INNER JOIN menus m ON r.menu_id = m.id
    INNER JOIN menu_bean_mappings mbm ON m.id = mbm.menu_id
    ON DUPLICATE KEY UPDATE
        acidity = VALUES(acidity),
        body = VALUES(body),
        sweetness = VALUES(sweetness),
        aroma = VALUES(aroma),
        flavor = VALUES(flavor),
        aftertaste = VALUES(aftertaste),
        total_score = VALUES(total_score),
        roast_level = VALUES(roast_level),
        updated_at = CURRENT_TIMESTAMP;
END //

DELIMITER ;


-- ============================================================================
-- 외부 CSV 데이터 임포트 예시 (LOAD DATA)
-- ============================================================================
-- 외부 CSV (bean_scores.csv)는 이미 1-10 스케일이므로 직접 임포트
--
-- LOAD DATA INFILE '/path/to/bean_scores.csv'
-- INTO TABLE bean_scores
-- FIELDS TERMINATED BY ','
-- ENCLOSED BY '"'
-- LINES TERMINATED BY '\n'
-- IGNORE 1 ROWS
-- (bean_id, @rating, @aroma, @acidity, @body, @flavor, @aftertaste)
-- SET
--     total_score = @rating,
--     aroma = ROUND(@aroma),
--     acidity = ROUND(@acidity),
--     body = ROUND(@body),
--     flavor = ROUND(@flavor),
--     aftertaste = ROUND(@aftertaste),
--     sweetness = 5,      -- CSV에 없으므로 기본값
--     bitterness = 5,     -- CSV에 없으므로 기본값
--     roast_level = 'MEDIUM',  -- CSV에 없으므로 기본값
--     data_source = 'EXTERNAL_CSV';
-- ============================================================================
