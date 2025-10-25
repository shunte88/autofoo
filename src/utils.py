#!/usr/bin/env python3
import os
import sys
import logging
import time
from datetime import datetime
import requests
import asyncio
import aiohttp
from pathlib import Path
import re

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from fake_useragent import UserAgent

import plyvel

class SceneDownload:

    # Constants
    DB_PATH = "./cache/"
    NTFURL_API = "https://nitroflare.com/api/v2"
    NTFURL_KEYINFO = f"{NTFURL_API}/getKeyInfo"
    NTFURL_FILEINFO = f"{NTFURL_API}/getFileInfo"
    NTFURL_DOWNLOADLINK = f"{NTFURL_API}/getDownloadLink"

    # List of special case words that should stay uppercase
    SPECIAL_CASES = {
        "USA", "FBI", "BBC", "CSI", "WILTY",
        "US", "AU", "PL", "IE", "NZ", "FR", "DE", "JP", "UK",
        "QI", "XL", "LOL",
        "WWII", "WPC","TV",
        "VI", "VII", "VIII", "VIIII", "IX", "II", "III", "IV",
        "DCI", "HD", "W1A", "HBO", "100K",
    }

    # don't expect anything other than mkv, webm, and mp4 in 2025
    FILETYPES = ['mkv', 'mpeg', 'mp4', 'm4v', 'mpg', 'webm', 'avif', 'ts']

    def __init__(self, **kwargs):
        self.season_episode_regex = r"(.*?)(S\d{2,3}E\d{2})"
        self.season_episode_title_regex = r"s\d{2,3}e\d{2}\.(.*)"
        self.driver = None
        self.seen_db = plyvel.DB(self.DB_PATH, create_if_missing=True) 
        self.tvshows_ = []
        self.chromeProfilePath = os.path.join(os.getcwd(), "chrome_profile", "scene_profile")
        sys.path.append(self.chromeProfilePath)
        self.profile_dir = os.path.basename(self.chromeProfilePath)
        sys.path.append(self.profile_dir)
        #self.seen_file = os.path.join(os.getcwd(),'.','seen_files_load')
        self.log_dir = os.path.join(os.getcwd(), "logs")
        self.download_dir = kwargs.get('download_dir', None)
        self.uxs = kwargs.get('uxs', None)
        self.pxs = kwargs.get('pxs', None)
        self.logging_verbose = kwargs.get('logging_verbose', False)
        self.scene_tags = []
        self._init_logging()
        #self._run_once()
        self.init_browser(self.chrome_browser_options())

    def _view_db(self):
        print("\n--- Verifying Seen Data ---")
        for key, value in self.seen_db:
            print(f"Key: {key.decode('utf-8')}, Value: {value.decode('utf-8')}")
            
    def _run_once(self):
        return
        tmp_file = self.seen_file + '.tmp'
        with open(self.seen_file, 'r', encoding='utf-8') as fin:
            with open(tmp_file, 'w', encoding='utf-8') as fout:
                for line in fin:
                    key = line.strip().encode('utf-8')
                    # stage unknown key
                    if self.seen_db.get(key) is None:
                        fout.write(line)
        with open(tmp_file, 'r', encoding='utf-8') as f:
            # Use a batch to perform multiple writes efficiently
            with self.seen_db.write_batch() as wb:
                for line in f:
                    key = line.strip().encode('utf-8')
                    # prime
                    now = datetime.now()
                    value = now.strftime("%Y-%m-%d %H:%M:%S").encode('utf-8')
                    self.seen_db.put(key, value)

    def _init_logging(self, **kwargs):
        self.ensure_log_dir()
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            level = logging.INFO,
            format = '%(asctime)s:%(levelname)s:%(name)s:%(message)s',
            handlers = [
                logging.FileHandler(os.path.join(self.log_dir, f'autofoo_log_{self._get_timestamp()}.log')),
                logging.StreamHandler(sys.stdout)
            ])
        # Set the formatter for the handler
        logging.info(f'Setting log directory at {self.log_dir}')
        if self.logging_verbose:
            self.webdriver_logging = 0
        return True

    def __del__(self):
        self.close()
        logging.info(f'Goodbye from {str(type(self)).replace("<class '", '').replace("'>",'')}')

    def close(self):
        if self.driver:
            try:
                logging.info('Cleanup Chrome')
                self.driver.quit()
                self.driver = None
            except:
                pass

    def set_params(self, **kwargs):
        self.download_dir = kwargs.get('download_dir', self.download_dir)
        self.uxs = kwargs.get('uxs', self.uxs)
        self.pxs = kwargs.get('pxs', self.pxs)

    # Load garbage words from file
    def load_scene_tags(self, filepath='/data/tvtitle_munge.txt'):
        """
        Load ripper/scene garbage words from a file.
        """
        with open(filepath, "r", encoding="utf-8") as f:
            self.scene_tags = set(line.strip().lower() for line in f if line.strip())

    def setup_request_session(self):
        # Create a Requests session
        self.session = requests.Session()
        # Get cookies from Selenium and add them to Requests session
        for cookie in self.driver.get_cookies():
            self.session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])

    def get_first_links(self, url) -> dict:
        # Use the Requests session to make requests with the transferred cookies
        response = self.session.get(url)
        print(response.content)
        return {}

    def ensure_log_dir(self):
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def _get_timestamp(self):
        return datetime.now().strftime("%Y_%m_%d_%H_%M_%S")

    def season_episode_regex(self):
        return self.season_episode_regex

    def load_tvshows(self):
        """
        Load tv shows of interest.
        """
        tvshows_file = os.path.join(os.getcwd(), 'tvshows.list')
        with open(tvshows_file, 'r', encoding='utf-8') as f:
            self.tvshows_ = set(line.strip().upper() \
                for line in f if line.strip() and line[0] != '#')
            return self.tvshows_

    def load_page(self, url):

        def good(link):
            test = link.upper()
            keys = ('.MP4', '.MKV', '.MOV', '.MPG', '.WEBM')
            return any(key in test for key in keys)

        self.driver.get(url)
        try:
            # Wait for the specific HTML structure to render
            WebDriverWait(self.driver, 1).until(
                EC.presence_of_element_located((By.XPATH, '//h4[@class="links" and contains(text(), "NitroFlare:")]/following-sibling::pre[@class="links"]'))
            )

            # Extract the Nitroflare links from the <pre> tag
            links = self.driver.find_element(By.XPATH, '//h4[@class="links" and contains(text(), "NitroFlare:")]/following-sibling::pre[@class="links"]')
            links = links.text.strip().split("\n")
            # print(links)
            links = [link for link in links if good(link)]

            return links

        except Exception as e:
            logging.error(f'Exception: {e}')
            return None

    def clean_filename(self, filename):
        """
        Extracts the correct folder and filename from a messy TV episode 
        filename while filtering out scene rippers.
        """

        fn = filename.replace('_', '.').replace('-', '.').replace(' ', '.')
        # Extract show name and season/episode
        match = re.search(self.season_episode_regex, fn, re.IGNORECASE)
        if not match:
            return None, None  # No valid show structure found

        show_raw, season_episode = match.groups()

        # Find episode title, stopping at first garbage word
        title_match = re.search(self.season_episode_title_regex, fn, re.IGNORECASE)
        episode_title_raw = title_match.group(1) if title_match else ""

        # Stop at the first garbage word
        title_tokens = re.split(r"[._\s]+", episode_title_raw.strip())
        filtered_tokens = []
        for token in title_tokens:
            if token.upper() in self.scene_tags:
                break  # Stop at first garbage word
            if token.lower() in self.FILETYPES:
                break
            filtered_tokens.append(token)

        # Format episode title
        episode_title = ""
        if filtered_tokens:
            formatted_title_tokens = [
                word.upper() if word.upper() in self.SPECIAL_CASES else word.capitalize()
                for word in filtered_tokens
            ]
            episode_title = "." + ".".join(formatted_title_tokens).strip(".")

        # Process show name
        show_tokens = re.split(r"[._\s]+", show_raw.strip())
        formatted_show_tokens = [
            word.upper() if word.upper() in self.SPECIAL_CASES else word.capitalize()
            for word in show_tokens
        ]
        show_name = ".".join(formatted_show_tokens).strip(".")

        # Extract file extension
        extension = filename.split(".")[-1].lower()

        # Generate output
        folder = show_name.strip()
        # we use the S00E00 format for specials, movies, etc.
        if 'S00E00' != season_episode.upper():
            clean_filename = f"{folder}.{season_episode.upper()}{episode_title}.{extension}"
        else:
            clean_filename = f"{folder}{episode_title}.{extension}"

        clean_filename = clean_filename.replace('..','.').replace('..','.')
        return folder, clean_filename

    def sanitize_show(self, data):
        test = data.strip().replace(' ','.').upper()
        try:
            match = re.search(self.season_episode_regex, test, re.IGNORECASE)
            if match:
                return ''.join(match.groups())
        except:
            pass
        return test

    def add_seen_show(self, data):
        self.write_seen_entry(data)

    def write_seen_entry(self, data):
        test = self.sanitize_show(data).strip().encode('utf-8')
        if self.seen_db.get(test) is None:
            now = datetime.now()
            value = now.strftime("%Y-%m-%d %H:%M:%S").encode('utf-8')
            self.seen_db.put(test, value)

    async def download_file(self, url, filepath, title=None):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        with open(filepath, 'wb') as f:
                            while True:
                                chunk = await response.content.read(4096)
                                if not chunk:
                                    break
                                f.write(chunk)
                        logging.info(f"Write {url} -> {filepath}")
                        test='.'.join(filepath.split('/')[-1].split('.')[:-1]).upper()
                        self.write_seen_entry(test)
                        if title:
                            self.write_seen_entry(title)
                    else:
                        logging.warning(f"Failed to download {url}, status code: {response.status}")
            except aiohttp.ClientError as e:
                logging.error(f"An error occurred while downloading {url}: {e}")

    async def go_download(self, auri):
        tasks = [self.download_file(url, name, title) for url, name, title in auri]
        await asyncio.gather(*tasks)

    def not_seen(self, test):
        test = self.sanitize_show(test).strip().encode('utf-8')
        return (self.seen_db.get(test) is None)

    def nf_premium(self) -> dict:
        return {"user": self.uxs, "premiumKey": self.pxs}

    def ensure_chrome_profile(self):
        if not os.path.exists(self.profile_dir):
            os.makedirs(self.profile_dir)
        if not os.path.exists(self.chromeProfilePath):
            os.makedirs(self.chromeProfilePath)
        return self.chromeProfilePath

    def chrome_browser_options(self):
        self.ensure_chrome_profile()
        options = webdriver.ChromeOptions()
        options.add_argument("--start-minimized")
        options.add_argument("--headless")
        options.add_argument("--start-maximized")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        options.add_argument("window-size=1920x1080")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-translate")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-logging")
        options.add_argument("--disable-autofill")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-animations")
        options.add_argument("--disable-cache")
        options.add_argument(f"user-agent={UserAgent().random}")
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])

        prefs = {
            "profile.default_content_setting_values.images": 2,
            "profile.managed_default_content_settings.stylesheets": 2,
        }
        options.add_experimental_option("prefs", prefs)

        if len(self.chromeProfilePath) > 0:
            initial_path = os.path.dirname(self.chromeProfilePath)
            self.profile_dir = os.path.basename(self.chromeProfilePath)
            sys.path.append(self.chromeProfilePath)
            sys.path.append(self.profile_dir)
            options.add_argument(f'--user-data-dir={initial_path}')
            options.add_argument(f'--profile-directory={self.profile_dir}')
        else:
            options.add_argument("--incognito")

        return options

    def init_browser(self, chrome_options) -> webdriver.Chrome:
        try:
            options = chrome_options
            service = ChromeService(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.setup_request_session()
            return self.driver
        except Exception as e:
            logging.critical(f"Failed to initialize browser: {str(e)}")
            sys.exit(1)

    def isit(self, subs, inthis):
        if subs in inthis:
            return subs
        else:
            return None

    def download_files(self, files):

        auri = []
        logging.info(f'We have {len(files)} file(s) to process')
        response = requests.get(url=self.NTFURL_KEYINFO, params=self.nf_premium())
        if response.status_code == 200:
            j = response.json()
            if files:
                for f, t in files:
                    if f:
                        for uri in f:
                            if uri:
                                _file_id = uri.split("/")[4]
                                params = {"files": _file_id}
                                response = requests.get(url=self.NTFURL_FILEINFO, params=params)
                                if response.status_code == 200:
                                    j = response.json()
                                    params = self.nf_premium() 
                                    params['file'] = _file_id
                                    response = requests.get(url=self.NTFURL_DOWNLOADLINK, params=params)
                                    if response.status_code == 200:
                                        j = response.json()
                                        print(j)
                                        splitstr = self.isit('1080',j["result"]["name"])
                                        if not splitstr:
                                            splitstr = self.isit('2160',j["result"]["name"])
                                        if not splitstr:
                                            splitstr = self.isit('720',j["result"]["name"])
                                        if not splitstr:
                                            continue
                                        test = f'''{j["result"]["name"].split(splitstr)[0].strip()}{j["result"]["name"].split('.')[-1]}'''
                                        _, show_filename = self.clean_filename(test)
                                        auri.append((
                                            j["result"]["url"],
                                            os.path.join(self.download_dir,show_filename),
                                            t,
                                        ))
                            else:
                                logging.warning('uri exposed as NULL')
                                logging.info(f'>> {t}, {f}')
                    else:
                        logging.warning('files exposed as NULL')
                        logging.info(f'> {t}, {f}')
        if auri:
            asyncio.run(self.go_download(auri))

    def test_files(self):
        test_filenames = [
            "DUPAHIYA.S01.1080p.hdtv.mkv",
            "breaking.bad.s02e05.1080p.bluray.x264.mkv",
            "game.of.thrones.s05e09.720p.hdtv.x264.mkv",
            "prime.suspect.s03e02.720p.hdtv.x264.mkv",
            "stranger.things.s03e01.webrip.hevc.x265.mkv",
            "HIGH_POTENTIAL_s02e12_webrip_hevc_x265.mkv",
            "have.I.got.news.for.you.US.s01e03.webrip.hevc.x265.mkv",
            "high.potential.s01e13.lets.play.1080p.web.dl.hevc.x265.rmteam.mkv",
            "prime.target.s01e05.house.of.1080p.web.dl.hevc.x265.rmteam.mkv"
        ]

        for test in test_filenames:
            logging.info(f"IN .....: {test}")
            path_, name_ = self.clean_filename(test)
            logging.info(f"OUT ....: {path_}/{name_}")
            logging.info(f"Test ...: {self.sanitize_show(test)}\n")

#sdf=SceneDownload()
#sdf.test_files()
#sdf.close()
#exit(0)
