"""
외부 CSV 데이터를 bean_scores 테이블 형식으로 변환

데이터 소스:
- data/debug/bean_scores.csv: 기본 점수 데이터
- data/final/beans.csv: roasting_level
- data/final/bean_flavor_notes.csv: flavor 정보 (sweetness, bitterness 추정용)

출력: data/processed/bean_scores_import.csv

사용법:
    python scripts/import_bean_scores.py
"""

import pandas as pd
from pathlib import Path

# 경로 설정
BASE_DIR = Path(__file__).parent.parent
INPUT_SCORES = BASE_DIR / "data" / "debug" / "bean_scores.csv"
INPUT_BEANS = BASE_DIR / "data" / "final" / "beans.csv"
INPUT_FLAVORS = BASE_DIR / "data" / "final" / "bean_flavor_notes.csv"
OUTPUT_DIR = BASE_DIR / "data" / "processed"
OUTPUT_PATH = OUTPUT_DIR / "bean_scores_import.csv"

# ============================================================================
# Flavor ID 분류 (SCA Flavor Wheel 기반)
# ============================================================================

# SWEET 관련 flavor_id (8xx 계열)
SWEET_FLAVOR_IDS = {
    8,      # SWEET (대분류)
    801, 802, 803, 804, 805,  # 중분류
    80101, 80102, 80103, 80104,  # 소분류: Molasses, Maple, Caramel, Honey
}

# BITTERNESS 관련 flavor_id
BITTER_FLAVOR_IDS = {
    5,      # ROASTED (대분류)
    501, 502, 503, 504,  # 중분류: Tobacco, Burnt, Cereal
    50301, 50302, 50303, 50304,  # 소분류: Acrid, Ashy, Smoky, Brown Roast
    40201,  # BITTER (화학적 쓴맛)
    70201, 70202,  # Dark Chocolate (약간의 쓴맛)
}

# Roast Level별 기본 bitterness 가중치
ROAST_BITTERNESS_BASE = {
    "LIGHT": 2,
    "MEDIUM": 5,
    "HEAVY": 8,
}

# Roast Level별 기본 sweetness 가중치 (라이트가 과일향/산미 강조)
ROAST_SWEETNESS_BASE = {
    "LIGHT": 6,
    "MEDIUM": 5,
    "HEAVY": 3,
}


def load_data():
    """모든 데이터 로드"""
    scores = pd.read_csv(INPUT_SCORES)
    beans = pd.read_csv(INPUT_BEANS)
    flavors = pd.read_csv(INPUT_FLAVORS)

    print(f"[데이터 로드]")
    print(f"  - bean_scores.csv: {len(scores)}개")
    print(f"  - beans.csv: {len(beans)}개")
    print(f"  - bean_flavor_notes.csv: {len(flavors)}개")

    return scores, beans, flavors


def calculate_sweetness(bean_id: int, flavor_ids: set, roast_level: str) -> int:
    """
    단맛 점수 계산 (1-10)

    로직:
    1. 기본값: roast_level에 따른 base (LIGHT=6, MEDIUM=5, HEAVY=3)
    2. SWEET 플레이버 개수당 +1 (최대 +4)
    """
    base = ROAST_SWEETNESS_BASE.get(roast_level, 5)
    sweet_count = len(flavor_ids & SWEET_FLAVOR_IDS)

    # 최대 4점 추가
    bonus = min(sweet_count, 4)

    return min(10, max(1, base + bonus))


def calculate_bitterness(bean_id: int, flavor_ids: set, roast_level: str) -> int:
    """
    쓴맛 점수 계산 (1-10)

    로직:
    1. 기본값: roast_level에 따른 base (LIGHT=2, MEDIUM=5, HEAVY=8)
    2. BITTER 플레이버 개수당 +1 (최대 +2)
    """
    base = ROAST_BITTERNESS_BASE.get(roast_level, 5)
    bitter_count = len(flavor_ids & BITTER_FLAVOR_IDS)

    # 최대 2점 추가
    bonus = min(bitter_count, 2)

    return min(10, max(1, base + bonus))


def transform_bean_scores(scores: pd.DataFrame, beans: pd.DataFrame, flavors: pd.DataFrame) -> pd.DataFrame:
    """
    외부 CSV를 bean_scores 테이블 스키마에 맞게 변환
    """
    # bean_id -> roasting_level 매핑
    roast_map = beans.set_index("id")["roasting_level"].to_dict()

    # bean_id -> flavor_ids 집합 매핑
    flavor_map = flavors.groupby("bean_id")["flavor_id"].apply(set).to_dict()

    results = []

    for _, row in scores.iterrows():
        bean_id = row["bean_id"]
        roast_level = roast_map.get(bean_id, "MEDIUM")
        flavor_ids = flavor_map.get(bean_id, set())

        # sweetness, bitterness 추정
        sweetness = calculate_sweetness(bean_id, flavor_ids, roast_level)
        bitterness = calculate_bitterness(bean_id, flavor_ids, roast_level)

        # flavor_tags 생성 (flavor_id를 code로 변환은 추후 처리)
        # 일단 flavor_id 리스트로 저장
        flavor_tags = list(flavor_ids) if flavor_ids else None

        results.append({
            "bean_id": bean_id,
            "acidity": int(round(row["acidity"])),
            "body": int(round(row["body"])),
            "sweetness": sweetness,
            "bitterness": bitterness,
            "aroma": int(round(row["aroma"])),
            "flavor": int(round(row["flavor"])),
            "aftertaste": int(round(row["aftertaste"])),
            "total_score": int(row["rating"]),
            "roast_level": roast_level,
            "flavor_tags": str(flavor_tags) if flavor_tags else None,
            "data_source": "EXTERNAL_CSV",
            "confidence_score": 0.9,
        })

    return pd.DataFrame(results)


def print_summary(df: pd.DataFrame):
    """변환된 데이터 요약 출력"""
    print("\n" + "=" * 60)
    print("변환 결과 요약")
    print("=" * 60)
    print(f"총 레코드: {len(df)}개")

    print(f"\n[로스팅 레벨 분포]")
    print(df["roast_level"].value_counts())

    print(f"\n[감각속성 통계]")
    for col in ["acidity", "body", "sweetness", "bitterness", "aroma", "flavor", "aftertaste", "total_score"]:
        print(f"  {col:12} | min: {df[col].min():3} | max: {df[col].max():3} | mean: {df[col].mean():.1f}")

    print(f"\n[sweetness 분포]")
    print(df["sweetness"].value_counts().sort_index())

    print(f"\n[bitterness 분포]")
    print(df["bitterness"].value_counts().sort_index())


def validate_data(df: pd.DataFrame) -> bool:
    """데이터 유효성 검사"""
    errors = []

    for col in ["acidity", "body", "sweetness", "bitterness", "aroma", "flavor", "aftertaste"]:
        out_of_range = df[(df[col] < 1) | (df[col] > 10)]
        if len(out_of_range) > 0:
            errors.append(f"{col}: {len(out_of_range)}개 값이 1-10 범위 벗어남")

    if errors:
        print("\n[유효성 검사 실패]")
        for err in errors:
            print(f"  - {err}")
        return False

    print("\n[유효성 검사 통과]")
    return True


def generate_insert_sql(df: pd.DataFrame, output_path: Path):
    """INSERT SQL 문 생성"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("-- bean_scores 테이블 데이터 임포트\n")
        f.write("-- 생성일: 자동 생성\n\n")

        f.write("INSERT INTO bean_scores (\n")
        f.write("    bean_id, acidity, body, sweetness, bitterness,\n")
        f.write("    aroma, flavor, aftertaste, total_score,\n")
        f.write("    roast_level, data_source, confidence_score\n")
        f.write(") VALUES\n")

        values = []
        for _, row in df.iterrows():
            val = (
                f"    ({row['bean_id']}, {row['acidity']}, {row['body']}, "
                f"{row['sweetness']}, {row['bitterness']}, {row['aroma']}, "
                f"{row['flavor']}, {row['aftertaste']}, {row['total_score']}, "
                f"'{row['roast_level']}', '{row['data_source']}', {row['confidence_score']})"
            )
            values.append(val)

        f.write(",\n".join(values))
        f.write("\nON DUPLICATE KEY UPDATE\n")
        f.write("    acidity = VALUES(acidity),\n")
        f.write("    body = VALUES(body),\n")
        f.write("    sweetness = VALUES(sweetness),\n")
        f.write("    bitterness = VALUES(bitterness),\n")
        f.write("    aroma = VALUES(aroma),\n")
        f.write("    flavor = VALUES(flavor),\n")
        f.write("    aftertaste = VALUES(aftertaste),\n")
        f.write("    total_score = VALUES(total_score),\n")
        f.write("    roast_level = VALUES(roast_level),\n")
        f.write("    updated_at = CURRENT_TIMESTAMP;\n")


def main():
    # 출력 디렉토리 생성
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 데이터 로드
    scores, beans, flavors = load_data()

    # 변환 실행
    print(f"\n[변환 시작]")
    result_df = transform_bean_scores(scores, beans, flavors)

    # 유효성 검사
    if not validate_data(result_df):
        print("\n변환 중단: 유효성 검사 실패")
        return

    # 요약 출력
    print_summary(result_df)

    # CSV 저장
    result_df.to_csv(OUTPUT_PATH, index=False)
    print(f"\n[저장 완료]")
    print(f"  CSV: {OUTPUT_PATH}")

    # SQL INSERT 문 생성
    sql_path = OUTPUT_DIR / "bean_scores_insert.sql"
    generate_insert_sql(result_df, sql_path)
    print(f"  SQL: {sql_path}")


if __name__ == "__main__":
    main()
