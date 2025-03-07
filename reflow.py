#!/usr/bin/env python3
"""
Reflow - A Webflow site exporter/scraper

This tool downloads a Webflow site and repackages it into a static site,
similar to how exflow works. It preserves the structure, styling, and CMS content.
"""

import os
import re
import json
import time
import shutil
import argparse
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor

class ReflowExporter:
    def __init__(self, url, output_dir, max_workers=5, delay=0.2):
        """
        Initialize the Reflow exporter.
        
        Args:
            url (str): The URL of the Webflow site to export
            output_dir (str): The directory to save the exported site
            max_workers (int): Maximum number of concurrent download workers
            delay (float): Delay between requests to avoid rate limiting
        """
        self.base_url = url
        self.output_dir = output_dir
        self.max_workers = max_workers
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.visited_urls = set()
        self.assets_to_download = set()
        self.cms_pages = {}
        
        # Parse the domain from the URL
        parsed_url = urlparse(self.base_url)
        self.domain = parsed_url.netloc
        
        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)
    
    def download_page(self, url, output_path=None):
        """
        Download a page from the Webflow site.
        
        Args:
            url (str): The URL of the page to download
            output_path (str, optional): The path to save the page to
            
        Returns:
            tuple: (BeautifulSoup object, HTML content)
        """
        if url in self.visited_urls:
            return None, None
        
        self.visited_urls.add(url)
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            # Add delay to avoid rate limiting
            time.sleep(self.delay)
            
            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')
            
            if output_path:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
            
            return soup, html_content
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            return None, None
    
    def process_html(self, soup, base_url, output_path):
        """
        Process HTML content to fix links and find assets to download.
        
        Args:
            soup (BeautifulSoup): The BeautifulSoup object of the page
            base_url (str): The base URL of the page
            output_path (str): The path where the page will be saved
            
        Returns:
            BeautifulSoup: The processed BeautifulSoup object
        """
        # Process links
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if href.startswith('#') or href.startswith('mailto:') or href.startswith('tel:'):
                continue
                
            absolute_url = urljoin(base_url, href)
            parsed_url = urlparse(absolute_url)
            
            # Only process links from the same domain
            if parsed_url.netloc == self.domain:
                # Convert to relative path
                path = parsed_url.path
                if not path:
                    path = '/'
                
                # Adjust relative path based on output location
                rel_path = os.path.relpath('/', os.path.dirname('/' + os.path.relpath(output_path, self.output_dir)))
                if rel_path == '.':
                    rel_path = ''
                
                if path == '/':
                    a_tag['href'] = f"{rel_path}/"
                else:
                    a_tag['href'] = f"{rel_path}{path}"
        
        # Process images
        for img_tag in soup.find_all('img', src=True):
            src = img_tag['src']
            absolute_url = urljoin(base_url, src)
            
            # Extract path and filename
            parsed_url = urlparse(absolute_url)
            path = parsed_url.path.lstrip('/')
            
            # Add to assets to download
            self.assets_to_download.add((absolute_url, os.path.join('images', os.path.basename(path))))
            
            # Update src attribute
            rel_path = os.path.relpath('/', os.path.dirname('/' + os.path.relpath(output_path, self.output_dir)))
            if rel_path == '.':
                rel_path = ''
            
            img_tag['src'] = f"{rel_path}images/{os.path.basename(path)}"
            
            # Process srcset if it exists
            if img_tag.get('srcset'):
                srcset_parts = []
                for srcset_part in img_tag['srcset'].split(','):
                    src_parts = srcset_part.strip().split(' ')
                    if len(src_parts) >= 1:
                        src_url = src_parts[0]
                        absolute_src_url = urljoin(base_url, src_url)
                        parsed_src_url = urlparse(absolute_src_url)
                        src_path = parsed_src_url.path.lstrip('/')
                        
                        # Add to assets to download
                        self.assets_to_download.add((absolute_src_url, os.path.join('images', os.path.basename(src_path))))
                        
                        # Update srcset part
                        src_parts[0] = f"{rel_path}images/{os.path.basename(src_path)}"
                        srcset_parts.append(' '.join(src_parts))
                
                img_tag['srcset'] = ', '.join(srcset_parts)
        
        # Process CSS files
        for link_tag in soup.find_all('link', rel='stylesheet', href=True):
            href = link_tag['href']
            absolute_url = urljoin(base_url, href)
            
            # Extract path and filename
            parsed_url = urlparse(absolute_url)
            path = parsed_url.path.lstrip('/')
            
            # Add to assets to download
            self.assets_to_download.add((absolute_url, os.path.join('css', os.path.basename(path))))
            
            # Update href attribute
            rel_path = os.path.relpath('/', os.path.dirname('/' + os.path.relpath(output_path, self.output_dir)))
            if rel_path == '.':
                rel_path = ''
            
            link_tag['href'] = f"{rel_path}css/{os.path.basename(path)}"
        
        # Process JavaScript files
        for script_tag in soup.find_all('script', src=True):
            src = script_tag['src']
            absolute_url = urljoin(base_url, src)
            
            # Extract path and filename
            parsed_url = urlparse(absolute_url)
            path = parsed_url.path.lstrip('/')
            
            # Add to assets to download
            self.assets_to_download.add((absolute_url, os.path.join('js', os.path.basename(path))))
            
            # Update src attribute
            rel_path = os.path.relpath('/', os.path.dirname('/' + os.path.relpath(output_path, self.output_dir)))
            if rel_path == '.':
                rel_path = ''
            
            script_tag['src'] = f"{rel_path}js/{os.path.basename(path)}"
        
        return soup
    
    def download_asset(self, url_path_tuple):
        """
        Download an asset from the Webflow site.
        
        Args:
            url_path_tuple (tuple): (URL, local path) of the asset to download
        """
        url, local_path = url_path_tuple
        full_path = os.path.join(self.output_dir, local_path)
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        try:
            response = self.session.get(url, stream=True)
            response.raise_for_status()
            
            # Add delay to avoid rate limiting
            time.sleep(self.delay)
            
            with open(full_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"Downloaded {url} to {local_path}")
        except Exception as e:
            print(f"Error downloading {url}: {e}")
    
    def detect_cms_collections(self, soup, url):
        """
        Detect CMS collections in the page.
        
        Args:
            soup (BeautifulSoup): The BeautifulSoup object of the page
            url (str): The URL of the page
        """
        # Look for collection data in the HTML
        collection_items = soup.select('[data-wf-collection]')
        for item in collection_items:
            collection_id = item.get('data-wf-collection')
            if collection_id:
                print(f"Found collection: {collection_id} on page {url}")
                
                # Look for item slugs
                item_slug = None
                if 'data-wf-item-slug' in item.attrs:
                    item_slug = item.get('data-wf-item-slug')
                    print(f"Found item slug: {item_slug}")
                
                # Store CMS page info
                if collection_id not in self.cms_pages:
                    self.cms_pages[collection_id] = []
                
                if item_slug:
                    self.cms_pages[collection_id].append({
                        'url': url,
                        'slug': item_slug
                    })
    
    def crawl_site(self):
        """
        Crawl the Webflow site and download all pages and assets.
        """
        print(f"Starting crawl of {self.base_url}")
        
        # Download the homepage
        soup, html_content = self.download_page(self.base_url, os.path.join(self.output_dir, 'index.html'))
        if not soup:
            print("Failed to download homepage. Exiting.")
            return
        
        # Process the homepage
        soup = self.process_html(soup, self.base_url, os.path.join(self.output_dir, 'index.html'))
        
        # Save the processed homepage
        with open(os.path.join(self.output_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(str(soup))
        
        # Detect CMS collections
        self.detect_cms_collections(soup, self.base_url)
        
        # Find all links on the homepage
        links_to_crawl = []
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if href.startswith('#') or href.startswith('mailto:') or href.startswith('tel:'):
                continue
                
            absolute_url = urljoin(self.base_url, href)
            parsed_url = urlparse(absolute_url)
            
            # Only process links from the same domain
            if parsed_url.netloc == self.domain:
                path = parsed_url.path
                if not path:
                    path = '/'
                
                # Skip the homepage since we already processed it
                if path == '/':
                    continue
                
                # Determine output path
                if path.endswith('/'):
                    output_path = os.path.join(self.output_dir, path.lstrip('/'), 'index.html')
                else:
                    # Check if it's a file or directory
                    if '.' in os.path.basename(path):
                        output_path = os.path.join(self.output_dir, path.lstrip('/'))
                    else:
                        output_path = os.path.join(self.output_dir, path.lstrip('/'), 'index.html')
                
                links_to_crawl.append((absolute_url, output_path))
        
        # Crawl all links
        for url, output_path in links_to_crawl:
            soup, html_content = self.download_page(url, output_path)
            if soup:
                # Process the page
                soup = self.process_html(soup, url, output_path)
                
                # Save the processed page
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(str(soup))
                
                # Detect CMS collections
                self.detect_cms_collections(soup, url)
        
        # Download all assets
        print(f"Downloading {len(self.assets_to_download)} assets...")
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            executor.map(self.download_asset, self.assets_to_download)
        
        # Save CMS pages info
        if self.cms_pages:
            with open(os.path.join(self.output_dir, 'cms_pages.json'), 'w', encoding='utf-8') as f:
                json.dump(self.cms_pages, f, indent=2)
            
            print(f"Saved CMS pages info to {os.path.join(self.output_dir, 'cms_pages.json')}")
        
        print("Crawl complete!")

def main():
    parser = argparse.ArgumentParser(description='Reflow - A Webflow site exporter/scraper')
    parser.add_argument('url', help='The URL of the Webflow site to export')
    parser.add_argument('--output', '-o', default='output', help='The directory to save the exported site')
    parser.add_argument('--workers', '-w', type=int, default=5, help='Maximum number of concurrent download workers')
    parser.add_argument('--delay', '-d', type=float, default=0.2, help='Delay between requests to avoid rate limiting')
    
    args = parser.parse_args()
    
    exporter = ReflowExporter(args.url, args.output, args.workers, args.delay)
    exporter.crawl_site()

if __name__ == '__main__':
    main() 