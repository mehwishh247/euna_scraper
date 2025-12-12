import asyncio
import os
import json
from pathlib import Path
from random import randint, uniform
from cleaner import clean_all_opportunities
from db import init_db, insert_opportunities
from utils import deduplicate_opportunities
_processing_lock = asyncio.Lock()

from pydoll.browser import tab as Tab
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.decorators import retry
from pydoll.constants import By
from pydoll.exceptions import WaitElementTimeout, NetworkError, ElementNotFound, TimeoutException
from dotenv import load_dotenv
import logging
from utils import configure_logging

load_dotenv()

ROOT = Path().cwd()

EMAIL = os.getenv('EMAIL')
PASSWORD = os.getenv('PASSWORD')
BASE_URL = 'https://vendor.bonfirehub.com/'

PROXIES = [
    'http://103.157.200.126:3128',
    'http://103.253.18.6:8080',
    'http://103.152.116.82:8080',
    'http://103.125.179.6:8080',
    'http://103.205.178.227:8080',
    'http://103.248.222.0:90',
    'http://103.66.149.194:8080',
    'http://202.69.38.42:5678',
    'http://103.155.62.141:8081',
    'http://110.38.226.139:8080',
    'http://202.154.241.199:808',
]

def get_proxy():
    global PROXIES
    proxy = PROXIES.pop(0)
    PROXIES.append(proxy)

    return proxy

# --- AGENCY PREFIXES REQUIRED ---
AGENCY_PREFIXES = ["D", "G", "J", "L"]
AGENCIES_PER_PREFIX = 5

async def login(tab):
    print('login')
    goto_login = await tab.find(tag_name='a', class_name='MuiButtonBase-root')
    await goto_login.click(
        x_offset=randint(-2,2),
        y_offset=randint(-2,2)
    )
    await asyncio.sleep(uniform(3.0,6.5))
    email = await tab.find(id="input-email")
    await email.click(
        x_offset=randint(-3, 5),
        y_offset=randint(-5, 2)
    )
    await asyncio.sleep(1.0)

    await email.type_text(EMAIL, humanize=True)

    continue_button = await tab.find(tag_name="button")
    await continue_button.click(
        x_offset=randint(-1, 2),
        y_offset=randint(1, 3)
    )
    await asyncio.sleep(6)

    password = await tab.find(id="input-password")
    await password.click(
        x_offset=randint(-3, 5),
        y_offset=randint(-5, 2)
    )
    password.type_text(PASSWORD, humanize=True)

    continue_button = await tab.find(tag_name="button")
    await continue_button.click(
        x_offset=randint(-1, 2),
        y_offset=randint(1, 3)
    )
    await asyncio.sleep(uniform(3,5))

    try:
        alert_p = await tab.find(
            tag_name='p',
            role='alert',
            raise_exec=False
        )
        if alert_p is not None:
            logging.warning(f"Login failed (alert found after password). Waiting 30s for possible manual correction or retry...")
            await asyncio.sleep(30)
    except ElementNotFound:
        pass
    await asyncio.sleep(uniform(2.0,4.0))

async def navigate_agency_search_tab(agency_tab, browser, on_agency_found):
    """Navigate agency search pages, find matching agencies (D/G/J/L), call callback immediately for each."""
    selected = {p: 0 for p in AGENCY_PREFIXES}
    seen_names = set()
    page_idx = 1

    items_list = await agency_tab.find(tag_name='div', class_name='css-1ks2a1h')
    await items_list.click()

    items_on_page = await agency_tab.find(tag_name='li', class_name='css-1rfvp8v', data_value="80")
    await items_on_page.click()
    await asyncio.sleep(2.5)
    
    while True:
        cards = await agency_tab.find(tag_name='div', class_name='css-cfm4ee', find_all=True)
        logging.info(f"[Page {page_idx}] Found {len(cards)} agency card elements")
        
        for card in cards:
            try:
                name_p = await card.find(tag_name='p', class_name='css-prt0s1')
                name = str(await name_p.text).strip()

                prefix = next((p for p in AGENCY_PREFIXES if name.upper().startswith(p)), None)
                
                if not prefix:
                    continue 
                    
                if name in seen_names:
                    continue
                    
                if selected[prefix] >= AGENCIES_PER_PREFIX:
                    logging.info(f"Skipping {name} ({prefix}): Already have {selected[prefix]}/5")
                    continue
                
                seen_names.add(name)
                logging.info(f"Found target: {name} ({prefix}) - Clicking card now...")
                
                try:
                    await card.click(
                        x_offset=randint(-3, 5),
                        y_offset=randint(-4, 4)
                    )
                    await asyncio.sleep(uniform(3.5, 6.0))

                except Exception as e:
                    logging.error(f"Failed to click card for {name}: {e}")
                    continue

                tabs = await browser.get_opened_tabs()
                agency_page_tab = tabs[-1]

                await asyncio.sleep(uniform(1.2, 2.2))
                
                region_span = await agency_tab.find(tag_name='span', class_name='css-1l59ypq', raise_exc=False)
                region = str(await region_span.text).strip() if region_span else None
                
                agency_obj = {
                    'name': name,
                    'agency_tab': agency_page_tab
                }

                await _processing_lock.acquire()
                try:
                    open_opps, past_opps = await scrape_agency_page(browser, agency_page_tab, agency_obj)

                    with open(ROOT / 'data' / 'open_opportunities_raw.json', 'a+') as f:
                        json.dump({name: open_opps}, f, indent=2)

                    with open(ROOT / 'data' / 'past_opportunities_raw.json', 'a+') as f:
                        json.dump({name: past_opps}, f, indent=2)
                    
                    # has_open = await on_agency_found(agency_obj)
                    if open_opps:
                        selected[prefix] += 1

                        logging.info(f"Selected {name} ({prefix}): {selected[prefix]}/5. Total: {sum(selected.values())}/20")
                except Exception as e:
                    logging.error(f"Error scraping {name}: {e}")
                finally:
                        await agency_page_tab.close()
                        _processing_lock.release()

                if all(selected[p] == AGENCIES_PER_PREFIX for p in AGENCY_PREFIXES):
                    logging.info(f"✓✓✓ ALL QUOTAS MET! {selected}. STOPPING NOW.")
                    return
            except Exception as e:
                logging.warning(f"Error parsing agency card: {e}")
                continue
        
        if all(selected[p] == AGENCIES_PER_PREFIX for p in AGENCY_PREFIXES):
            logging.info(f"All quotas met after processing page {page_idx}: {selected}")
            break
            
        try:
            paginator_p = await agency_tab.find(tag_name='p', class_name='css-ghev09')
            paginator_text = str(await paginator_p.text).strip()
            parts = paginator_text.split()
            last_entry = int(parts[3])
            total_entries = int(parts[-1])
            if last_entry == total_entries:
                logging.info(f"Reached last page (entry {last_entry} == total {total_entries}). Stopping pagination.")
                break
        except Exception as e:
            logging.warning(f"Could not parse page footer for pagination: {e}")
            break
            
        try:
            next_btn = await agency_tab.find(tag_name='button', aria_label='Go to next page')
            await next_btn.click(
                x_offset=randint(-3, 5),
                y_offset=randint(-4, 4)
            )
            await asyncio.sleep(uniform(2.5, 4.2))

            page_idx += 1

        except Exception as e:
            logging.info(f"Could not click next page, stopping: {e}")
            break

async def scrape_agency_page(browser, agency_tab, agency_obj) -> tuple[list[dict[str, str]] | None, list[dict[str, str]] | None]:
    """Scrape both open and past opportunities from already-opened agency tab."""
    logging.info(f"Scraping opportunities for {agency_obj['name']}")
    
    open_opps = await scrape_opportunity_tab(browser, agency_tab, 'open')
    if not open_opps:
        return None, None
    past_opps = await scrape_opportunity_tab(browser, agency_tab, 'past')
    
    return open_opps, past_opps

async def scrape_opportunity_tab(browser, agency_tab, kind='open'):
    """Navigate to open or past tab, get all opportunity links, fetch details for each."""

    taburl_type = 'openOpportunities' if kind == 'open' else 'pastOpportunities'

    base_url = str(await agency_tab.current_url).split('/')[2]
    target_url = f"https://{base_url}/portal/?tab={taburl_type}"
    await asyncio.sleep(2)

    print("Opening opps")
    
    await agency_tab.go_to(target_url)
    await asyncio.sleep(4)
    
    links = []
    buttons = await agency_tab.find(tag_name="a", class_name="btn bold box-sizing alignCenter", find_all=True)
    for btn in buttons:
        href = btn.get_attribute("href")
        if href and "/opportunities/" in href:
            links.append(f"https://{base_url}{href}")
    
    logging.info(f"Found {len(links)} opportunities for {kind}")
    
    results = []
    for url in links:
        opp_data = await fetch_opportunity_data(browser, url)
        if opp_data:
            opp_data["Opportunity link"] = base_url
            results.append(opp_data)
    logging.info(f"Successfully captured {len(results)} opportunities from https:\\{base_url}")
    return results

async def fetch_opportunity_data(browser, opp_url) -> dict[str, str] | None:
    """Open opportunity detail page, extract data from JSON-LD script, return raw data."""

    opp_tab = await browser.new_tab()
    data = None
    custom_selector = (By.ID, "content")

    try:
        # await opp_tab.go_to(opp_url)
        # await asyncio.sleep(10)
        # tgnx8
        async with opp_tab.expect_and_bypass_cloudflare_captcha(
            custom_selector=custom_selector,
            time_before_click=10,
            time_to_wait_captcha=5
            ):
            await opp_tab.go_to(opp_url)
            await asyncio.sleep(3)
        
        await asyncio.sleep(5)

        project_details = await opp_tab.find(
            tag_name='div',
            class_name='projectDetailSection',
            find_all=True,
        )

        data = dict()
        count = 1
        if len(project_details) > 1:
            for detail in project_details:
                if count == 9:
                    break
                count += 1
                text = await detail.text
                split_i = text.index(':')    
                key = text[:split_i]
                value = text[split_i + 1:]
                
                data[key] = value
                                
        description = await opp_tab.find(
        tag_name='div',
        class_name='markdown_formatted',
        )

        data['description'] = str(await description.text)

    except Exception as e:
        logging.error(f"Failed to extract {opp_url}: {e}")

    finally:
        if data:
            with open('data.json', 'a+') as f:
                f.write(json.dumps(data))
                f.write(',\n')
    
    await opp_tab.close()
    await asyncio.sleep(uniform(0.9, 1.6))
    return data

@retry(max_retries=5, exceptions=[TimeoutException, ElementNotFound])
async def run_scraper():
    """Main scraper: login, find agencies, scrape opportunities, dump raw data."""
    raw_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
    os.makedirs(raw_folder, exist_ok=True)
    
    proxy = get_proxy()
    options = ChromiumOptions()
    # options.add_argument(f'--proxy-server={proxy}')
    
    all_open_raw = []
    all_past_raw = []
    
    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.enable_network_events()
        await tab.go_to(BASE_URL)
        await asyncio.sleep(2)

        '''<a class="MuiButtonBase-root MuiButton-root MuiButton-contained MuiButton-containedPrimary MuiButton-sizeMedium MuiButton-containedSizeMedium MuiButton-colorPrimary MuiButton-disableElevation MuiButton-root MuiButton-contained MuiButton-containedPrimary MuiButton-sizeMedium MuiButton-containedSizeMedium MuiButton-colorPrimary MuiButton-disableElevation css-mjjty1" tabindex="0" type="button" role="link" aria-label="Refresh" href="/" data-discover="true">
        <div class="MuiBox-root css-1bh59ny"></div><div class="MuiBox-root css-rrm59m">Refresh</div>
        <span class="MuiTouchRipple-root css-w0pj6f"></span>
        </a>'''

        # is_refresh = await tab.find(
        #     tag_name='a',
        #     aria_label="Refresh",
        #     raise_exc=False
        #     )

        # if is_refresh:
        #     print('Button clicked')
        #     await is_refresh.click(randint(-1, 2))

        await login(tab)
        await asyncio.sleep(10)

        agency_tab = await browser.new_tab()
        await agency_tab.go_to(f'{BASE_URL}agencies/search')
        await asyncio.sleep(5)

        async def handle_agency(agency_obj):
            agency_page_tab = agency_obj.get('agency_tab')
            if not agency_page_tab:
                logging.error(f"No agency tab provided for {agency_obj['name']}")
                return False
            logging.info(f"Scraping opportunities for {agency_obj['name']}")
            try:
                open_opps, past_opps = await scrape_agency_page(browser, agency_page_tab, agency_obj)
                if open_opps:
                    past_oppt_len = len(past_opps) if past_opps is not None else 0
                    logging.info(f"Found {len(open_opps)} open and {past_oppt_len} past opportunities for {agency_obj['name']}")
                    for opp in open_opps:
                        opp['organization_name'] = agency_obj['name']
                        all_open_raw.append(opp)

                    if past_opps:
                        for opp in past_opps:
                            opp['organization_name'] = agency_obj['name']
                            all_past_raw.append(opp)
                    return True
                else:
                    logging.info(f"Skipped {agency_obj['name']}: No open opportunities.")
                    return False
            except Exception as e:
                logging.error(f"Error processing {agency_obj['name']}: {e}")
                return False
        
        await navigate_agency_search_tab(agency_tab, browser, handle_agency)
        
        with open(os.path.join(raw_folder, 'open_opportunities_raw.json'), 'w') as f:
            json.dump(all_open_raw, f, indent=2)
        with open(os.path.join(raw_folder, 'past_opportunities_raw.json'), 'w') as f:
            json.dump(all_past_raw, f, indent=2)
        
        logging.info(f"Scraped {len(all_open_raw)} open and {len(all_past_raw)} past opportunities (raw data saved)")

if __name__ == "__main__":
    configure_logging()
    asyncio.run(run_scraper())
        
    raw_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
    
    with open(os.path.join(raw_folder, 'open_opportunities_raw.json'), 'r') as f:
        open_raw = json.load(f)
    with open(os.path.join(raw_folder, 'past_opportunities_raw.json'), 'r') as f:
        past_raw = json.load(f)
    
    open_clean = clean_all_opportunities(open_raw)
    past_clean = clean_all_opportunities(past_raw)
    
    open_clean = deduplicate_opportunities(open_clean)
    past_clean = deduplicate_opportunities(past_clean)
    
    with open(os.path.join(raw_folder, 'open_opportunities.json'), 'w') as f:
        json.dump(open_clean, f, indent=2)
    with open(os.path.join(raw_folder, 'past_opportunities.json'), 'w') as f:
        json.dump(past_clean, f, indent=2)
    
    init_db()
    insert_opportunities(open_clean + past_clean)
    
    logging.info("Cleaning and database storage complete")
