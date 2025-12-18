"""
메뉴 추출 테스트 스크립트 v2
- 더 안정적인 대기 로직
- 스크린샷 저장
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
import os


def setup_driver():
    options = Options()
    options.add_argument('--headless=new')  # 새로운 헤드리스 모드
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')  # 봇 감지 우회
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # 봇 감지 우회를 위한 JavaScript 실행
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        '''
    })

    driver.implicitly_wait(5)
    return driver


def test_single_cafe(driver, search_query, cafe_index=0):
    """단일 카페 메뉴 추출 테스트"""
    print(f"\n{'='*60}")
    print(f"검색어: {search_query}")
    print(f"카페 인덱스: {cafe_index}")
    print('='*60)

    # 1. 검색
    url = f"https://map.naver.com/p/search/{search_query}"
    print(f"URL: {url}")
    driver.get(url)
    time.sleep(4)

    # 스크린샷 저장
    os.makedirs("crawlers_v3/screenshots", exist_ok=True)
    driver.save_screenshot(f"crawlers_v3/screenshots/1_search_{search_query.replace(' ', '_')}.png")

    # 2. searchIframe 대기 및 전환
    print("\n--- searchIframe 전환 ---")
    try:
        wait = WebDriverWait(driver, 15)
        search_iframe = wait.until(EC.presence_of_element_located((By.ID, "searchIframe")))
        print(f"searchIframe 발견")
        driver.switch_to.frame(search_iframe)
        time.sleep(3)
        print(f"searchIframe 전환 성공")
    except Exception as e:
        print(f"searchIframe 전환 실패: {e}")
        driver.save_screenshot("crawlers_v3/screenshots/error_search_iframe.png")
        return

    # 현재 프레임에서 스크린샷
    driver.save_screenshot(f"crawlers_v3/screenshots/2_in_search_frame_{search_query.replace(' ', '_')}.png")

    # 3. 검색 결과 찾기
    print("\n--- 검색 결과 탐색 ---")
    selectors_to_try = [
        "li.UEzoS",
        "li[data-laim-exp-id]",
        "ul li",
        ".place_bluelink",
    ]

    place_items = []
    for selector in selectors_to_try:
        try:
            items = driver.find_elements(By.CSS_SELECTOR, selector)
            print(f"셀렉터 '{selector}': {len(items)}개")
            if items and len(items) > 0:
                place_items = items
                break
        except Exception as e:
            print(f"셀렉터 '{selector}' 오류: {e}")

    if not place_items:
        print("검색 결과를 찾을 수 없음")
        # HTML 저장
        with open("crawlers_v3/screenshots/search_html.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        driver.switch_to.default_content()
        return

    print(f"\n검색 결과 수: {len(place_items)}개")

    # 4. 첫 번째 결과 클릭
    if len(place_items) > cafe_index:
        try:
            item = place_items[cafe_index]

            # 카페 이름 링크를 찾아서 클릭 (span.TYaxT 또는 a 태그)
            click_target = None
            name_text = ""

            # 이름 요소 찾기
            for sel in ["span.TYaxT", "a.tzwk0", "a[href]", ".place_bluelink"]:
                try:
                    el = item.find_element(By.CSS_SELECTOR, sel)
                    if el.text.strip():
                        click_target = el
                        name_text = el.text.strip()
                        break
                except:
                    continue

            if click_target:
                print(f"선택된 카페: {name_text}")
                print(f"클릭 대상: {click_target.tag_name}")
            else:
                click_target = item
                print(f"선택된 카페: (이름 추출 실패, li 전체 클릭)")

            # 클릭 전 대기
            time.sleep(1)

            # JavaScript로 클릭
            driver.execute_script("arguments[0].click();", click_target)
            print("클릭 완료")
            time.sleep(4)  # 더 오래 대기

        except StaleElementReferenceException:
            print("StaleElementReferenceException - 재시도")
            time.sleep(2)
            place_items = driver.find_elements(By.CSS_SELECTOR, "li.UEzoS")
            if place_items:
                driver.execute_script("arguments[0].click();", place_items[cafe_index])
        except Exception as e:
            print(f"클릭 오류: {e}")
            driver.switch_to.default_content()
            return
    else:
        print("인덱스 범위 초과")
        driver.switch_to.default_content()
        return

    # default로 돌아가기
    driver.switch_to.default_content()
    time.sleep(3)
    driver.save_screenshot(f"crawlers_v3/screenshots/3_after_click_{search_query.replace(' ', '_')}.png")

    # 5. entryIframe 전환
    print("\n--- entryIframe 전환 ---")

    # 여러 방법으로 iframe 찾기 시도
    iframe_found = False
    iframe_selectors = [
        (By.ID, "entryIframe"),
        (By.CSS_SELECTOR, "iframe#entryIframe"),
        (By.CSS_SELECTOR, "iframe[src*='place']"),
        (By.CSS_SELECTOR, "iframe[title*='Place']"),
    ]

    # 현재 페이지의 모든 iframe 확인
    all_iframes = driver.find_elements(By.TAG_NAME, "iframe")
    print(f"페이지 내 iframe 수: {len(all_iframes)}")
    for i, iframe in enumerate(all_iframes):
        iframe_id = iframe.get_attribute("id")
        iframe_src = iframe.get_attribute("src")
        print(f"  iframe {i}: id='{iframe_id}', src='{iframe_src[:50] if iframe_src else 'None'}...'")

    for by, selector in iframe_selectors:
        try:
            wait = WebDriverWait(driver, 10)
            entry_iframe = wait.until(EC.presence_of_element_located((by, selector)))
            print(f"entryIframe 발견: {selector}")
            driver.switch_to.frame(entry_iframe)
            iframe_found = True
            time.sleep(3)
            print("entryIframe 전환 성공")
            break
        except Exception as e:
            print(f"  {selector} 실패")
            continue

    if not iframe_found:
        print("entryIframe 전환 실패 - 모든 방법 시도 완료")
        driver.save_screenshot("crawlers_v3/screenshots/error_entry_iframe.png")
        with open("crawlers_v3/screenshots/main_html.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        return

    driver.save_screenshot(f"crawlers_v3/screenshots/4_in_entry_frame_{search_query.replace(' ', '_')}.png")

    # 6. APOLLO_STATE 확인
    print("\n--- APOLLO_STATE 분석 ---")
    try:
        data = driver.execute_script("return window.__APOLLO_STATE__")
        if data:
            print(f"APOLLO_STATE 키 수: {len(data)}")

            # 가게 정보 찾기
            for key, value in data.items():
                if 'PlaceDetailBase' in key:
                    print(f"\n가게 정보:")
                    print(f"  이름: {value.get('name')}")
                    print(f"  주소: {value.get('roadAddress')}")
                    print(f"  카테고리: {value.get('category')}")
                    break

            # 메뉴 관련 키 찾기
            menu_keys = [k for k in data.keys() if 'menu' in k.lower() or 'Menu' in k]
            print(f"\n메뉴 관련 키: {len(menu_keys)}개")
            for mk in menu_keys[:5]:
                print(f"  - {mk}: {str(data[mk])[:100]}")

            # JSON으로 저장
            with open("crawlers_v3/screenshots/apollo_state.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
                print("\nAPOLLO_STATE JSON 저장됨")

        else:
            print("APOLLO_STATE 없음")
    except Exception as e:
        print(f"APOLLO_STATE 오류: {e}")

    # 7. 메뉴 탭 클릭
    print("\n--- 메뉴 탭 클릭 시도 ---")
    menu_clicked = False

    # 탭 목록 먼저 확인
    try:
        tabs = driver.find_elements(By.CSS_SELECTOR, "a[role='tab'], div[role='tab'], span.veBoZ")
        print(f"탭 수: {len(tabs)}개")
        for tab in tabs:
            print(f"  - '{tab.text}'")
    except:
        pass

    menu_tab_selectors = [
        "//span[contains(text(), '메뉴')]/..",
        "//a[contains(text(), '메뉴')]",
        "//span[text()='메뉴']/..",
        "//*[contains(@class, 'tab')]//*[contains(text(), '메뉴')]",
    ]

    for xpath in menu_tab_selectors:
        try:
            menu_tab = driver.find_element(By.XPATH, xpath)
            print(f"메뉴 탭 발견: {xpath}")
            driver.execute_script("arguments[0].click();", menu_tab)
            menu_clicked = True
            time.sleep(3)
            break
        except Exception as e:
            continue

    if menu_clicked:
        print("메뉴 탭 클릭 성공")
        driver.save_screenshot(f"crawlers_v3/screenshots/5_menu_tab_{search_query.replace(' ', '_')}.png")
    else:
        print("메뉴 탭을 찾지 못함")

    # 8. 메뉴 페이지에서 DOM 분석
    print("\n--- 메뉴 DOM 분석 ---")

    menu_selectors = [
        "li[class*='MenuContent__order_list_item']",
        "li[class*='order_list_item']",
        "div[class*='menu_item']",
        ".place_section_content li",
        "ul li",
    ]

    for selector in menu_selectors:
        try:
            items = driver.find_elements(By.CSS_SELECTOR, selector)
            if items:
                print(f"\n셀렉터 '{selector}': {len(items)}개")
                for item in items[:5]:
                    text = item.text.replace('\n', ' | ')[:150]
                    print(f"  - {text}")
        except:
            pass

    # 9. HTML 저장
    with open("crawlers_v3/screenshots/menu_page.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print("\n메뉴 페이지 HTML 저장됨")

    driver.switch_to.default_content()
    print("\n테스트 완료")


def main():
    driver = setup_driver()

    try:
        # 더 일반적인 검색어로 테스트
        test_single_cafe(driver, "성수 카페", cafe_index=0)

    finally:
        driver.quit()
        print("\n드라이버 종료")


if __name__ == '__main__':
    main()
