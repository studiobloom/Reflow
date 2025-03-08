#!/usr/bin/env python3
"""
Reflow - A Webflow site exporter/scraper

This tool downloads a Webflow site and repackages it into a static site.
It preserves the structure, styling, and CMS content with advanced features.
"""

import os
import re
import json
import time
import shutil
import argparse
import requests
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('reflow')

class Reflow:
    def __init__(self, url, output_dir, max_workers=5, delay=0.2, process_cms=True, process_css=True, create_zip=True, log_level=logging.INFO, log_file=None):
        """
        Initialize the Reflow exporter.
        
        Args:
            url (str): The URL of the Webflow site to export
            output_dir (str): The directory to save the exported site
            max_workers (int): Maximum number of concurrent download workers
            delay (float): Delay between requests to avoid rate limiting
            process_cms (bool): Whether to process CMS collections
            process_css (bool): Whether to process CSS files (False means retain original URLs)
            create_zip (bool): Whether to create a ZIP archive
            log_level (int): Logging level (logging.DEBUG, INFO, ERROR)
            log_file (str): Path to log file (optional)
        """
        self.base_url = url.rstrip('/')
        self.output_dir = output_dir
        self.max_workers = max_workers
        self.delay = delay
        self.process_cms = process_cms
        self.process_css = not process_css  # Invert the logic since True now means retain original URLs
        self.create_zip = create_zip
        
        # Set up logging
        logger.setLevel(log_level)
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(file_handler)
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        self.visited_urls = set()
        self.assets_to_download = set()
        self.cms_pages = {}
        self.cms_collections = {}
        
        # Parse the domain from the URL
        parsed_url = urlparse(self.base_url)
        self.domain = parsed_url.netloc
        
        # Determine the working directory
        if self.create_zip:
            # If creating a ZIP, use a temporary directory
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.working_dir = os.path.join(os.path.dirname(output_dir), f"temp_export_{timestamp}")
        else:
            # If not creating a ZIP, use the output directory directly
            self.working_dir = output_dir
            
        # Create working directory
        os.makedirs(self.working_dir, exist_ok=True)
    
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
            logger.info(f"Downloading page: {url}")
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
            logger.error(f"Error downloading {url}: {e}")
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
        # Get the relative path from the output file to the root
        rel_path_to_root = os.path.relpath('/', os.path.dirname('/' + os.path.relpath(output_path, self.working_dir)))
        if rel_path_to_root == '.':
            rel_path_to_root = ''
        
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
                
                if path == '/':
                    a_tag['href'] = f"{rel_path_to_root}/"
                else:
                    a_tag['href'] = f"{rel_path_to_root}{path}"
        
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
            img_tag['src'] = f"{rel_path_to_root}images/{os.path.basename(path)}"
            
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
                        src_parts[0] = f"{rel_path_to_root}images/{os.path.basename(src_path)}"
                        srcset_parts.append(' '.join(src_parts))
                
                img_tag['srcset'] = ', '.join(srcset_parts)
        
        # Process CSS files
        if self.process_css:
            for link_tag in soup.find_all('link', rel='stylesheet', href=True):
                href = link_tag['href']
                absolute_url = urljoin(base_url, href)
                
                # Extract path and filename
                parsed_url = urlparse(absolute_url)
                path = parsed_url.path.lstrip('/')
                
                # Add to assets to download
                self.assets_to_download.add((absolute_url, os.path.join('css', os.path.basename(path))))
                
                # Update href attribute
                link_tag['href'] = f"{rel_path_to_root}css/{os.path.basename(path)}"
        
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
            script_tag['src'] = f"{rel_path_to_root}js/{os.path.basename(path)}"
        
        # Process inline styles with background images
        for tag in soup.find_all(style=True):
            style = tag['style']
            # Find all background-image: url(...) patterns
            bg_images = re.findall(r'background-image\s*:\s*url\([\'"]?([^\'"]+)[\'"]?\)', style)
            for bg_image in bg_images:
                absolute_url = urljoin(base_url, bg_image)
                parsed_url = urlparse(absolute_url)
                path = parsed_url.path.lstrip('/')
                
                # Add to assets to download
                self.assets_to_download.add((absolute_url, os.path.join('images', os.path.basename(path))))
                
                # Update style attribute
                style = style.replace(bg_image, f"{rel_path_to_root}images/{os.path.basename(path)}")
            
            tag['style'] = style
        
        # Process favicon
        favicon_tags = soup.find_all('link', rel=['icon', 'shortcut icon'])
        for favicon_tag in favicon_tags:
            if 'href' in favicon_tag.attrs:
                href = favicon_tag['href']
                absolute_url = urljoin(base_url, href)
                
                # Extract path and filename
                parsed_url = urlparse(absolute_url)
                path = parsed_url.path.lstrip('/')
                
                # Add to assets to download
                self.assets_to_download.add((absolute_url, os.path.join('images', os.path.basename(path))))
                
                # Update href attribute
                favicon_tag['href'] = f"{rel_path_to_root}images/{os.path.basename(path)}"
        
        return soup
    
    def process_css(self, css_content, base_url, css_path):
        """
        Process CSS content to fix asset URLs.
        
        Args:
            css_content (str): The CSS content to process
            base_url (str): The base URL of the CSS file
            css_path (str): The path where the CSS file will be saved
            
        Returns:
            str: The processed CSS content
        """
        if not self.process_css:
            return css_content
            
        # Get the relative path from the CSS file to the root
        rel_path_to_root = os.path.relpath('/', os.path.dirname('/' + os.path.relpath(css_path, self.working_dir)))
        if rel_path_to_root == '.':
            rel_path_to_root = ''
        
        # Find all url(...) patterns
        url_patterns = re.findall(r'url\([\'"]?([^\'"]+)[\'"]?\)', css_content)
        for url_pattern in url_patterns:
            # Skip data URLs
            if url_pattern.startswith('data:'):
                continue
            
            # Skip URLs with variables
            if '${' in url_pattern or '$(' in url_pattern:
                continue
            
            absolute_url = urljoin(base_url, url_pattern)
            parsed_url = urlparse(absolute_url)
            path = parsed_url.path.lstrip('/')
            
            # Add to assets to download
            self.assets_to_download.add((absolute_url, os.path.join('images', os.path.basename(path))))
            
            # Update URL in CSS
            css_content = css_content.replace(f'url({url_pattern})', f'url({rel_path_to_root}images/{os.path.basename(path)})')
            css_content = css_content.replace(f"url('{url_pattern}')", f"url('{rel_path_to_root}images/{os.path.basename(path)}')")
            css_content = css_content.replace(f'url("{url_pattern}")', f'url("{rel_path_to_root}images/{os.path.basename(path)}")')
        
        return css_content
    
    def download_asset(self, url_path_tuple):
        """
        Download an asset from the Webflow site.
        
        Args:
            url_path_tuple (tuple): (URL, local path) of the asset to download
        """
        url, local_path = url_path_tuple
        full_path = os.path.join(self.working_dir, local_path)
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        try:
            # Skip if file already exists
            if os.path.exists(full_path):
                logger.info(f"Asset already exists: {local_path}")
                return
            
            logger.info(f"Downloading asset: {url} to {local_path}")
            response = self.session.get(url, stream=True)
            response.raise_for_status()
            
            # Add delay to avoid rate limiting
            time.sleep(self.delay)
            
            with open(full_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Process CSS files if enabled
            if self.process_css and local_path.startswith('css/') and local_path.endswith('.css'):
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    css_content = f.read()
                
                processed_css = self.process_css(css_content, url, full_path)
                
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(processed_css)
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
    
    def detect_cms_collections(self, soup, url):
        """
        Detect CMS collections in the page.
        
        Args:
            soup (BeautifulSoup): The BeautifulSoup object of the page
            url (str): The URL of the page
        """
        if not self.process_cms:
            return
            
        # Look for collection data in the HTML
        collection_items = soup.select('[data-wf-collection]')
        for item in collection_items:
            collection_id = item.get('data-wf-collection')
            if collection_id:
                logger.info(f"Found collection: {collection_id} on page {url}")
                
                # Look for item slugs
                item_slug = None
                if 'data-wf-item-slug' in item.attrs:
                    item_slug = item.get('data-wf-item-slug')
                    logger.info(f"Found item slug: {item_slug}")
                
                # Store CMS page info
                if collection_id not in self.cms_pages:
                    self.cms_pages[collection_id] = []
                
                if item_slug:
                    self.cms_pages[collection_id].append({
                        'url': url,
                        'slug': item_slug
                    })
        
        # Look for collection list components
        collection_lists = soup.select('.w-dyn-list')
        for collection_list in collection_lists:
            # Try to find collection ID
            collection_id = None
            collection_bind = collection_list.get('bind')
            if collection_bind:
                # This is a more advanced way to detect collection IDs
                self.cms_collections[collection_bind] = {
                    'url': url,
                    'type': 'collection_list'
                }
            
            # Look for collection items
            collection_items = collection_list.select('.w-dyn-item')
            if collection_items:
                logger.info(f"Found collection list with {len(collection_items)} items on page {url}")
    
    def extract_cms_paths(self):
        """
        Extract CMS paths from the detected collections.
        
        Returns:
            list: List of (URL, output path) tuples for CMS pages
        """
        if not self.process_cms:
            return []
            
        cms_paths = []
        
        for collection_id, items in self.cms_pages.items():
            for item in items:
                url = item['url']
                slug = item['slug']
                
                # Parse the URL to get the path
                parsed_url = urlparse(url)
                path = parsed_url.path
                
                # Determine the collection path pattern
                if path.endswith(f"/{slug}"):
                    # The URL already contains the slug
                    collection_path = path[:-(len(slug) + 1)]
                else:
                    # The URL doesn't contain the slug, assume it's a template
                    collection_path = path
                
                # Find other items in the same collection
                for other_item in items:
                    if other_item['slug'] != slug:
                        other_slug = other_item['slug']
                        other_url = f"{self.base_url}{collection_path}/{other_slug}"
                        
                        # Determine output path
                        output_path = os.path.join(self.working_dir, collection_path.lstrip('/'), other_slug, 'index.html')
                        
                        cms_paths.append((other_url, output_path))
        
        return cms_paths
    
    def crawl_site(self):
        """
        Crawl the Webflow site and download all pages and assets.
        """
        try:
            logger.info(f"Starting crawl of {self.base_url}")
            
            # Download the homepage
            soup, html_content = self.download_page(self.base_url, os.path.join(self.working_dir, 'index.html'))
            if not soup:
                logger.error("Failed to download homepage. Exiting.")
                return
            
            # Process the homepage
            soup = self.process_html(soup, self.base_url, os.path.join(self.working_dir, 'index.html'))
            
            # Save the processed homepage
            with open(os.path.join(self.working_dir, 'index.html'), 'w', encoding='utf-8') as f:
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
                        output_path = os.path.join(self.working_dir, path.lstrip('/'), 'index.html')
                    else:
                        # Check if it's a file or directory
                        if '.' in os.path.basename(path):
                            output_path = os.path.join(self.working_dir, path.lstrip('/'))
                        else:
                            output_path = os.path.join(self.working_dir, path.lstrip('/'), 'index.html')
                    
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
            
            # Process CMS pages if enabled
            if self.process_cms:
                cms_paths = self.extract_cms_paths()
                logger.info(f"Found {len(cms_paths)} CMS pages to crawl")
                
                for url, output_path in cms_paths:
                    soup, html_content = self.download_page(url, output_path)
                    if soup:
                        # Process the page
                        soup = self.process_html(soup, url, output_path)
                        
                        # Save the processed page
                        with open(output_path, 'w', encoding='utf-8') as f:
                            f.write(str(soup))
            
            # Download all assets
            logger.info(f"Downloading {len(self.assets_to_download)} assets...")
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                executor.map(self.download_asset, self.assets_to_download)
            
            # Save CMS pages info if enabled
            if self.process_cms and self.cms_pages:
                with open(os.path.join(self.working_dir, 'cms_pages.json'), 'w', encoding='utf-8') as f:
                    json.dump(self.cms_pages, f, indent=2)
                
                logger.info(f"Saved CMS pages info to {os.path.join(self.working_dir, 'cms_pages.json')}")
            
            # Save CMS collections info if enabled
            if self.process_cms and self.cms_collections:
                with open(os.path.join(self.working_dir, 'cms_collections.json'), 'w', encoding='utf-8') as f:
                    json.dump(self.cms_collections, f, indent=2)
                
                logger.info(f"Saved CMS collections info to {os.path.join(self.working_dir, 'cms_collections.json')}")
            
            # Create ZIP archive if enabled
            if self.create_zip:
                logger.info("Creating ZIP archive...")
                zip_path = self.output_dir if self.output_dir.endswith('.zip') else f"{self.output_dir}.zip"
                
                try:
                    # Create ZIP archive directly
                    shutil.make_archive(
                        os.path.splitext(zip_path)[0],
                        'zip',
                        self.working_dir
                    )
                    logger.info(f"ZIP archive created at: {zip_path}")
                except Exception as e:
                    logger.error(f"Error creating ZIP archive: {e}")
                    raise
                finally:
                    # Clean up working directory if it's temporary
                    if self.working_dir != self.output_dir:
                        shutil.rmtree(self.working_dir)
            
            logger.info("Crawl complete!")
            
        except Exception as e:
            logger.error(f"Error during crawl: {e}")
            # Clean up working directory if it's temporary
            if self.create_zip and os.path.exists(self.working_dir):
                shutil.rmtree(self.working_dir)
            raise

def main():
    parser = argparse.ArgumentParser(description='Reflow - A Webflow site exporter/scraper')
    parser.add_argument('url', help='The URL of the Webflow site to export')
    parser.add_argument('--output', '-o', default='output', help='The directory to save the exported site')
    parser.add_argument('--workers', '-w', type=int, default=5, help='Maximum number of concurrent download workers')
    parser.add_argument('--delay', '-d', type=float, default=0.2, help='Delay between requests to avoid rate limiting')
    parser.add_argument('--no-cms', action='store_true', help='Disable processing CMS collections')
    parser.add_argument('--no-css', action='store_true', help='Disable processing CSS files')
    parser.add_argument('--no-zip', action='store_true', help='Disable creating ZIP archive')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--quiet', '-q', action='store_true', help='Suppress all output except errors')
    parser.add_argument('--log-file', help='Save logs to a file')
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.ERROR
    else:
        log_level = logging.INFO
    
    # Create and run the exporter
    exporter = Reflow(
        args.url,
        args.output,
        max_workers=args.workers,
        delay=args.delay,
        process_cms=not args.no_cms,
        process_css=not args.no_css,
        create_zip=not args.no_zip,
        log_level=log_level,
        log_file=args.log_file
    )
    exporter.crawl_site()

if __name__ == '__main__':
    main() 