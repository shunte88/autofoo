import sys
import os
import re
import logging
import feedparser
import requests
import html
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from src.utils import SceneDownload
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent / 'src'))

upo = os.getenv('NTFLR_USERNAME')
if not upo:
    print('NTFLR_USERNAME not set')
    sys.exit(1)

sdx = SceneDownload(
    download_dir=os.getenv(
        'VIDEO_DOWNLOAD_DIR', 
        '/data/videos'
    ),
    uxs=upo,
    pxs=os.getenv('NTFLR_PREMIUM'),
    logging_verbose=True)
tvshows_ = sdx.load_tvshows()

def can_process(title):
    test = title.upper()
    keys = ('AV1','HEVC','X265')
    return ('1080P' in test and \
        'NF' in test and \
        any(key in test for key in keys))

def go_show(title):
    # the title needs to be sanitized
    match = re.search(sdx.season_episode_regex, title, re.IGNORECASE)
    if not match:
        sanshow = title.upper()
    else:
        sanshow, _ = match.groups()
    sanshow = sanshow.split(']')[1].strip().upper()
    # straight equivalence
    return sanshow in tvshows_

basesrl = 'https://scene-rls.net/releases/index.php?'

urls = [
    {'source':'https://rapidmoviez.cr/feed/s','type':'RSS'},
    {'source':'https://rapidmoviez.cr/feed/m','type':'RSS'},
    {'source':'feed.xml','type':'FILE'},
]

delta = (datetime.now() - timedelta(hours=12)).replace(tzinfo=timezone.utc)
process = []
for uri in urls:

    url = uri['source']
    logging.info(url)
    if uri['type'] == 'RSS':
        feed = feedparser.parse(url)
        entries = feed.entries
    elif uri['type'] == 'FILE' and os.path.exists(url):
        feed = feedparser.parse(url)
        entries = feed.entries
        # cleanup the feed.xml file
        os.remove(url)
    else:
        try:
            logging.info(f"""{uri['type']}: {uri['regex']['first']}""")
            entries = sdx.get_first_links(url)
        except:
            pass
        continue

    # Iterate through entries and filter by the time and keyword
    # further filter by shows of interest
    logging.info(f'Evaluating {len(feed.entries)} potential shows')
    for entry in entries:
        if '1080P' in entry.title.upper():

            test = entry.title.upper().split('1080P')[0].strip().split(']')[-1].strip()
            test = sdx.sanitize_show(test)
            print(test)
            if can_process(entry.title) \
                and go_show(entry.title) \
                and sdx.not_seen(test):
                sdx.add_seen_show(test) # no repeat downloads!!!!
                entry['test'] = test
                logging.info(f'Adding {test} for further processing...')
                process.append(entry)

nlx = []
for show in sorted(process, \
    key=lambda x: datetime.strptime(x.published, "%a, %d %b %Y %H:%M:%S %z").timestamp()):
    nlx.append((sdx.load_page(show.link), show.test))

#nlx.append((sdx.load_page('https://rapidmoviez.cr/the-studio'), 'The.Studio.S01E00'))

sdx.close()
sdx.download_files(nlx)
sdx.rebuild_seen_shows()
