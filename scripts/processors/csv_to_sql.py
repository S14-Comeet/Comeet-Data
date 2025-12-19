"""
CSV to SQL INSERT 변환 스크립트

data/final/ 폴더의 CSV 파일들을 SQL INSERT 문으로 변환합니다.
외래키 의존성을 고려한 순서로 생성합니다.
"""

import pandas as pd
from pathlib import Path
import re
from collections import Counter

# 경로 설정
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "final"
OUTPUT_DIR = PROJECT_ROOT / "sql"

# 커피 카테고리 정의
COFFEE_CATEGORIES = ['핸드드립', '라떼', '콜드브루', '에스프레소', '아메리카노']

# 메뉴 이름 기반 카테고리 분류 키워드
CATEGORY_KEYWORDS = {
    '핸드드립': ['핸드드립', '드립', '싱글오리진', 'single origin', 'pour over', '푸어오버',
                '에티오피아', '케냐', '콜롬비아', '과테말라', '브라질', '게이샤', '예가체프'],
    '라떼': ['라떼', 'latte', '라테', '카푸치노', 'cappuccino', '플랫화이트', 'flat white',
            '바닐라라떼', '카라멜라떼', '헤이즐넛라떼', '모카', 'mocha'],
    '콜드브루': ['콜드브루', 'cold brew', '더치', 'dutch', '더치커피'],
    '에스프레소': ['에스프레소', 'espresso', '리스트레토', 'ristretto', '도피오', 'doppio',
                 '마끼아또', '마키아토', 'macchiato', '아포가토', 'affogato', '콘파나'],
    '아메리카노': ['아메리카노', 'americano', '롱블랙', 'long black']
}


def classify_menu_category(menu_name):
    """메뉴 이름을 기반으로 카테고리 분류"""
    if pd.isna(menu_name) or menu_name == '':
        return None

    menu_name_lower = str(menu_name).lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in menu_name_lower:
                return category

    return None


def calculate_store_categories(menus_df):
    """각 가게별 가장 많은 카테고리 계산"""
    store_categories = {}

    # 각 메뉴에 카테고리 할당
    menus_df['classified_category'] = menus_df['name'].apply(classify_menu_category)

    # 가게별로 카테고리 카운트
    for store_id in menus_df['store_id'].unique():
        store_menus = menus_df[menus_df['store_id'] == store_id]
        categories = store_menus['classified_category'].dropna().tolist()

        if categories:
            # 가장 많이 나온 카테고리 선택
            category_counts = Counter(categories)
            most_common_category = category_counts.most_common(1)[0][0]
            store_categories[store_id] = most_common_category
        else:
            # 카테고리가 없으면 기본값
            store_categories[store_id] = '아메리카노'

    return store_categories


def escape_sql_string(value):
    """SQL 문자열 이스케이프"""
    if pd.isna(value) or value == '' or value == 'nan':
        return 'NULL'

    value = str(value)
    # 작은따옴표 이스케이프
    value = value.replace("'", "''")
    # 백슬래시 이스케이프
    value = value.replace("\\", "\\\\")
    return f"'{value}'"


def format_value(value, column_type='string'):
    """컬럼 타입에 따른 값 포맷팅"""
    if pd.isna(value) or value == '' or str(value).lower() == 'nan':
        return 'NULL'

    if column_type == 'int':
        return str(int(float(value)))
    elif column_type == 'float':
        return str(float(value))
    elif column_type == 'bool':
        if str(value).lower() in ['true', '1', 'yes']:
            return 'TRUE'
        return 'FALSE'
    else:
        return escape_sql_string(value)


def generate_roasteries_sql(df):
    """roasteries 테이블 INSERT 문 생성"""
    lines = ["-- Roasteries", "INSERT INTO roasteries (id, name, logo_url, website_url) VALUES"]
    values = []

    for _, row in df.iterrows():
        val = f"({format_value(row['id'], 'int')}, {format_value(row['name'])}, {format_value(row['logo_url'])}, {format_value(row['website_url'])})"
        values.append(val)

    lines.append(",\n".join(values) + ";")
    return "\n".join(lines)


def generate_stores_sql(df, store_categories=None):
    """stores 테이블 INSERT 문 생성

    Args:
        df: stores DataFrame
        store_categories: 가게 ID -> 카테고리 매핑 딕셔너리
    """
    lines = ["-- Stores", "INSERT INTO stores (id, roastery_id, owner_id, name, description, address, latitude, longitude, phone_number, category, thumbnail_url, open_time, close_time, average_rating, review_count, visit_count, is_closed) VALUES"]
    values = []

    for _, row in df.iterrows():
        # 메뉴 기반 카테고리 사용 (없으면 기본값 '아메리카노')
        store_id = int(row['id'])
        category = store_categories.get(store_id, '아메리카노') if store_categories else row['category']

        val = f"({format_value(row['id'], 'int')}, {format_value(row['roastery_id'], 'int')}, {format_value(row['owner_id'], 'int') if pd.notna(row.get('owner_id')) else 'NULL'}, {format_value(row['name'])}, {format_value(row['description'])}, {format_value(row['address'])}, {format_value(row['latitude'], 'float')}, {format_value(row['longitude'], 'float')}, {format_value(row['phone_number'])}, {format_value(category)}, {format_value(row['thumbnail_url'])}, {format_value(row['open_time']) if pd.notna(row.get('open_time')) and row.get('open_time') != '' else 'NULL'}, {format_value(row['close_time']) if pd.notna(row.get('close_time')) and row.get('close_time') != '' else 'NULL'}, {format_value(row['average_rating'], 'float')}, {format_value(row['review_count'], 'int')}, {format_value(row['visit_count'], 'int')}, {format_value(row['is_closed'], 'bool')})"
        values.append(val)

    lines.append(",\n".join(values) + ";")
    return "\n".join(lines)


def generate_beans_sql(df):
    """beans 테이블 INSERT 문 생성"""
    lines = ["-- Beans", "INSERT INTO beans (id, roastery_id, name, country, farm, variety, processing_method, roasting_level) VALUES"]
    values = []

    for _, row in df.iterrows():
        val = f"({format_value(row['id'], 'int')}, {format_value(row['roastery_id'], 'int')}, {format_value(row['name'])}, {format_value(row['country'])}, {format_value(row['farm'])}, {format_value(row['variety'])}, {format_value(row['processing_method'])}, {format_value(row['roasting_level'])})"
        values.append(val)

    lines.append(",\n".join(values) + ";")
    return "\n".join(lines)


def generate_menus_sql(df):
    """menus 테이블 INSERT 문 생성"""
    lines = ["-- Menus", "INSERT INTO menus (id, store_id, name, description, price, category, image_url) VALUES"]
    values = []

    for _, row in df.iterrows():
        price = row['price']
        # price가 0이거나 비어있으면 0으로 설정
        if pd.isna(price) or price == '' or price == 0:
            price = 0

        val = f"({format_value(row['id'], 'int')}, {format_value(row['store_id'], 'int')}, {format_value(row['name'])}, {format_value(row['description'])}, {format_value(price, 'int')}, {format_value(row['category'])}, {format_value(row['image_url'])})"
        values.append(val)

    lines.append(",\n".join(values) + ";")
    return "\n".join(lines)


def generate_bean_flavor_notes_sql(df):
    """bean_flavor_notes 테이블 INSERT 문 생성"""
    lines = ["-- Bean Flavor Notes", "INSERT INTO bean_flavor_notes (bean_id, flavor_id) VALUES"]
    values = []

    for _, row in df.iterrows():
        val = f"({format_value(row['bean_id'], 'int')}, {format_value(row['flavor_id'], 'int')})"
        values.append(val)

    lines.append(",\n".join(values) + ";")
    return "\n".join(lines)


def generate_menu_bean_mappings_sql(df):
    """menu_bean_mappings 테이블 INSERT 문 생성"""
    lines = ["-- Menu Bean Mappings", "INSERT INTO menu_bean_mappings (id, menu_id, bean_id, is_blended) VALUES"]
    values = []

    for _, row in df.iterrows():
        val = f"({format_value(row['id'], 'int')}, {format_value(row['menu_id'], 'int')}, {format_value(row['bean_id'], 'int')}, {format_value(row['is_blended'], 'bool')})"
        values.append(val)

    lines.append(",\n".join(values) + ";")
    return "\n".join(lines)


def main():
    print("=== CSV to SQL 변환 시작 ===\n")

    # 출력 디렉토리 생성
    OUTPUT_DIR.mkdir(exist_ok=True)

    sql_parts = []
    sql_parts.append("-- Comeet Data Import SQL")
    sql_parts.append("-- Generated from data/final/*.csv")
    sql_parts.append("-- 외래키 의존성 순서: roasteries -> stores, beans -> menus -> bean_flavor_notes, menu_bean_mappings")
    sql_parts.append("")
    sql_parts.append("SET FOREIGN_KEY_CHECKS = 0;")
    sql_parts.append("")

    # 먼저 메뉴 데이터를 읽어서 가게별 카테고리 계산
    print("0. 메뉴 기반 가게 카테고리 계산 중...")
    menus_df = pd.read_csv(DATA_DIR / "menus.csv")
    store_categories = calculate_store_categories(menus_df)

    # 카테고리 분포 출력
    category_distribution = Counter(store_categories.values())
    print(f"   -> 카테고리 분포: {dict(category_distribution)}")
    print("")

    # 1. Roasteries
    print("1. roasteries.csv 처리 중...")
    roasteries_df = pd.read_csv(DATA_DIR / "roasteries.csv")
    sql_parts.append(generate_roasteries_sql(roasteries_df))
    sql_parts.append("")
    print(f"   -> {len(roasteries_df)}개 레코드")

    # 2. Stores (메뉴 기반 카테고리 적용)
    print("2. stores.csv 처리 중...")
    stores_df = pd.read_csv(DATA_DIR / "stores.csv")
    sql_parts.append(generate_stores_sql(stores_df, store_categories))
    sql_parts.append("")
    print(f"   -> {len(stores_df)}개 레코드")

    # 3. Beans
    print("3. beans.csv 처리 중...")
    beans_df = pd.read_csv(DATA_DIR / "beans.csv")
    sql_parts.append(generate_beans_sql(beans_df))
    sql_parts.append("")
    print(f"   -> {len(beans_df)}개 레코드")

    # 4. Menus (이미 위에서 읽었으므로 재사용)
    print("4. menus.csv 처리 중...")
    sql_parts.append(generate_menus_sql(menus_df))
    sql_parts.append("")
    print(f"   -> {len(menus_df)}개 레코드")

    # 5. Bean Flavor Notes
    print("5. bean_flavor_notes.csv 처리 중...")
    bean_flavor_notes_df = pd.read_csv(DATA_DIR / "bean_flavor_notes.csv")
    sql_parts.append(generate_bean_flavor_notes_sql(bean_flavor_notes_df))
    sql_parts.append("")
    print(f"   -> {len(bean_flavor_notes_df)}개 레코드")

    # 6. Menu Bean Mappings
    print("6. menu_bean_mappings.csv 처리 중...")
    menu_bean_mappings_df = pd.read_csv(DATA_DIR / "menu_bean_mappings.csv")
    sql_parts.append(generate_menu_bean_mappings_sql(menu_bean_mappings_df))
    sql_parts.append("")
    print(f"   -> {len(menu_bean_mappings_df)}개 레코드")

    sql_parts.append("SET FOREIGN_KEY_CHECKS = 1;")
    sql_parts.append("")
    sql_parts.append("-- Import complete!")

    # SQL 파일 저장
    output_path = OUTPUT_DIR / "data_import.sql"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(sql_parts))

    print(f"\n✓ SQL 파일 생성 완료: {output_path}")

    # 통계
    total_records = (
        len(roasteries_df) + len(stores_df) + len(beans_df) +
        len(menus_df) + len(bean_flavor_notes_df) + len(menu_bean_mappings_df)
    )
    print(f"✓ 총 {total_records}개 레코드")


if __name__ == "__main__":
    main()
