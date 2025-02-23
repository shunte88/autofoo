import sys
import os
import feedparser
from datetime import datetime, timedelta, timezone
from src.utils import chrome_browser_options, init_browser, download_files, seen_shows
import requests
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

sys.path.append(str(Path(__file__).resolve().parent / 'src'))

upo = os.Getenv("NTFLR_USERNAME")
if not upo:
    print("NTFLR_USERNAME not set")
    sys.exit(1)

ppo = os.getenv("NTFLR_PREMIUM")

chrome_options = chrome_browser_options()
driver = init_browser(chrome_options)

urlm = "https://rapidmoviez.cr/feed/m"
urls = "https://rapidmoviez.cr/feed/s"

feed = feedparser.parse(urls)
delta = (datetime.now() - timedelta(hours=12)).replace(tzinfo=timezone.utc)

def load_page(url):
    
    def good(link):
        test = link.upper()
        keys = ('.MP4', '.MKV', '.MOV', '.MPG', '.WEBM')
        return any(key in test for key in keys)

    driver.get(url)
    try:
        # Wait for the specific HTML structure to render
        WebDriverWait(driver, 1).until(
            EC.presence_of_element_located((By.XPATH, '//h4[@class="links" and contains(text(), "NitroFlare:")]/following-sibling::pre[@class="links"]'))
        )

        # Extract the Nitroflare links from the <pre> tag
        links = driver.find_element(By.XPATH, '//h4[@class="links" and contains(text(), "NitroFlare:")]/following-sibling::pre[@class="links"]')
        links = links.text.strip().split("\n")
        links = [link for link in links if good(link)]

        return links
    except Exception as e:
        print(f'Exception: {e}')
        return None

# Load garbage words from file
def load_garbage_words(filepath):
    """
    Load ripper/scene garbage words from a file.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        return set(line.strip().lower() for line in f if line.strip())

GARBAGE_WORDS = load_garbage_words("/data/tvtitle_munge.txt")

# List of special case words that should stay uppercase
SPECIAL_CASES = {
    "USA", "FBI", "BBC",
    "US", "AU", "PL", "IE", "NZ", "FR", "DE", "JP", "UK",
    "QI", "XL",
    "WWII", "WPC",
    "VI", "VII", "VIII", "VIIII", "IX", "II", "III", "IV",
    "DCI", "HD", "W1A", "HBO", "100K",
}

def load_tvshows():
    """
    Load tv shows of interest.
    """
    with open('tvshows.list', 'r', encoding='utf-8') as f:
        return set(line.strip().upper() \
            for line in f if line.strip() and line[0] != '#')

def can_process(title):
    test = title.upper()
    keys = ('AV1','HEVC','X265')
    return ('1080P' in test and \
        'NF' in test and \
        any(key in test for key in keys))

def go_show(title, shows):
    return any(show in title.upper() for show in shows)

def not_seen(test):
    return not(test+'\n' in seen_shows())

tvshows = load_tvshows()
process = []

# Iterate through entries and filter by the time and keyword
# further filter by shows of interest
for entry in feed.entries:
    entry_date = datetime.strptime(entry.published, "%a, %d %b %Y %H:%M:%S %z")
    test = entry.title.upper().split('1080P')[0].strip().split(']')[-1].strip()
    if entry_date >= delta \
        and can_process(entry.title) \
        and go_show(entry.title, tvshows) \
        and not_seen(test):
        entry['test'] = test
        process.append(entry)

nlx = []
for show in sorted(process, \
    key=lambda x: datetime.strptime(x.published, "%a, %d %b %Y %H:%M:%S %z").timestamp()):
    nlx.append((load_page(show.link), show.test))

driver.quit()    

download_files(nlx,upo,ppo)
