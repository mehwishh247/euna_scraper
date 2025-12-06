import asyncio
import os
from random import randint, uniform
from itertools import cycle

from pydoll.browser import tab as Tab
from pydoll.browser.chromium import Chrome
from pydoll.browser.options import ChromiumOptions
# from pydoll.connection.connection_handler import ConnectionHandler
# from pydoll.protocol.network.events import NetworkEvent
# from pydoll.protocol.page.events import PageEvent

from pydoll.decorators import retry
from pydoll.exceptions import WaitElementTimeout, NetworkError, ElementNotFound, TimeoutException

from dotenv import load_dotenv

load_dotenv()

EMAIL = os.getenv('EMAIL')
PASSWORD = os.getenv('PASSWORD')
BASE_URL = 'https://vendor.bonfirehub.com/'

PROXIES = [
        'http://202.69.38.42:5678',
        'http://103.157.200.126:3128',
        'http://103.157.200.126:3128,',
        'http://103.155.62.141:8081',
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
    # change this with page load complete

    email = await tab.find(id="input-email")
    await email.click(
        x_offset=randint(-3, 5),
        y_offset=randint(-5, 2)
    )
    await asyncio.sleep(uniform(1.0, 2.0))

    for i, char in enumerate(EMAIL):
        await email.type_text(char, interval=0)
        # Longer pause at @ and . symbols (natural)
        if char in ['@', '.']:
            await asyncio.sleep(uniform(0.2, 0.4))
        else:
            await asyncio.sleep(uniform(0.1, 0.2))

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

    p = await tab.find(
        tag_name='p',
        role='alert',
        raise_exec=False
    )

    if not p:
        return
    
    await asyncio.sleep(uniform(15.0,30.0))
    return

async def fetch_agencies(dashboard_tab):
    opportunity_btn = await dashboard_tab.find(
        tag_name='button',
        class_name='css-hf45bl'
    )
    await opportunity_btn.click(
        x_offset=randint(-1,2),
        y_offset=randint(-2,1)
    )
    await asyncio.sleep(0.5)

    agency_link = await dashboard_tab.find(
        tag_name='a',
        class_name='css-1rfvp8v',
        find_all=True
    )[1]

    return agency_link

@retry(max_retries=2, exceptions=[TimeoutException, ElementNotFound])
async def run_scraper():
    # connection =ConnectionHandler()
    proxy = get_proxy()
    options = ChromiumOptions()
    options.add_argument(f'--proxy-server={proxy}')
    print(proxy)

    async with Chrome(options=options) as browser:
        tab = await browser.start()
        await tab.enable_network_events()

        await tab.go_to(BASE_URL)
        await asyncio.sleep(4)

        # await tab.execute_script('return document.body.script')

        # log = await tab.get_network_logs()
        # requestid = log[0]['params']['requestId']
        # resp = await tab.get_network_response_body(requestid)
        # print('\n', resp[0], '\n')

        # await tab.disable_network_events()

        await login(tab)
        await asyncio.sleep(2)

        agency_link = await fetch_agencies(tab)
        await asyncio.sleep(2)

        agency_tab = await browser.new_tab(url=agency_link)

        await asyncio.sleep(5)

        await tab.close()

asyncio.run(run_scraper())
# async def scraper():
