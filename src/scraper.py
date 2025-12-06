import asyncio
import os
from random import randint, uniform
import random
from cleaner import clean_opportunity
import json, os
from utils import deduplicate_opportunities

from pydoll.browser import tab as Tab
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions
# from pydoll.connection.connection_handler import ConnectionHandler
# from pydoll.protocol.network.events import NetworkEvent
# from pydoll.protocol.page.events import PageEvent

from pydoll.decorators import retry
from pydoll.exceptions import WaitElementTimeout, NetworkError, ElementNotFound, TimeoutException
# from pydoll.utils import wait_for_event

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
            # Optionally could retry once more, but for now, we wait for user intervention.
    except ElementNotFound:
        pass
    await asyncio.sleep(uniform(2.0,4.0))

async def goto_agency_tab(agency_tab):
    pass

# --- AGENCY PREFIXES REQUIRED ---
AGENCY_PREFIXES = ["D", "G", "J", "L"]
AGENCIES_PER_PREFIX = 5

# --- HELPERS FOR AGENCY SELECTION ---
def agency_matches_prefix(agency_name, prefix):
    return agency_name.strip().upper().startswith(prefix)

def get_selected_agencies(agency_list):
    selected = {p: [] for p in AGENCY_PREFIXES}
    for agency in agency_list:
        name = agency.get("name", "").strip()
        for p in AGENCY_PREFIXES:
            if name.upper().startswith(p) and len(selected[p]) < AGENCIES_PER_PREFIX:
                selected[p].append(agency)
    # Flatten into single list
    return [ag for ags in selected.values() for ag in ags]    

async def find_agency_listing(agency_tab, scrape_agency_opportunities):
    """
    Immediately scrape opportunities as soon as a D/G/J/L agency is found,
    collect up to 5 per prefix, break immediately when the quota is hit for all 4 letters.
    """
    selected = {p: 0 for p in ["D", "G", "J", "L"]}
    agencies_collected = {p: [] for p in ["D", "G", "J", "L"]}
    page_idx = 1
    while True:
        cards = await agency_tab.find(tag_name='div', class_name='MuiBox-root css-cfm4ee', find_all=True)
        logging.info(f"[Page {page_idx}] Found {len(cards)} agency card elements")
        for card in cards:
            try:
                name_p = await card.find(tag_name='p', class_name='MuiTypography-root MuiTypography-subtitle2  css-prt0s1')
                name = name_p.text.strip()
                prefix = next((p for p in selected if name.upper().startswith(p)), None)
                if not prefix:
                    continue
                if selected[prefix] >= 5:
                    continue
                # Scrape this agency's opportunities immediately
                region_span = await card.find(tag_name='span', class_name='MuiTypography-root MuiTypography-body3 css-1l59ypq', raise_exec=False)
                region = str(await region_span.text).strip() if region_span else None
                agency_obj = {'name': name, 'region': region, 'card_element': card}
                has_opportunities = await scrape_agency_opportunities(agency_obj)
                if has_opportunities:
                    agencies_collected[prefix].append(agency_obj)
                    selected[prefix] += 1
                    logging.info(f"Selected {name} (prefix {prefix}), now have {selected[prefix]} for {prefix}.")
                else:
                    logging.info(f"Skipping {name}: No open opportunities found.")
                # If we've satisfied all quotas, stop all collection immediately
                if all(n == 5 for n in selected.values()):
                    logging.info(f"Collected all required agencies: {selected}")
                    return agencies_collected
            except Exception as e:
                logging.warning(f"Error parsing agency card or scraping opps: {e}")
                continue
        # Pagination: footer
        try:
            paginator_p = await agency_tab.find(tag_name='p', class_name='MuiTypography-root MuiTypography-body2 css-ghev09')
            paginator_text = paginator_p.text.strip()
            parts = paginator_text.split()
            last_entry = int(parts[3])
            total_entries = int(parts[-1])
            if last_entry == total_entries:
                logging.info(f"Reached last page (entry {last_entry} == total {total_entries}). Stopping pagination.")
                break
        except Exception as e:
            logging.warning(f"Could not parse page footer for pagination: {e}")
            break
        # Find next page button by aria-label
        try:
            next_btn = await agency_tab.find(tag_name='button', aria_label='Go to next page')
            await human_like_click(next_btn)
            await asyncio.sleep(random.uniform(2.5, 4.2))
            page_idx += 1
        except Exception as e:
            logging.info(f"Could not click next page, stopping: {e}")
            break
    return agencies_collected

async def fetch_opportunities(parent_tab, agency_obj, kind='open'):
    """Click card, catch new tab, scrape the right opportunity kind."""
    # Click agency card -> opens new tab
    card = agency_obj['card_element']
    tabs_before = parent_tab.window.open_tabs
    await human_like_click(card)
    await asyncio.sleep(random.uniform(3.5, 6.0)) # wait for new tab load
    # Wait for new tab
    newtab = None
    for _ in range(10):
        tabs_after = parent_tab.window.open_tabs
        if len(tabs_after) > len(tabs_before):
            newtab = list(set(tabs_after) - set(tabs_before))[0]
            break
        await asyncio.sleep(0.5)
    if not newtab:
        return []
    await newtab.bring_to_front()
    await asyncio.sleep(random.uniform(1.2, 2.2)) # wait for content render
    # Now scrape opportunities of the right type
    data = await extract_opportunities_from_agency_tab(newtab, kind=kind)
    await newtab.close()
    return data

async def go_to_portal_and_tab(agency_tab, taburl_type):
    '''Go to Portal and switch to open or past opportunities via URL.'''
    ORG_URL = str(agency_tab.url).split('/portal')[0]
    TARGET_URL = f"{ORG_URL}/portal/?tab={taburl_type}"
    await agency_tab.go_to(TARGET_URL)
    await asyncio.sleep(random.uniform(2.5, 4.7)) # wait for tab/page load
    return

async def get_opportunity_links_on_tab(tab):
    """
    Find all 'View Opportunity' links on current tab.
    Returns: list of absolute URLs.
    """
    links = []
    buttons = await tab.find_all(css_selector="a.btn.bold")
    for btn in buttons:
        href = btn.get_attribute("href")
        if href and "/opportunities/" in href:
            org_url = str(tab.url).split('/portal')[0]
            links.append(f"{org_url}{href}")
    return links

async def extract_opportunity_details(tab, opp_url):
    '''Open a new tab, go to opp_url, parse <script type=ld+json>, close tab.'''
    data = None
    browser = tab.window
    opp_tab = await browser.new_tab()
    try:
        await opp_tab.go_to(opp_url)
        await asyncio.sleep(random.uniform(3.5, 6.0)) # wait for detail load
        # CAPTCHA handling (pseudo):
        # If captcha present, skip/log. UI review needed for bypass.
        #if await opp_tab.find(...):
        #   logging.warning(f"Captcha detected at {opp_url}, skipping.")
        #   return None
        # Extract first <script type='application/ld+json'> block:
        scripts = await opp_tab.find_all(xpath="//script[@type='application/ld+json']")
        for script in scripts:
            text = getattr(script, "text", None) or getattr(script, "innerText", "")
            if text and '{' in text:
                try:
                    import json
                    d = json.loads(text)
                    data = d
                    break
                except Exception as e:
                    continue
        # supplement with main fields if missing
    except Exception as e:
        logging.error(f"Failed to extract {opp_url}: {e}")
    await opp_tab.close()
    await asyncio.sleep(random.uniform(0.9, 1.6)) # wait between details
    return data

async def extract_opportunities_from_agency_tab(tab, kind='open'):
    '''Go to open/past tab, find all opps, open each, scrape details (<script type=ld+json>).'''
    taburl_type = 'openOpportunities' if kind == 'open' else 'pastOpportunities'
    await go_to_portal_and_tab(tab, taburl_type)
    opp_links = await get_opportunity_links_on_tab(tab)
    logging.info(f"Found {len(opp_links)} opportunities for {kind}")
    result = []
    for url in opp_links:
        opp_data = await extract_opportunity_details(tab, url)
        if opp_data is None:
            continue
        opp_data['apply_url'] = url # Add detail page as application url
        result.append(opp_data)
    return result

async def find_public_opportunities():
    '''
    pass and present opportunities
    '''
    pass

async def fetch_data():
    ''' Fetch data for each listing and save into raw data '''
    raw_folder = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))
    os.makedirs(raw_folder, exist_ok=True)
    proxy = get_proxy()
    options = ChromiumOptions()
    options.add_argument(f'--proxy-server={proxy}')

    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.enable_network_events()
        await tab.go_to(BASE_URL)

        await login(tab)
        await asyncio.sleep(10)

        agency_tab = await browser.new_tab()
        await agency_tab.go_to(f'{BASE_URL}agencies/search')
        await asyncio.sleep(5)

        # Define a function to scrape opportunities for a single agency
        async def scrape_agency_opportunities(agency_obj):
            open_opps = await fetch_opportunities(agency_tab, agency_obj, kind='open')
            for item in open_opps:
                clean = clean_opportunity(item, agency_obj)
                # Add to a temporary list for deduplication
                all_open.append(clean)
            past_opps = await fetch_opportunities(agency_tab, agency_obj, kind='past')
            for item in past_opps:
                clean = clean_opportunity(item, agency_obj)
                # Add to a temporary list for deduplication
                all_past.append(clean)
            return len(open_opps) > 0 # Return True if open opportunities were found

        # Initialize lists to collect all opportunities
        all_open = []
        all_past = []

        # Call find_agency_listing with the scraping function
        agencies_collected = await find_agency_listing(agency_tab, scrape_agency_opportunities)

        # Deduplicate
        all_open = deduplicate_opportunities(all_open)
        all_past = deduplicate_opportunities(all_past)
        with open(os.path.join(raw_folder, 'open_opportunities.json'), 'w') as f:
            json.dump(all_open, f, indent=2)
        with open(os.path.join(raw_folder, 'past_opportunities.json'), 'w') as f:
            json.dump(all_past, f, indent=2)
    return True

@retry(max_retries=5, exceptions=[TimeoutException, ElementNotFound])
async def run_scraper():
    await fetch_data()

if __name__ == "__main__":
    asyncio.run(run_scraper())
'''
* turn raw data into two different files (open and past)
* Use a cleaner function from cleaner.py that will clean data (stripping, changing datatypes etc) before saving into both files
* Add functions to db.py to initialize db, add table, add data to table. Make sure to have a function that runs on start up to check if db exists and table exist. Make them if they do not exist
* work on docker file to run up and setup everything as required in project description. 
'''
