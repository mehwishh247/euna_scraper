import asyncio
import os
import json
from random import randint, uniform
import random

from pydoll.browser import tab as Tab
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions
from pydoll.decorators import retry
from pydoll.exceptions import WaitElementTimeout, NetworkError, ElementNotFound, TimeoutException
from dotenv import load_dotenv
import logging
from utils import configure_logging

load_dotenv()

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
    goto_login = await tab.find(tag_name='a', class_name='MuiButtonBase-root')
    await goto_login.click(
        x_offset=randint(-2,2),
        y_offset=randint(-2,2)
    )
    await asyncio.sleep(uniform(6.0,9.5))
    email = await tab.find(id="input-email")
    await email.click(
        x_offset=randint(-3, 5),
        y_offset=randint(-5, 2)
    )
    await asyncio.sleep(uniform(1.0, 2.0))

    for i, char in enumerate(EMAIL):
        await email.type_text(char, interval=0.2)

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
    for char in PASSWORD:
        await password.type_text(char, interval=0.02)
    continue_button = await tab.find(tag_name="button")
    await continue_button.click(
        x_offset=randint(-1, 2),
        y_offset=randint(1, 3)
    )
    await asyncio.sleep(uniform(5,7))

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

async def navigate_agency_search_tab(agency_tab, on_agency_found):
    """Navigate agency search pages, find matching agencies (D/G/J/L), call callback immediately for each."""
    selected = {p: 0 for p in AGENCY_PREFIXES}
    seen_names = set()
    page_idx = 1
    
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
                if name in seen_names or selected[prefix] >= AGENCIES_PER_PREFIX:
                    continue
                    
                seen_names.add(name)
                region_span = await card.find(tag_name='span', class_name='css-1l59ypq', raise_exec=False)
                region = str(await region_span.text).strip() if region_span else None
                
                agency_obj = {
                    'name': name,
                    'region': region,
                    'card_element': card
                }
                
                # Call callback immediately - it will scrape and return True if has open opps
                has_open = await on_agency_found(agency_obj)
                if has_open:
                    selected[prefix] += 1
                    logging.info(f"Selected {name} ({prefix}): {selected[prefix]}/5 for {prefix}")
                
                if all(selected[p] == AGENCIES_PER_PREFIX for p in AGENCY_PREFIXES):
                    logging.info(f"Collected all required agencies: {selected}")
                    return
            except Exception as e:
                logging.warning(f"Error parsing agency card: {e}")
                continue
        
        if all(selected[p] == AGENCIES_PER_PREFIX for p in AGENCY_PREFIXES):
            break
            
        # Pagination check
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
                x_offset=random.randint(-3, 5),
                y_offset=random.randint(-4, 4)
            )
            await asyncio.sleep(random.uniform(2.5, 4.2))

            page_idx += 1

        except Exception as e:
            logging.info(f"Could not click next page, stopping: {e}")
            break

async def scrape_agency_page(parent_tab, agency_obj):
    """Open agency page, scrape both open and past opportunities, return raw data."""
    card = agency_obj['card_element']
    tabs_before = parent_tab.window.open_tabs
    
    await card.click(
        x_offset=random.randint(-3, 5),
        y_offset=random.randint(-4, 4)
    )
    await asyncio.sleep(random.uniform(3.5, 6.0))
    
    # Wait for new tab
    newtab = None
    for _ in range(10):
        tabs_after = parent_tab.window.open_tabs
        if len(tabs_after) > len(tabs_before):
            newtab = list(set(tabs_after) - set(tabs_before))[0]
            break
        await asyncio.sleep(0.5)
    
    if not newtab:
        logging.warning(f"Could not open tab for {agency_obj['name']}")
        return [], []
    
    await newtab.bring_to_front()
    await asyncio.sleep(random.uniform(1.2, 2.2))
    
    # Scrape open opportunities
    open_opps = await scrape_opportunity_tab(newtab, 'open')
    
    # Scrape past opportunities
    past_opps = await scrape_opportunity_tab(newtab, 'past')
    
    await newtab.close()
    return open_opps, past_opps

async def scrape_opportunity_tab(agency_tab, kind='open'):
    """Navigate to open or past tab, get all opportunity links, fetch details for each."""
    taburl_type = 'openOpportunities' if kind == 'open' else 'pastOpportunities'
    org_url = str(agency_tab.url).split('/portal')[0]
    target_url = f"{org_url}/portal/?tab={taburl_type}"
    
    await agency_tab.go_to(target_url)
    await asyncio.sleep(random.uniform(2.5, 4.7))
    
    # Find all opportunity links
    links = []
    buttons = await agency_tab.find(tag_name="a", class_name="btn bold", find_all=True)
    for btn in buttons:
        href = btn.get_attribute("href")
        if href and "/opportunities/" in href:
            links.append(f"{org_url}{href}")
    
    logging.info(f"Found {len(links)} opportunities for {kind}")
    
    # Fetch details for each opportunity
    results = []
    for url in links:
        opp_data = await fetch_opportunity_data(agency_tab, url)
        if opp_data:
            opp_data['apply_url'] = url
            results.append(opp_data)
    
    return results

async def fetch_opportunity_data(parent_tab, opp_url):
    """Open opportunity detail page, extract data from JSON-LD script, return raw data."""
    browser = parent_tab.window
    opp_tab = await browser.new_tab()
    data = None
    
    try:
        await opp_tab.go_to(opp_url)
        await asyncio.sleep(random.uniform(3.5, 6.0))
        
        # Extract JSON-LD script
        scripts = await opp_tab.find_all(xpath="//script[@type='application/ld+json']")
        for script in scripts:
            text = getattr(script, "text", None) or getattr(script, "innerText", "")
            if text and '{' in text:
                try:
                    d = json.loads(text)
                    data = d
                    break
                except Exception as e:
                    continue
    except Exception as e:
        logging.error(f"Failed to extract {opp_url}: {e}")
    
    await opp_tab.close()
    await asyncio.sleep(random.uniform(0.9, 1.6))
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
        
        await login(tab)
        await asyncio.sleep(10)
        
        agency_tab = await browser.new_tab()
        await agency_tab.go_to(f'{BASE_URL}agencies/search')
        await asyncio.sleep(5)
        
        # Callback: scrape agency immediately when found
        async def handle_agency(agency_obj):
            open_opps, past_opps = await scrape_agency_page(agency_tab, agency_obj)
            if open_opps:
                for opp in open_opps:
                    opp['organization_name'] = agency_obj['name']
                    all_open_raw.append(opp)
                for opp in past_opps:
                    opp['organization_name'] = agency_obj['name']
                    all_past_raw.append(opp)
                return True
            else:
                logging.info(f"Skipped {agency_obj['name']}: No open opportunities.")
                return False
        
        # Navigate and scrape as we go
        await navigate_agency_search_tab(agency_tab, handle_agency)
        
        # Dump raw data
        with open(os.path.join(raw_folder, 'open_opportunities_raw.json'), 'w') as f:
            json.dump(all_open_raw, f, indent=2)
        with open(os.path.join(raw_folder, 'past_opportunities_raw.json'), 'w') as f:
            json.dump(all_past_raw, f, indent=2)
        
        logging.info(f"Scraped {len(all_open_raw)} open and {len(all_past_raw)} past opportunities (raw data saved)")

if __name__ == "__main__":
    configure_logging()
    asyncio.run(run_scraper())
    
    # After scraping, clean and store
    from cleaner import clean_all_opportunities
    from db import init_db, insert_opportunities
    from utils import deduplicate_opportunities
    import json
    import os
    
    raw_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
    
    # Load raw data
    with open(os.path.join(raw_folder, 'open_opportunities_raw.json'), 'r') as f:
        open_raw = json.load(f)
    with open(os.path.join(raw_folder, 'past_opportunities_raw.json'), 'r') as f:
        past_raw = json.load(f)
    
    # Clean data
    open_clean = clean_all_opportunities(open_raw)
    past_clean = clean_all_opportunities(past_raw)
    
    # Deduplicate
    open_clean = deduplicate_opportunities(open_clean)
    past_clean = deduplicate_opportunities(past_clean)
    
    # Save cleaned data
    with open(os.path.join(raw_folder, 'open_opportunities.json'), 'w') as f:
        json.dump(open_clean, f, indent=2)
    with open(os.path.join(raw_folder, 'past_opportunities.json'), 'w') as f:
        json.dump(past_clean, f, indent=2)
    
    # Store to DB
    init_db()
    insert_opportunities(open_clean + past_clean)
    
    logging.info("Cleaning and database storage complete")
