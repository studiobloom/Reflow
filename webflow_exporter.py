#!/usr/bin/env python3
"""
Webflow Exporter - A tool to export Webflow sites to static HTML

This tool downloads a Webflow site and repackages it into a static site,
preserving the structure, styling, and CMS content.
"""

import os
import re
import json
import time
import shutil
import argparse
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
from concurrent.futures import ThreadPoolExecutor
import zipfile

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('webflow_exporter')

class WebflowExporter:
    def __init__(self, url, output_dir, max_workers=5, delay=0.2, follow_cms=True, process_css=True):
        """
        Initialize the Webflow exporter.
        
        Args:
            url (str): The URL of the Webflow site to export
            output_dir (str): The directory to save the exported site
            max_workers (int): Maximum number of concurrent download workers
            delay (float): Delay between requests to avoid rate limiting
            follow_cms (bool): Whether to follow and process CMS collection pages
            process_css (bool): Whether to process CSS files to fix asset URLs
        """
        self.base_url = url.rstrip('/')
        self.output_dir = output_dir
        self.max_workers = max_workers
        self.delay = delay
        self.follow_cms = follow_cms
        self.process_css = process_css
        
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
        
        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)
    
    def download_page(self, url, output_path=None):
        """
        Download a page from the Webflow site.
        
        Args:
            url (str): The URL of the page to download
            output_path (str, optional): The path to save the page to (deprecated)
            
        Returns:
            tuple: (BeautifulSoup object, HTML content)
        """
        if url in self.visited_urls:
            return None, None
        
        # Try without .html first if it ends with .html
        original_url = url
        if url.endswith('.html'):
            url = url[:-5]
        
        try:
            logger.info(f"Downloading page: {url}")
            response = self.session.get(url)
            response.raise_for_status()
            
            # Add delay to avoid rate limiting
            time.sleep(self.delay)
            
            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Add the successful URL to visited
            self.visited_urls.add(url)
            if original_url != url:
                self.visited_urls.add(original_url)  # Add both versions to visited
            
            return soup, html_content
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            
            # If we tried without .html and it failed, try with .html
            if not url.endswith('.html') and original_url.endswith('.html'):
                try:
                    logger.info(f"Retrying with .html: {original_url}")
                    response = self.session.get(original_url)
                    response.raise_for_status()
                    
                    # Add delay to avoid rate limiting
                    time.sleep(self.delay)
                    
                    html_content = response.text
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Add the successful URL to visited
                    self.visited_urls.add(original_url)
                    
                    return soup, html_content
                except Exception as e:
                    logger.error(f"Error downloading {original_url}: {e}")
            
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
        # Get the relative path from output directory to the page
        rel_dir = os.path.dirname(os.path.relpath(output_path, self.output_dir))
        
        # Process links (a tags)
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            
            # Skip empty, javascript, and anchor links
            if not href or href.startswith('javascript:') or href.startswith('#'):
                continue
            
            # Convert to absolute URL
            abs_url = urljoin(base_url, href)
            parsed_url = urlparse(abs_url)
            
            # Only process links to the same domain
            if parsed_url.netloc == self.domain:
                # Get the path without query parameters
                path = parsed_url.path
                
                # Fix the link to point to the local file
                if path == '/':
                    rel_path = os.path.join('/' if rel_dir else '', 'index.html')
                else:
                    # Remove trailing slash
                    if path.endswith('/'):
                        path = path[:-1]
                    
                    # Add .html extension if missing
                    if not path.endswith('.html'):
                        path = f"{path}.html"
                    
                    rel_path = os.path.join('/' if rel_dir else '', path.lstrip('/'))
                
                a_tag['href'] = rel_path
        
        # Process images
        for img_tag in soup.find_all('img', src=True):
            src = img_tag['src']
            
            # Skip data URLs
            if src.startswith('data:'):
                continue
            
            # Convert to absolute URL
            abs_url = urljoin(base_url, src)
            
            # Get the path for the asset
            parsed_url = urlparse(abs_url)
            path = parsed_url.path
            
            # Create the local path for the asset
            local_path = os.path.join(self.output_dir, path.lstrip('/'))
            
            # Add to assets to download
            self.assets_to_download.add((abs_url, local_path))
            
            # Fix the src attribute
            rel_path = os.path.join('/' if rel_dir else '', path.lstrip('/'))
            img_tag['src'] = rel_path
        
        # Process CSS links
        for link_tag in soup.find_all('link', rel='stylesheet', href=True):
            href = link_tag['href']
            
            # Convert to absolute URL
            abs_url = urljoin(base_url, href)
            
            # Get the path for the asset
            parsed_url = urlparse(abs_url)
            path = parsed_url.path
            
            # Create the local path for the asset
            local_path = os.path.join(self.output_dir, path.lstrip('/'))
            
            # Add to assets to download
            self.assets_to_download.add((abs_url, local_path))
            
            # Fix the href attribute
            rel_path = os.path.join('/' if rel_dir else '', path.lstrip('/'))
            link_tag['href'] = rel_path
        
        # Process JavaScript
        for script_tag in soup.find_all('script', src=True):
            src = script_tag['src']
            
            # Skip external scripts
            if src.startswith('http') and self.domain not in src:
                continue
            
            # Convert to absolute URL
            abs_url = urljoin(base_url, src)
            
            # Get the path for the asset
            parsed_url = urlparse(abs_url)
            path = parsed_url.path
            
            # Create the local path for the asset
            local_path = os.path.join(self.output_dir, path.lstrip('/'))
            
            # Add to assets to download
            self.assets_to_download.add((abs_url, local_path))
            
            # Fix the src attribute
            rel_path = os.path.join('/' if rel_dir else '', path.lstrip('/'))
            script_tag['src'] = rel_path
        
        # Process inline styles with background images
        for tag in soup.find_all(style=True):
            style = tag['style']
            
            # Find all background-image URLs
            bg_images = re.findall(r'background-image:\s*url\([\'"]?([^\'"]+)[\'"]?\)', style)
            
            for bg_image in bg_images:
                # Skip data URLs
                if bg_image.startswith('data:'):
                    continue
                
                # Convert to absolute URL
                abs_url = urljoin(base_url, bg_image)
                
                # Get the path for the asset
                parsed_url = urlparse(abs_url)
                path = parsed_url.path
                
                # Create the local path for the asset
                local_path = os.path.join(self.output_dir, path.lstrip('/'))
                
                # Add to assets to download
                self.assets_to_download.add((abs_url, local_path))
                
                # Fix the URL in the style
                rel_path = os.path.join('/' if rel_dir else '', path.lstrip('/'))
                style = style.replace(bg_image, rel_path)
            
            tag['style'] = style
        
        # Process favicon
        for link_tag in soup.find_all('link', rel=lambda r: r and ('icon' in r or 'shortcut' in r), href=True):
            href = link_tag['href']
            
            # Convert to absolute URL
            abs_url = urljoin(base_url, href)
            
            # Get the path for the asset
            parsed_url = urlparse(abs_url)
            path = parsed_url.path
            
            # Create the local path for the asset
            local_path = os.path.join(self.output_dir, path.lstrip('/'))
            
            # Add to assets to download
            self.assets_to_download.add((abs_url, local_path))
            
            # Fix the href attribute
            rel_path = os.path.join('/' if rel_dir else '', path.lstrip('/'))
            link_tag['href'] = rel_path
        
        return soup
    
    def process_css_file(self, css_content, base_url, css_path):
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
        
        # Find all URLs in the CSS
        url_pattern = re.compile(r'url\([\'"]?([^\'"]+)[\'"]?\)')
        urls = url_pattern.findall(css_content)
        
        for url in urls:
            # Skip data URLs
            if url.startswith('data:'):
                continue
            
            # Convert to absolute URL
            abs_url = urljoin(base_url, url)
            
            # Get the path for the asset
            parsed_url = urlparse(abs_url)
            path = parsed_url.path
            
            # Create the local path for the asset
            local_path = os.path.join(self.output_dir, path.lstrip('/'))
            
            # Add to assets to download
            self.assets_to_download.add((abs_url, local_path))
            
            # Calculate the relative path from the CSS file to the asset
            css_dir = os.path.dirname(css_path)
            rel_path = os.path.relpath(local_path, css_dir)
            
            # Fix the URL in the CSS
            css_content = css_content.replace(f'url({url})', f'url({rel_path})')
            css_content = css_content.replace(f"url('{url}')", f"url('{rel_path}')")
            css_content = css_content.replace(f'url("{url}")', f'url("{rel_path}")')
        
        return css_content
    
    def download_asset(self, url_path_tuple):
        """
        Download an asset from the Webflow site.
        
        Args:
            url_path_tuple (tuple): A tuple containing the URL and local path of the asset
            
        Returns:
            bool: True if the asset was downloaded successfully, False otherwise
        """
        url, local_path = url_path_tuple
        
        try:
            # Create the directory if it doesn't exist
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Download the asset
            response = self.session.get(url, stream=True)
            response.raise_for_status()
            
            # Add delay to avoid rate limiting
            time.sleep(self.delay)
            
            # Save the asset
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Process CSS files
            if local_path.endswith('.css') and self.process_css:
                with open(local_path, 'r', encoding='utf-8') as f:
                    css_content = f.read()
                
                # Process the CSS
                processed_css = self.process_css_file(css_content, url, local_path)
                
                # Save the processed CSS
                with open(local_path, 'w', encoding='utf-8') as f:
                    f.write(processed_css)
            
            logger.info(f"Downloaded asset: {url} -> {local_path}")
            return True
        except Exception as e:
            logger.error(f"Error downloading asset {url}: {e}")
            return False
    
    def detect_cms_collections(self, soup, url):
        """
        Detect CMS collections in the page.
        
        Args:
            soup (BeautifulSoup): The BeautifulSoup object of the page
            url (str): The URL of the page
        """
        # Look for collection list elements
        collection_lists = soup.find_all(class_=lambda c: c and 'w-dyn-list' in c.split())
        
        for collection_list in collection_lists:
            # Get the collection ID
            collection_id = collection_list.get('data-wf-collection', '')
            
            if not collection_id:
                continue
            
            # Get the collection items
            collection_items = collection_list.find_all(class_=lambda c: c and 'w-dyn-item' in c.split())
            
            # Initialize the collection if it doesn't exist
            if collection_id not in self.cms_collections:
                self.cms_collections[collection_id] = {
                    'items': [],
                    'pages': []
                }
            
            # Add the page to the collection
            self.cms_collections[collection_id]['pages'].append(url)
            
            # Process collection items
            for item in collection_items:
                # Look for links in the item
                links = item.find_all('a', href=True)
                
                for link in links:
                    href = link['href']
                    
                    # Skip empty, javascript, and anchor links
                    if not href or href.startswith('javascript:') or href.startswith('#'):
                        continue
                    
                    # Convert to absolute URL
                    abs_url = urljoin(url, href)
                    parsed_url = urlparse(abs_url)
                    
                    # Only process links to the same domain
                    if parsed_url.netloc == self.domain:
                        # Get the path without query parameters
                        path = parsed_url.path
                        
                        # Extract the slug from the path
                        slug = path.strip('/').split('/')[-1]
                        
                        # Add the item to the collection
                        item_data = {
                            'url': abs_url,
                            'slug': slug,
                            'path': path
                        }
                        
                        if item_data not in self.cms_collections[collection_id]['items']:
                            self.cms_collections[collection_id]['items'].append(item_data)
                            
                            # Add the page to the CMS pages
                            self.cms_pages[abs_url] = {
                                'collection_id': collection_id,
                                'slug': slug
                            }
    
    def extract_cms_paths(self):
        """
        Extract paths for CMS pages.
        
        Returns:
            list: A list of URLs to crawl
        """
        urls_to_crawl = []
        
        for collection_id, collection_data in self.cms_collections.items():
            for item in collection_data['items']:
                urls_to_crawl.append(item['url'])
        
        return urls_to_crawl
    
    def crawl_site(self):
        """
        Crawl the Webflow site and download all pages and assets.
        """
        logger.info(f"Starting crawl of {self.base_url}")
        
        # Queue of URLs to crawl
        urls_to_crawl = [self.base_url]
        
        # Create a timestamp for the zip file
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        site_name = urlparse(self.base_url).netloc.split('.')[0]
        
        try:
            # Crawl the site
            while urls_to_crawl:
                url = urls_to_crawl.pop(0)
                
                # Skip if already visited
                if url in self.visited_urls:
                    continue
                
                # Parse the URL
                parsed_url = urlparse(url)
                
                # Skip if not the same domain
                if parsed_url.netloc != self.domain:
                    continue
                
                # Get the path without query parameters
                path = parsed_url.path
                
                # Determine the output path
                if path == '/' or path == '/index.html':  # Handle both root and explicit index.html
                    output_path = os.path.join(self.output_dir, 'index.html')
                else:
                    # Remove trailing slash and .html extension
                    if path.endswith('/'):
                        path = path[:-1]
                    if path.endswith('.html'):
                        path = path[:-5]
                    
                    # Special case: if path is empty after stripping, it's the index
                    if not path:
                        output_path = os.path.join(self.output_dir, 'index.html')
                    else:
                        # Add .html extension
                        path = f"{path}.html"
                        output_path = os.path.join(self.output_dir, path.lstrip('/'))
                
                # Download the page
                soup, html_content = self.download_page(url, None)  # Don't save the file yet
                
                if not soup:
                    # Skip this page and continue with the next one
                    continue
                
                # Process the HTML
                processed_soup = self.process_html(soup, url, output_path)
                
                # Save the processed HTML only if we successfully got the page
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(str(processed_soup))
                
                # Detect CMS collections
                self.detect_cms_collections(soup, url)
                
                # Extract links from the page
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']
                    
                    # Skip empty, javascript, and anchor links
                    if not href or href.startswith('javascript:') or href.startswith('#'):
                        continue
                    
                    # Convert to absolute URL
                    abs_url = urljoin(url, href)
                    
                    # Add to the queue
                    if abs_url not in self.visited_urls:
                        # Remove .html extension if present
                        if abs_url.endswith('.html'):
                            abs_url = abs_url[:-5]
                        urls_to_crawl.append(abs_url)
            
            # Extract CMS paths
            if self.follow_cms:
                cms_urls = self.extract_cms_paths()
                
                # Crawl CMS pages
                for url in cms_urls:
                    # Skip if already visited
                    if url in self.visited_urls:
                        continue
                    
                    # Parse the URL
                    parsed_url = urlparse(url)
                    
                    # Skip if not the same domain
                    if parsed_url.netloc != self.domain:
                        continue
                    
                    # Get the path without query parameters
                    path = parsed_url.path
                    
                    # Determine the output path
                    if path == '/':
                        output_path = os.path.join(self.output_dir, 'index.html')
                    else:
                        # Remove trailing slash and .html extension
                        if path.endswith('/'):
                            path = path[:-1]
                        if path.endswith('.html'):
                            path = path[:-5]
                        
                        # Add .html extension
                        path = f"{path}.html"
                        
                        output_path = os.path.join(self.output_dir, path.lstrip('/'))
                    
                    # Download the page
                    soup, html_content = self.download_page(url, None)  # Don't save the file yet
                    
                    if not soup:
                        # Skip this page and continue with the next one
                        continue
                    
                    # Process the HTML
                    processed_soup = self.process_html(soup, url, output_path)
                    
                    # Save the processed HTML only if we successfully got the page
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(str(processed_soup))
            
            # Save CMS data
            with open(os.path.join(self.output_dir, 'cms_pages.json'), 'w', encoding='utf-8') as f:
                json.dump(self.cms_pages, f, indent=2)
            
            with open(os.path.join(self.output_dir, 'cms_collections.json'), 'w', encoding='utf-8') as f:
                json.dump(self.cms_collections, f, indent=2)
            
            # Download assets
            logger.info(f"Downloading {len(self.assets_to_download)} assets")
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                executor.map(self.download_asset, self.assets_to_download)
            
            # Clean up any files without .html extension
            for root, dirs, files in os.walk(self.output_dir):
                for file in files:
                    if not file.endswith('.html') and not file.endswith('.json') and not file.endswith('.css') and not file.endswith('.js') and not file.endswith('.svg') and not file.endswith('.png') and not file.endswith('.jpg') and not file.endswith('.jpeg') and not file.endswith('.gif') and not file.endswith('.ico'):
                        file_path = os.path.join(root, file)
                        html_path = f"{file_path}.html"
                        
                        # If the HTML version exists, delete the non-HTML version
                        if os.path.exists(html_path):
                            try:
                                os.remove(file_path)
                                logger.info(f"Removed duplicate file without .html extension: {file_path}")
                            except Exception as e:
                                logger.error(f"Error removing file {file_path}: {e}")
                        else:
                            # If the HTML version doesn't exist, rename to add .html
                            try:
                                os.rename(file_path, html_path)
                                logger.info(f"Renamed file to add .html extension: {file_path} -> {html_path}")
                            except Exception as e:
                                logger.error(f"Error renaming file {file_path}: {e}")
            
            logger.info(f"Crawl complete! Downloaded {len(self.visited_urls)} pages and {len(self.assets_to_download)} assets")
            
            # Create a zip file of the exported site
            zip_filename = f"{site_name}-{timestamp}.zip"
            logger.info(f"Creating zip archive: {zip_filename}")
            
            def zipdir(path, ziph):
                # Zip the directory
                for root, dirs, files in os.walk(path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, path)
                        ziph.write(file_path, arcname)
            
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipdir(self.output_dir, zipf)
            
            logger.info(f"Zip archive created: {zip_filename}")
            
            # Clean up the output directory
            logger.info("Cleaning up output directory...")
            try:
                shutil.rmtree(self.output_dir)
                logger.info("Output directory cleaned up successfully")
            except Exception as e:
                logger.error(f"Error cleaning up output directory: {e}")
            
        except Exception as e:
            logger.error(f"Error during crawl: {e}")
            raise

def main():
    parser = argparse.ArgumentParser(description='Webflow Exporter - A tool to export Webflow sites to static HTML')
    parser.add_argument('url', help='The URL of the Webflow site to export')
    parser.add_argument('--output', '-o', default='output', help='The directory to save the exported site')
    parser.add_argument('--workers', '-w', type=int, default=5, help='Maximum number of concurrent download workers')
    parser.add_argument('--delay', '-d', type=float, default=0.2, help='Delay between requests to avoid rate limiting')
    parser.add_argument('--no-cms', action='store_true', help='Disable following and processing CMS collection pages')
    parser.add_argument('--no-css-process', action='store_true', help='Disable processing CSS files to fix asset URLs')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--quiet', '-q', action='store_true', help='Suppress all output except errors')
    parser.add_argument('--log-file', help='Save logs to a file')
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.ERROR
    else:
        log_level = logging.INFO
    
    # Set up logging
    logger.setLevel(log_level)
    
    # Add file handler if log file is specified
    if args.log_file:
        file_handler = logging.FileHandler(args.log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output, exist_ok=True)
    
    try:
        # Create the exporter
        exporter = WebflowExporter(
            args.url,
            args.output,
            args.workers,
            args.delay,
            not args.no_cms,
            not args.no_css_process
        )
        
        # Start the crawl
        exporter.crawl_site()
        
        # Print summary
        if not args.quiet:
            print("\nExport Summary:")
            print(f"- Site URL: {args.url}")
            print(f"- Output directory: {args.output}")
            print(f"- Workers: {args.workers}")
            print(f"- Delay: {args.delay} seconds")
            print(f"- CMS processing: {'Disabled' if args.no_cms else 'Enabled'}")
            print(f"- CSS processing: {'Disabled' if args.no_css_process else 'Enabled'}")
            print(f"- Pages downloaded: {len(exporter.visited_urls)}")
            print(f"- Assets downloaded: {len(exporter.assets_to_download)}")
            print(f"- CMS collections detected: {len(exporter.cms_collections)}")
            print("\nExport completed successfully!")
    
    except KeyboardInterrupt:
        logger.error("Export interrupted by user")
        exit(1)
    except Exception as e:
        logger.error(f"Export failed: {e}")
        exit(1)

if __name__ == '__main__':
    main() 