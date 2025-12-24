# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

서울 스페셜티 카페 데이터 파이프라인. 네이버 지도 크롤링 + LLM 기반 원두 데이터 전처리 + SQL 생성.

**Data:** 231 roasteries, 246 stores, 1,000 beans, 1,355 menus, 4,823 flavor notes

## Commands

### Run scripts (in order)
```bash
python scripts/1_crawl_cafes.py      # Naver Map crawling
python scripts/2_process_beans.py    # Bean CSV processing (requires OPENAI_API_KEY)
python scripts/3_preprocess_for_db.py
python scripts/4_map_menu_beans.py
python scripts/5_generate_sql.py
python scripts/6_import_bean_scores.py  # Optional: recommendation scores
```

### DB Import
```bash
mysql -u <user> -p <db> < sql/schema.sql
mysql -u <user> -p <db> < sql/flavor_prod.sql
mysql -u <user> -p <db> < sql/data_import.sql
```

### Dependencies
```bash
pip install selenium webdriver_manager pandas langchain langchain-openai
```

## Architecture

### Data Flow
```
[Naver Map]                     [Kaggle Dataset]
     ↓                               ↓
1_crawl_cafes.py             data/raw/coffee_clean.csv
     ↓                               ↓
data/raw/stores.csv,         2_process_beans.py
         menus.csv                   ↓
     ↓                               ↓
     └───────────────┬───────────────┘
                     ↓
          3_preprocess_for_db.py
                     ↓
          data/final/roasteries.csv, stores.csv, beans.csv
                     ↓
          4_map_menu_beans.py
                     ↓
          data/final/menu_bean_mappings.csv
                     ↓
          5_generate_sql.py
                     ↓
          sql/data_import.sql
```

### Key Scripts

| Script | Purpose |
| --- | --- |
| `1_crawl_cafes.py` | Selenium crawler for Naver Map. Blacklist filtering for non-coffee items. |
| `2_process_beans.py` | LLM-based flavor extraction from coffee_clean.csv → SCA Flavor Wheel mapping |
| `4_map_menu_beans.py` | Auto-mapping menus to beans by country/origin keywords |
| `5_generate_sql.py` | CSV → SQL. Auto-classifies menu categories (Java enum) |

### Menu Category Classification
Priority order: FLAT_WHITE → CAPPUCCINO → COLD_BREW → HAND_DRIP → ESPRESSO → AMERICANO → LATTE

### Menu-Bean Mapping Strategy
1. Extract country from menu name → map to representative bean
2. Extract country from store description → map to all menus in store
3. Uses `COUNTRY_BEANS` dict with default and keyword-specific bean IDs

## Database Schema

Key tables in `sql/schema.sql`:
- `roasteries`: id=1 is Admin Roastery for unattributed beans
- `stores`: FK to roasteries
- `beans`: country, variety, processing_method, roasting_level
- `menus`: category enum (HAND_DRIP, ESPRESSO, AMERICANO, LATTE, CAPPUCCINO, FLAT_WHITE, COLD_BREW)
- `flavors`: 3-level hierarchy based on SCA Flavor Wheel

## Recommendation System

See `docs/recommendation-system-design.md`:
- `bean_scores`: normalized sensory attributes for vector search
- `user_preferences`: onboarding results
- Hard filter: roast level, disliked tags
- Soft scoring: acidity/body/sweetness similarity + liked tags bonus
