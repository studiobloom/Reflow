#!/usr/bin/env python3
"""
Test script for Webflow Exporter

This script demonstrates how to use the Webflow Exporter to download a Webflow site.
"""

import os
import sys
import argparse
from webflow_exporter import WebflowExporter

def main():
    parser = argparse.ArgumentParser(description='Test script for Webflow Exporter')
    parser.add_argument('url', help='The URL of the Webflow site to export')
    parser.add_argument('--output', '-o', default='output', help='The directory to save the exported site')
    parser.add_argument('--workers', '-w', type=int, default=5, help='Maximum number of concurrent download workers')
    parser.add_argument('--delay', '-d', type=float, default=0.2, help='Delay between requests to avoid rate limiting')
    parser.add_argument('--no-cms', action='store_true', help='Disable following and processing CMS collection pages')
    parser.add_argument('--no-css-process', action='store_true', help='Disable processing CSS files to fix asset URLs')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output, exist_ok=True)
    
    print(f"Using Webflow Exporter to download {args.url} to {args.output}")
    
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
    
    print(f"Export complete! Site has been saved to {args.output}")
    
    # Print summary
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

if __name__ == '__main__':
    main() 