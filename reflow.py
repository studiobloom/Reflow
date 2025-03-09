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
    
    def sanitize_filename(self, filename):
        """
        Sanitize a filename by decoding URL-encoded characters and removing/replacing invalid characters.
        
        Args:
            filename (str): The filename to sanitize
            
        Returns:
            str: The sanitized filename
        """
        # First, URL-decode the filename to handle percent-encoded characters
        decoded_filename = unquote(filename)
        
        # Replace problematic characters with underscores
        # This includes characters that are not allowed in filenames on various operating systems
        invalid_chars = r'[<>:"/\\|?*\x00-\x1F]'
        sanitized = re.sub(invalid_chars, '_', decoded_filename)
        
        # Replace spaces with underscores for better compatibility
        sanitized = sanitized.replace(' ', '_')
        
        # Ensure the filename isn't too long (max 255 characters)
        if len(sanitized) > 255:
            name, ext = os.path.splitext(sanitized)
            sanitized = name[:255-len(ext)] + ext
            
        return sanitized
    
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
            # First try with the original URL
            logger.info(f"Downloading page: {url}")
            response = self.session.get(url)
            
            # If we get a 404 and the URL ends with .html, try without it
            if response.status_code == 404 and url.endswith('.html'):
                url_without_html = url[:-5]  # Remove .html
                logger.info(f"404 encountered, retrying without .html: {url_without_html}")
                response = self.session.get(url_without_html)
            
            response.raise_for_status()
            
            # Add delay to avoid rate limiting
            time.sleep(self.delay)
            
            # Ensure correct encoding detection
            if response.encoding is None or response.encoding == 'ISO-8859-1':
                # Try to detect encoding from content
                response.encoding = response.apparent_encoding
            
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
    
    def remove_webflow_badge_from_html(self, soup):
        """
        Remove Webflow badge from HTML content.
        
        Args:
            soup (BeautifulSoup): The BeautifulSoup object of the page
            
        Returns:
            BeautifulSoup: The processed BeautifulSoup object
        """
        logger.info("Removing Webflow badge from HTML...")
        
        # 1. Remove any existing badge elements
        badge_selectors = [
            '.w-webflow-badge',
            'a[href*="webflow.com?utm_campaign=brandjs"]',
            'a.w-webflow-badge'
        ]
        
        for selector in badge_selectors:
            for element in soup.select(selector):
                logger.info(f"Removing badge element: {element}")
                element.decompose()
        
        # 2. Remove any script tags that might add the badge
        for script in soup.find_all('script'):
            if script.string and ('webflow-badge' in script.string or 'createBadge' in script.string):
                logger.info("Removing script tag containing badge code")
                script.decompose()
        
        # 3. Remove any style tags that style the badge
        for style in soup.find_all('style'):
            if style.string and 'w-webflow-badge' in style.string:
                logger.info("Removing style tag containing badge styles")
                style.decompose()
        
        # 4. Remove any images that are part of the badge
        badge_image_patterns = [
            'webflow-badge-icon',
            'webflow-badge-text',
            'd3e54v103j8qbb.cloudfront.net/img/webflow-badge',
            'd1otoma47x30pg.cloudfront.net/img/webflow-badge'
        ]
        
        for img in soup.find_all('img'):
            if 'src' in img.attrs:
                for pattern in badge_image_patterns:
                    if pattern in img['src']:
                        logger.info(f"Removing badge image: {img['src']}")
                        img.decompose()
                        break
        
        return soup
    
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
        # Remove Webflow badge from HTML
        soup = self.remove_webflow_badge_from_html(soup)
        
        # Get the relative path from the output file to the root
        rel_path_to_root = os.path.relpath('/', os.path.dirname('/' + os.path.relpath(output_path, self.working_dir)))
        if rel_path_to_root == '.':
            rel_path_to_root = ''
        
        # Process links
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if href.startswith('#') or href.startswith('mailto:') or href.startswith('tel:'):
                continue
            
            # Handle file protocol URLs
            if href.startswith('file:///'):
                href = href.replace('file:///', '')
                # Extract the path part after the drive letter or root
                path_parts = href.split('/', 1)
                if len(path_parts) > 1:
                    href = '/' + path_parts[1]
                else:
                    href = '/'
            
            # Convert absolute URLs to relative paths
            try:
                absolute_url = urljoin(base_url, href)
                parsed_url = urlparse(absolute_url)
                
                # Only process links from the same domain or local file paths
                if parsed_url.netloc == self.domain or not parsed_url.netloc:
                    # Get the path component
                    path = parsed_url.path
                    if not path:
                        path = '/'
                    
                    # Remove any domain prefix if present
                    if path.startswith(self.domain):
                        path = path[len(self.domain):]
                    
                    # Ensure path starts with /
                    if not path.startswith('/'):
                        path = '/' + path
                    
                    # Update href with relative path
                    if path == '/':
                        a_tag['href'] = f"{rel_path_to_root}/"
                    else:
                        # Remove leading slash for relative path
                        relative_path = path.lstrip('/')
                        if relative_path.endswith('/'):
                            relative_path = relative_path[:-1]
                        if not relative_path.endswith('.html'):
                            relative_path += '.html'
                        a_tag['href'] = f"{rel_path_to_root}{relative_path}"
            except Exception as e:
                logger.warning(f"Error processing link {href}: {e}")
                continue
        
        # Process images
        for img_tag in soup.find_all('img', src=True):
            src = img_tag['src']
            absolute_url = urljoin(base_url, src)
            
            # Skip Webflow badge images
            if 'webflow-badge' in src:
                img_tag.decompose()
                continue
            
            # Extract path and filename
            parsed_url = urlparse(absolute_url)
            path = parsed_url.path.lstrip('/')
            
            # Sanitize the filename
            sanitized_filename = self.sanitize_filename(os.path.basename(path))
            
            # Add to assets to download
            self.assets_to_download.add((absolute_url, os.path.join('images', sanitized_filename)))
            
            # Update src attribute
            img_tag['src'] = f"{rel_path_to_root}images/{sanitized_filename}"
            
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
                        
                        # Sanitize the filename
                        sanitized_src_filename = self.sanitize_filename(os.path.basename(src_path))
                        
                        # Add to assets to download
                        self.assets_to_download.add((absolute_src_url, os.path.join('images', sanitized_src_filename)))
                        
                        # Update srcset part
                        src_parts[0] = f"{rel_path_to_root}images/{sanitized_src_filename}"
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
                
                # Sanitize the filename
                sanitized_filename = self.sanitize_filename(os.path.basename(path))
                
                # Add to assets to download
                self.assets_to_download.add((absolute_url, os.path.join('css', sanitized_filename)))
                
                # Update href attribute
                link_tag['href'] = f"{rel_path_to_root}css/{sanitized_filename}"
        
        # Process JavaScript files
        for script_tag in soup.find_all('script', src=True):
            src = script_tag['src']
            absolute_url = urljoin(base_url, src)
            
            # Extract path and filename
            parsed_url = urlparse(absolute_url)
            path = parsed_url.path.lstrip('/')
            
            # Sanitize the filename
            sanitized_filename = self.sanitize_filename(os.path.basename(path))
            
            # Add to assets to download
            self.assets_to_download.add((absolute_url, os.path.join('js', sanitized_filename)))
            
            # Update src attribute
            script_tag['src'] = f"{rel_path_to_root}js/{sanitized_filename}"
        
        # Process inline styles with background images
        for tag in soup.find_all(style=True):
            style = tag['style']
            # Find all background-image: url(...) patterns
            bg_images = re.findall(r'background-image\s*:\s*url\([\'"]?([^\'"]+)[\'"]?\)', style)
            for bg_image in bg_images:
                absolute_url = urljoin(base_url, bg_image)
                parsed_url = urlparse(absolute_url)
                path = parsed_url.path.lstrip('/')
                
                # Sanitize the filename
                sanitized_filename = self.sanitize_filename(os.path.basename(path))
                
                # Add to assets to download
                self.assets_to_download.add((absolute_url, os.path.join('images', sanitized_filename)))
                
                # Update style attribute
                style = style.replace(bg_image, f"{rel_path_to_root}images/{sanitized_filename}")
            
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
                
                # Sanitize the filename
                sanitized_filename = self.sanitize_filename(os.path.basename(path))
                
                # Add to assets to download
                self.assets_to_download.add((absolute_url, os.path.join('images', sanitized_filename)))
                
                # Update href attribute
                favicon_tag['href'] = f"{rel_path_to_root}images/{sanitized_filename}"
        
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
            
            # Sanitize the filename
            sanitized_filename = self.sanitize_filename(os.path.basename(path))
            
            # Add to assets to download
            self.assets_to_download.add((absolute_url, os.path.join('images', sanitized_filename)))
            
            # Update URL in CSS
            css_content = css_content.replace(f'url({url_pattern})', f'url({rel_path_to_root}images/{sanitized_filename})')
            css_content = css_content.replace(f"url('{url_pattern}')", f"url('{rel_path_to_root}images/{sanitized_filename}')")
            css_content = css_content.replace(f'url("{url_pattern}")', f'url("{rel_path_to_root}images/{sanitized_filename}")')
        
        return css_content
    
    def process_javascript(self, js_content):
        """
        Process JavaScript content to remove Webflow branding.
        
        Args:
            js_content (str): The JavaScript content to process
            
        Returns:
            str: The processed JavaScript content
        """
        logger.info("Processing JavaScript to remove Webflow badge...")
        
        # Check if this is the webflow.js file (contains badge code)
        if 'webflow-badge' in js_content or 'createBadge' in js_content:
            logger.info("Found Webflow badge code, removing...")
            
            # 1. Find and remove the createBadge function
            # This is a more precise approach using string indices
            create_badge_start = js_content.find("function createBadge()")
            if create_badge_start != -1:
                # Find the end of the function (closing brace)
                brace_count = 0
                create_badge_end = create_badge_start
                
                # Start after "function createBadge() {"
                i = js_content.find("{", create_badge_start)
                if i != -1:
                    brace_count = 1
                    i += 1
                    
                    # Find matching closing brace
                    while i < len(js_content) and brace_count > 0:
                        if js_content[i] == "{":
                            brace_count += 1
                        elif js_content[i] == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                create_badge_end = i + 1
                                break
                        i += 1
                    
                    # Remove the function
                    if create_badge_end > create_badge_start:
                        logger.info(f"Removing createBadge function from index {create_badge_start} to {create_badge_end}")
                        js_content = js_content[:create_badge_start] + js_content[create_badge_end:]
            
            # 2. Remove any code that adds the badge to the page
            # Look for patterns like: $body.append(createBadge());
            badge_append_patterns = [
                r'\$\([^)]*\)\.append\(createBadge\(\)\);',
                r'\$body\.append\(createBadge\(\)\);',
                r'body\.appendChild\(createBadge\(\)\);',
                r'document\.body\.appendChild\(createBadge\(\)\);'
            ]
            
            for pattern in badge_append_patterns:
                js_content = re.sub(pattern, '', js_content)
            
            # 3. Remove any CSS related to the badge
            badge_css_patterns = [
                r'\.w-webflow-badge\s*\{[^}]*\}',
                r'\.w-webflow-badge:hover\s*\{[^}]*\}'
            ]
            
            for pattern in badge_css_patterns:
                js_content = re.sub(pattern, '', js_content)
            
            # 4. Disable any code that might dynamically add the badge
            # Replace any remaining references to createBadge with an empty function
            if 'createBadge' in js_content:
                js_content = js_content.replace('createBadge()', 'function(){return null;}()')
            
            logger.info("Webflow badge code removal complete")
        
        return js_content
    
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
            
            # Ensure correct encoding detection for text-based assets
            if not local_path.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico', '.ttf', '.woff', '.woff2', '.eot')):
                # Try to detect encoding from content
                if response.encoding is None or response.encoding == 'ISO-8859-1':
                    response.encoding = response.apparent_encoding
            
            # Add delay to avoid rate limiting
            time.sleep(self.delay)
            
            # Special handling for webflow.js file
            is_webflow_js = 'webflow' in url.lower() and local_path.endswith('.js')
            
            with open(full_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Process CSS files if enabled
            if self.process_css and local_path.startswith('css/') and local_path.endswith('.css'):
                try:
                    # First try UTF-8
                    with open(full_path, 'r', encoding='utf-8') as f:
                        css_content = f.read()
                except UnicodeDecodeError:
                    # If UTF-8 fails, try to detect encoding
                    import chardet
                    with open(full_path, 'rb') as f:
                        raw_data = f.read()
                        detected = chardet.detect(raw_data)
                        encoding = detected['encoding'] or 'utf-8'
                    
                    with open(full_path, 'r', encoding=encoding, errors='replace') as f:
                        css_content = f.read()
                
                processed_css = self.process_css(css_content, url, full_path)
                
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(processed_css)
            
            # Process JavaScript files
            if local_path.startswith('js/') and local_path.endswith('.js'):
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    js_content = f.read()
                
                # Extra thorough processing for webflow.js
                if is_webflow_js:
                    logger.info("Applying special processing for webflow.js file")
                    # Completely disable the badge creation
                    js_content = js_content.replace("function createBadge()", "function createBadge() { return null; }")
                    
                    # Remove any code that appends the badge to the body
                    badge_append_patterns = [
                        r'\$\([\'"]body[\'"]\)\.append\(createBadge\(\)\);',
                        r'\$body\.append\(createBadge\(\)\);',
                        r'body\.appendChild\(createBadge\(\)\);',
                        r'document\.body\.appendChild\(createBadge\(\)\);'
                    ]
                    
                    for pattern in badge_append_patterns:
                        js_content = re.sub(pattern, '', js_content)
                
                processed_js = self.process_javascript(js_content)
                
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(processed_js)
                
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
            soup, html_content = self.download_page(self.base_url)
            if not soup:
                logger.error("Failed to download homepage. Exiting.")
                return
            
            # Process the homepage
            soup = self.process_html(soup, self.base_url, os.path.join(self.working_dir, 'index.html'))
            
            # Save the processed homepage
            with open(os.path.join(self.working_dir, 'index.html'), 'w', encoding='utf-8') as f:
                f.write(soup.prettify(formatter="html"))
            
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
                    
                    # Remove .html from the URL if present (we'll add it back for the output file)
                    if path.endswith('.html'):
                        path = path[:-5]
                    
                    # Remove trailing slash if present
                    if path.endswith('/'):
                        path = path.rstrip('/')
                    
                    # Get the last part of the path as the filename
                    filename = os.path.basename(path)
                    if not filename:
                        filename = path.strip('/')
                    
                    # Add .html to the output filename
                    output_filename = filename + '.html'
                    
                    # Set output path directly in working directory
                    output_path = os.path.join(self.working_dir, output_filename)
                    
                    # Use the URL without .html for crawling
                    crawl_url = urljoin(self.base_url, path)
                    links_to_crawl.append((crawl_url, output_path))
            
            # Crawl all links
            for url, output_path in links_to_crawl:
                soup, html_content = self.download_page(url)
                if soup:
                    # Process the page
                    soup = self.process_html(soup, url, output_path)
                    
                    # Save the processed page
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(soup.prettify(formatter="html"))
                    
                    # Detect CMS collections
                    self.detect_cms_collections(soup, url)
            
            # Process CMS pages if enabled
            if self.process_cms:
                cms_paths = self.extract_cms_paths()
                logger.info(f"Found {len(cms_paths)} CMS pages to crawl")
                
                for url, cms_path in cms_paths:
                    soup, html_content = self.download_page(url)
                    if soup:
                        # Process the page
                        soup = self.process_html(soup, url, cms_path)
                        
                        # Create the directory if it doesn't exist
                        os.makedirs(os.path.dirname(cms_path), exist_ok=True)
                        
                        # Save the processed page
                        with open(cms_path, 'w', encoding='utf-8') as f:
                            f.write(soup.prettify(formatter="html"))
            
            # Download all assets
            if self.assets_to_download:
                logger.info(f"Downloading {len(self.assets_to_download)} assets...")
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    executor.map(self.download_asset, self.assets_to_download)
            
            # Post-processing: Final pass to ensure all webflow.js files are properly modified
            logger.info("Performing final pass to remove Webflow badge...")
            for root, dirs, files in os.walk(self.working_dir):
                for file in files:
                    if file.lower().startswith('webflow') and file.lower().endswith('.js'):
                        js_path = os.path.join(root, file)
                        logger.info(f"Final pass: Processing {js_path}")
                        try:
                            with open(js_path, 'r', encoding='utf-8', errors='ignore') as f:
                                js_content = f.read()
                            
                            # Direct replacement of badge code
                            if 'function createBadge()' in js_content:
                                logger.info(f"Found createBadge function in {file}, replacing with empty function")
                                js_content = js_content.replace(
                                    "function createBadge()",
                                    "function createBadge() { return null; }"
                                )
                                
                                # Also remove any code that appends the badge
                                badge_append_patterns = [
                                    r'\$\([\'"]body[\'"]\)\.append\(createBadge\(\)\);',
                                    r'\$body\.append\(createBadge\(\)\);',
                                    r'body\.appendChild\(createBadge\(\)\);',
                                    r'document\.body\.appendChild\(createBadge\(\)\);',
                                    r'[\w$]+\.append\(createBadge\(\)\);'
                                ]
                                
                                for pattern in badge_append_patterns:
                                    js_content = re.sub(pattern, '', js_content)
                                
                                with open(js_path, 'w', encoding='utf-8') as f:
                                    f.write(js_content)
                        except Exception as e:
                            logger.error(f"Error processing {js_path}: {e}")
            
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