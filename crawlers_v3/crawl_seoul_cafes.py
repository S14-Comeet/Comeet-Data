"""
서울 스페셜티 카페 크롤러 v3
- 개선된 메뉴 추출 로직 (APOLLO_STATE에서 Menu:* 패턴)
- 봇 감지 우회 설정
- 블랙리스트 방식 메뉴 필터링 (비커피 메뉴만 제외, 나머지는 모두 포함)
- 커피 메뉴가 1개 이상 있는 가게만 저장
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
import time
import json
import re
import csv
import os
import random
from datetime import datetime

# 검색어 목록 (서울 전역)
SEARCH_QUERIES = [
    # 광역
    "서울 스페셜티 커피",
    "서울 로스터리 카페",
    "서울 핸드드립 카페",

    # 강남권
    "강남 스페셜티", "강남 로스터리", "역삼 스페셜티", "압구정 로스터리",
    "청담 스페셜티", "신사동 로스터리", "삼성동 스페셜티",
    "서초 스페셜티", "양재 로스터리", "반포 스페셜티",
    "송파 스페셜티", "잠실 로스터리",

    # 마포/용산권
    "합정 스페셜티", "합정 로스터리", "망원 스페셜티", "연남동 로스터리",
    "홍대 스페셜티", "상수 로스터리", "연희동 스페셜티",
    "용산 스페셜티", "이태원 로스터리", "한남동 스페셜티",

    # 성동/광진
    "성수 스페셜티", "성수 로스터리", "뚝섬 스페셜티", "서울숲 로스터리",
    "건대 스페셜티", "자양동 로스터리",

    # 종로/중구
    "종로 스페셜티", "익선동 로스터리", "서촌 스페셜티", "북촌 로스터리",
    "을지로 스페셜티", "명동 로스터리",

    # 기타
    "영등포 스페셜티", "문래 로스터리", "여의도 스페셜티",
    "관악구 스페셜티", "샤로수길 로스터리",
    "성북구 스페셜티", "혜화 로스터리",
    "노원 스페셜티", "강동 로스터리",
]

# ============ 메뉴 필터링 설정 (블랙리스트 방식) ============
# 비커피 메뉴만 제외하고, 나머지는 모두 커피 메뉴로 포함

# 제외 키워드 (이 키워드가 포함된 메뉴는 제외)
EXCLUDE_KEYWORDS = [
    # 디저트/빵/베이커리
    '케이크', '케잌', '쿠키', '스콘', '크루아상', '크로와상', '빵', '베이글',
    '마카롱', '마들렌', '휘낭시에', '브라우니', '타르트', '파이', '푸딩',
    '도넛', '도너츠', '와플', '크로플', '팬케이크', '번', '롤', '까눌레',
    '몽블랑', '밀푀유', '슈크림', '에클레어', '티라미수', '무스', '바스크',
    '데니쉬', '페이스트리', '소금빵', '앙버터', '크림빵', '단팥빵',
    '카스테라', '시폰', '파운드', '생크림', '치즈케이크', '휘핑', '크런치',
    '초코볼', '초콜릿볼', '호두파이', '애플파이', '에그타르트', '프레첼',
    '츄러스', '츄로스', '붕어빵', '호떡', '떡', '인절미', '경단', '약과', '한과',

    # 음식/식사류
    '샌드위치', '토스트', '버거', '햄버거', '파스타', '피자', '리조또',
    '샐러드', '수프', '스프', '나초', '핫도그', '타코', '부리또',
    '브런치', '플레이트', '볼', '런치', '밥', '덮밥', '김밥', '죽',
    '오믈렛', '에그', '베이컨', '소시지', '감자튀김', '프렌치프라이',
    '치킨', '너겟', '윙', '스테이크', '그릴', '구이',

    # 빙수/아이스크림/요거트
    '빙수', '아이스크림', '젤라또', '젤라토', '소르베', '셔벗', '요거트',
    '아이스박스', '파르페', '선데', '소프트크림', '밀크셰이크', '쉐이크',

    # 차 (Tea) 종류
    '녹차', '말차', '맛차', '홍차', '얼그레이', '캐모마일', '허브티',
    '루이보스', '자스민', '페퍼민트', '레몬차', '자몽차', '유자차',
    '생강차', '대추차', '쌍화차', '한방차', '호지차', '현미차',
    '보리차', '옥수수차', '둥굴레', '히비스커스', '라벤더티', '민트티',
    '로즈티', '국화차', '매실차', '오미자', '모과차', '꿀차', '율무차',
    '밀크티', '버블티', '타로', '타피오카', '공차', '펄',
    '아이스티', '레몬티', '피치티', '애플티',

    # 과일 음료/에이드/스무디
    '에이드', '스무디', '쥬스', '주스', '프레쉬', '프레시', '착즙',
    '복숭아', '딸기', '망고', '청포도', '자몽', '레몬', '라임', '오렌지',
    '블루베리', '라즈베리', '체리', '수박', '멜론', '키위', '패션후르츠',
    '사과', '배', '바나나', '포도', '파인애플', '코코넛', '리치', '용과',
    '크랜베리', '아사이', '석류', '토마토', '당근', '샐러리', '케일',
    '그린', '레드', '오렌지', '옐로우', '퍼플',  # 과일/야채 스무디 색상

    # 초콜릿/코코아 음료
    '초코', '초콜릿', '핫초코', '코코아', '가나슈',

    # 주류
    '하이볼', '맥주', '와인', '칵테일', '위스키', '럼', '진',
    '소주', '막걸리', '사케', '모히또', '상그리아',

    # 상품/굿즈
    '굿즈', '텀블러', '머그컵', '원두', '드립백', '캡슐',
    '패키지', '기프트', '선물세트', '박스', '보틀', '컵',

    # 세트/구성 메뉴
    '세트', '+', '&', '콤보', '페어링',

    # 기타 비커피
    '우유', '밀크', '두유', '아몬드밀크', '오트밀크', '귀리',
    '꿀', '시럽', '휘핑크림', '생수', '탄산수', '토닉워터',
]

# 가격 범위 (원)
MIN_COFFEE_PRICE = 2000
MAX_COFFEE_PRICE = 15000

# ============ 결과 저장 경로 ============
OUTPUT_DIR = "crawlers_v3/data"
STORES_FILE = "stores.csv"
MENUS_FILE = "menus.csv"
CRAWL_LOG_FILE = "crawl_log.json"

# 최대 수집 개수
MAX_STORES = 300

# 디버깅 옵션
DEBUG_MODE = True  # 디버깅 정보 출력 여부


def setup_driver():
    """봇 감지 우회 설정이 포함된 Chrome 드라이버"""
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # 봇 감지 우회
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        '''
    })

    driver.implicitly_wait(5)
    return driver


def search_naver_map(driver, query, retry_count=0):
    """네이버 지도에서 검색"""
    search_url = f"https://map.naver.com/p/search/{query}"
    driver.get(search_url)

    # 랜덤 대기 시간 (봇 감지 우회)
    wait_time = 4 + random.uniform(1, 3)
    time.sleep(wait_time)

    # 페이지가 제대로 로드되었는지 확인
    try:
        # searchIframe이 있는지 확인 (최대 10초 대기)
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.ID, "searchIframe")))
    except TimeoutException:
        if retry_count < 2:
            if DEBUG_MODE:
                print(f"  [DEBUG] 페이지 로딩 실패, 재시도 {retry_count + 1}/2")
            time.sleep(3)
            return search_naver_map(driver, query, retry_count + 1)

    return driver


def get_search_results(driver, max_results=15):
    """검색 결과 목록 가져오기"""
    results = []

    try:
        wait = WebDriverWait(driver, 15)
        search_iframe = wait.until(EC.presence_of_element_located((By.ID, "searchIframe")))
        driver.switch_to.frame(search_iframe)
        time.sleep(4)  # 대기 시간 증가

        # 검색 결과 찾기 - 여러 셀렉터 시도
        place_items = []
        selectors = [
            "li.UEzoS",           # 기본 셀렉터
            "li[data-laim-exp-id]",  # 대체 셀렉터 1
            "ul.Ryr1F li",        # 대체 셀렉터 2
            "div.Ryr1F li",       # 대체 셀렉터 3
        ]

        for selector in selectors:
            place_items = driver.find_elements(By.CSS_SELECTOR, selector)
            if place_items:
                break

        # 여전히 없으면 스크롤해서 로딩 시도
        if not place_items:
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(2)
            for selector in selectors:
                place_items = driver.find_elements(By.CSS_SELECTOR, selector)
                if place_items:
                    break

        # 디버깅: 결과가 없을 때 페이지 소스 일부 출력
        if not place_items and DEBUG_MODE:
            try:
                html = driver.page_source[:2000]
                # 검색 결과 관련 키워드 확인
                if "검색 결과가 없습니다" in html or "결과가 없습니다" in html:
                    print(f"  [DEBUG] 네이버 지도에서 '검색 결과 없음' 메시지 발견")
                else:
                    # 주요 클래스 찾기
                    classes = re.findall(r'class="([^"]*)"', html[:1500])
                    unique_classes = list(set(classes))[:10]
                    print(f"  [DEBUG] 발견된 주요 클래스: {unique_classes}")
            except:
                pass

        for i, item in enumerate(place_items[:max_results]):
            try:
                # 이름 찾기 - 여러 셀렉터 시도
                name = ""
                name_selectors = ["span.TYaxT", "span.YwYLL", "a.tzwk0", "span.place_bluelink"]
                for ns in name_selectors:
                    try:
                        name_el = item.find_element(By.CSS_SELECTOR, ns)
                        name = name_el.text.strip()
                        if name:
                            break
                    except:
                        continue

                if name:
                    results.append({
                        'index': i,
                        'name': name,
                    })
            except:
                pass

        driver.switch_to.default_content()

    except TimeoutException:
        print(f"  [DEBUG] searchIframe 로딩 타임아웃 - 검색 결과 없거나 다른 UI")
        driver.switch_to.default_content()
    except Exception as e:
        print(f"  [DEBUG] 검색 결과 가져오기 오류: {type(e).__name__}: {e}")
        driver.switch_to.default_content()

    return results


def extract_store_from_apollo_state(data):
    """APOLLO_STATE에서 가게 정보 추출"""
    store_info = {}

    if not data:
        return store_info

    # PlaceDetailBase에서 정보 추출
    for key, value in data.items():
        if key.startswith("PlaceDetailBase:"):
            store_info['name'] = value.get('name')
            store_info['category'] = value.get('category')
            store_info['address'] = value.get('roadAddress') or value.get('address') or ""
            store_info['phone'] = value.get('virtualPhone') or value.get('phone') or ""

            if value.get('coordinate'):
                store_info['latitude'] = value['coordinate'].get('y')
                store_info['longitude'] = value['coordinate'].get('x')

            break

    # 설명 추출 (ROOT_QUERY에서)
    root_query = data.get('ROOT_QUERY', {})
    for rk, rv in root_query.items():
        if rk.startswith("placeDetail({"):
            if isinstance(rv, dict):
                for dk, dv in rv.items():
                    if dk.startswith("description({"):
                        store_info['description'] = dv or ""
                        break
            break

    return store_info


def extract_menus_from_apollo_state(data):
    """APOLLO_STATE에서 메뉴 정보 추출 (Menu:* 패턴)"""
    menus = []

    if not data:
        return menus

    for key, value in data.items():
        if key.startswith("Menu:") and isinstance(value, dict):
            name = value.get('name', '')
            price_str = value.get('price', '0')
            desc = value.get('description', '')

            if name:
                # 가격 처리
                price = 0
                if price_str:
                    try:
                        price = int(re.sub(r'[^\d]', '', str(price_str)))
                    except:
                        price = 0

                menus.append({
                    'name': name.strip(),
                    'price': price,
                    'description': desc.strip() if desc else "",
                })

    return menus


def is_coffee_menu(name, description="", price=0):
    """
    커피 메뉴인지 판별 (블랙리스트 방식)
    - 비커피 메뉴(디저트, 차, 음식 등)만 제외
    - 나머지는 모두 커피 메뉴로 포함
    """
    if not name:
        return False

    text = (name + " " + description).lower()

    # 1. 제외 키워드 체크 - 비커피 메뉴는 제외
    for keyword in EXCLUDE_KEYWORDS:
        if keyword.lower() in text:
            return False

    # 2. 가격 체크 - 적정 가격 범위 확인
    if price > 0:
        if price < MIN_COFFEE_PRICE or price > MAX_COFFEE_PRICE:
            return False

    # 3. 제외되지 않은 모든 메뉴는 커피 메뉴로 간주
    return True


def get_cafe_detail_and_menus(driver, index):
    """카페 상세 정보와 메뉴 가져오기"""
    store_info = {}
    menus = []

    try:
        # 1. searchIframe으로 전환
        wait = WebDriverWait(driver, 15)
        search_iframe = wait.until(EC.presence_of_element_located((By.ID, "searchIframe")))
        driver.switch_to.frame(search_iframe)
        time.sleep(3)  # 대기 시간 증가

        # 2. 카페 클릭 - 여러 셀렉터 시도
        place_items = []
        selectors = [
            "li.UEzoS",
            "li[data-laim-exp-id]",
            "ul.Ryr1F li",
            "div.Ryr1F li",
        ]

        for selector in selectors:
            place_items = driver.find_elements(By.CSS_SELECTOR, selector)
            if place_items:
                break

        if len(place_items) <= index:
            if DEBUG_MODE:
                print(f"(검색 결과 부족: {len(place_items)}개)", end=" ")
            driver.switch_to.default_content()
            return store_info, menus

        item = place_items[index]

        # 이름 요소 찾아서 클릭
        click_target = None
        name_selectors = ["span.TYaxT", "span.YwYLL", "a.tzwk0", "a[href]"]
        for sel in name_selectors:
            try:
                el = item.find_element(By.CSS_SELECTOR, sel)
                if el.text.strip():
                    click_target = el
                    break
            except:
                continue

        if not click_target:
            click_target = item

        driver.execute_script("arguments[0].click();", click_target)
        driver.switch_to.default_content()
        time.sleep(4 + random.uniform(1, 2))  # 랜덤 대기

        # 3. entryIframe으로 전환
        try:
            wait = WebDriverWait(driver, 15)
            entry_iframe = wait.until(EC.presence_of_element_located((By.ID, "entryIframe")))
            driver.switch_to.frame(entry_iframe)
            time.sleep(3)
        except TimeoutException:
            if DEBUG_MODE:
                print("(entryIframe 타임아웃)", end=" ")
            driver.switch_to.default_content()
            return store_info, menus

        # 4. APOLLO_STATE에서 정보 추출
        try:
            apollo_data = driver.execute_script("return window.__APOLLO_STATE__")
            if apollo_data:
                store_info = extract_store_from_apollo_state(apollo_data)
            else:
                if DEBUG_MODE:
                    print("(APOLLO_STATE 없음)", end=" ")
        except Exception as e:
            if DEBUG_MODE:
                print(f"(APOLLO 오류: {e})", end=" ")

        # 5. 메뉴 탭 클릭
        menu_clicked = False
        menu_xpaths = [
            "//span[contains(text(), '메뉴')]/..",
            "//a[contains(text(), '메뉴')]",
            "//span[text()='메뉴']/..",
        ]

        for xpath in menu_xpaths:
            try:
                menu_tab = driver.find_element(By.XPATH, xpath)
                driver.execute_script("arguments[0].click();", menu_tab)
                menu_clicked = True
                time.sleep(3)
                break
            except:
                continue

        # 6. 메뉴 추출
        if menu_clicked:
            try:
                apollo_data = driver.execute_script("return window.__APOLLO_STATE__")
                all_menus = extract_menus_from_apollo_state(apollo_data)

                # 커피 메뉴만 필터링
                for menu in all_menus:
                    if is_coffee_menu(menu['name'], menu['description'], menu['price']):
                        menus.append(menu)
            except:
                pass

        driver.switch_to.default_content()

    except Exception as e:
        print(f"    오류: {e}")
        try:
            driver.switch_to.default_content()
        except:
            pass

    return store_info, menus


def is_target_area(address):
    """서울 지역인지 확인"""
    if not address:
        return False
    return "서울" in address


def save_results(stores, all_menus):
    """결과를 CSV로 저장"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # stores.csv
    stores_path = os.path.join(OUTPUT_DIR, STORES_FILE)
    with open(stores_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'id', 'roastery_id', 'owner_id', 'name', 'description', 'address',
            'latitude', 'longitude', 'phone_number', 'category',
            'thumbnail_url', 'open_time', 'close_time'
        ])

        for i, store in enumerate(stores, 1):
            writer.writerow([
                i, 1, '',
                store.get('name', ''),
                store.get('description', ''),
                store.get('address', ''),
                store.get('latitude', ''),
                store.get('longitude', ''),
                store.get('phone', ''),
                store.get('category', ''),
                '', '', ''
            ])

    print(f"\nstores.csv 저장: {len(stores)}개")

    # menus.csv
    menus_path = os.path.join(OUTPUT_DIR, MENUS_FILE)
    with open(menus_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'store_id', 'name', 'description', 'price', 'category', 'image_url'])

        menu_id = 1
        for store_id, menus in enumerate(all_menus, 1):
            for menu in menus:
                writer.writerow([
                    menu_id, store_id,
                    menu.get('name', ''),
                    menu.get('description', ''),
                    menu.get('price', 0),
                    '', ''
                ])
                menu_id += 1

    print(f"menus.csv 저장: {menu_id - 1}개")


def main():
    print("=" * 60)
    print("서울 스페셜티 카페 크롤러 v3")
    print(f"검색어: {len(SEARCH_QUERIES)}개")
    print(f"목표: 커피 메뉴가 있는 카페 {MAX_STORES}개")
    print("=" * 60)

    driver = setup_driver()

    all_stores = {}
    crawl_log = {
        'start_time': datetime.now().isoformat(),
        'queries': [],
        'errors': [],
        'skipped_no_menu': 0,
    }

    try:
        for query_idx, query in enumerate(SEARCH_QUERIES):
            if len(all_stores) >= MAX_STORES:
                print(f"\n목표 수량({MAX_STORES}개) 달성!")
                break

            print(f"\n[{query_idx + 1}/{len(SEARCH_QUERIES)}] 검색: {query}")

            query_log = {'query': query, 'found': 0, 'added': 0, 'skipped': 0}

            try:
                search_naver_map(driver, query)
                results = get_search_results(driver, max_results=10)
                query_log['found'] = len(results)
                print(f"  검색 결과: {len(results)}개")

                for i, result in enumerate(results):
                    if len(all_stores) >= MAX_STORES:
                        break

                    print(f"    [{i + 1}] {result['name'][:15]}...", end=" ")

                    # 검색 페이지로 다시 이동 (충분한 대기 시간)
                    search_naver_map(driver, query)
                    time.sleep(2 + random.uniform(1, 2))

                    store_info, menus = get_cafe_detail_and_menus(driver, i)

                    if not store_info.get('name'):
                        print("정보 없음")
                        continue

                    address = store_info.get('address', '')

                    if not is_target_area(address):
                        print("서울 외 지역")
                        continue

                    if address in all_stores:
                        print("중복")
                        continue

                    # 핵심: 커피 메뉴가 있어야 저장
                    if not menus:
                        print("커피 메뉴 없음 (스킵)")
                        query_log['skipped'] += 1
                        crawl_log['skipped_no_menu'] += 1
                        continue

                    all_stores[address] = {
                        'store': store_info,
                        'menus': menus,
                    }
                    query_log['added'] += 1
                    print(f"저장! (메뉴 {len(menus)}개) [누적 {len(all_stores)}개]")

                    time.sleep(2 + random.uniform(1, 3))

            except Exception as e:
                print(f"  검색 오류: {e}")
                crawl_log['errors'].append({'query': query, 'error': str(e)})

            crawl_log['queries'].append(query_log)
            # 검색 간 랜덤 대기 (봇 감지 우회)
            time.sleep(3 + random.uniform(2, 5))

    finally:
        driver.quit()

    # 결과 저장
    print("\n" + "=" * 60)
    print("크롤링 완료!")
    print(f"총 수집 카페: {len(all_stores)}개")
    print(f"메뉴 없어서 스킵: {crawl_log['skipped_no_menu']}개")
    print("=" * 60)

    stores = [v['store'] for v in all_stores.values()]
    all_menus_list = [v['menus'] for v in all_stores.values()]

    save_results(stores, all_menus_list)

    # 로그 저장
    crawl_log['end_time'] = datetime.now().isoformat()
    crawl_log['total_stores'] = len(stores)
    crawl_log['total_menus'] = sum(len(m) for m in all_menus_list)

    log_path = os.path.join(OUTPUT_DIR, CRAWL_LOG_FILE)
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(crawl_log, f, ensure_ascii=False, indent=2)

    print(f"\n로그: {log_path}")

    # 샘플 출력
    print("\n=== 수집된 카페 샘플 ===")
    for i, (addr, data) in enumerate(list(all_stores.items())[:5], 1):
        store = data['store']
        menus = data['menus']
        print(f"{i}. {store.get('name')} ({len(menus)}개 메뉴)")
        for menu in menus[:3]:
            print(f"   - {menu.get('name')}: {menu.get('price')}원")


if __name__ == '__main__':
    main()
