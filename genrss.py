import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
import sys


def generate_rss_feed(uri, output_file='feed.xml'):
    response = requests.get(uri, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(response.text, 'html.parser')

    # Parse base URL
    base_url = f"{urlparse(uri).scheme}://{urlparse(uri).netloc}"

    # Start the RSS structure
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'RapidMovieZ 1080p NF HEVC Feed'
    ET.SubElement(channel, 'link').text = uri
    ET.SubElement(channel, 'description').text = 'Filtered links for 1080p releases containing NF and HEVC'
    ET.SubElement(channel, 'lastBuildDate').text = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %z')

    # Find all relevant links in the page
    for link in soup.find_all('a', href=True):
        href = link['href']
        text = link.get_text(strip=True)
        if '1080p' in text and 'NF' in text and 'HEVC' in text:
            full_url = urljoin(base_url, href)
            item = ET.SubElement(channel, 'item')
            ET.SubElement(item, 'title').text = text
            ET.SubElement(item, 'link').text = full_url
            ET.SubElement(item, 'guid').text = full_url
            ET.SubElement(item, 'pubDate').text = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %z')

    # Write to file
    tree = ET.ElementTree(rss)
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"RSS feed written to {output_file}")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python genrss.py <uri>")
        sys.exit(1)
    generate_rss_feed(sys.argv[1])
