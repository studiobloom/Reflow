#!/usr/bin/env python3
"""
Reflow CLI - Command-line interface for Reflow Webflow site exporter/scraper

This script provides a unified command-line interface for both the basic and advanced
versions of the Reflow exporter.
"""

import os
import sys
import argparse
import logging
from reflow import ReflowExporter
from reflow_advanced import ReflowAdvancedExporter, logger

def main():
    parser = argparse.ArgumentParser(description='Reflow - Webflow site exporter/scraper')
    parser.add_argument('url', help='The URL of the Webflow site to export')
    parser.add_argument('--output', '-o', default='output', help='The directory to save the exported site')
    parser.add_argument('--advanced', '-a', action='store_true', help='Use the advanced exporter')
    parser.add_argument('--workers', '-w', type=int, default=5, help='Maximum number of concurrent download workers')
    parser.add_argument('--delay', '-d', type=float, default=0.2, help='Delay between requests to avoid rate limiting')
    parser.add_argument('--no-cms', action='store_true', help='Disable following and processing CMS collection pages (advanced only)')
    parser.add_argument('--no-css-process', action='store_true', help='Disable processing CSS files to fix asset URLs (advanced only)')
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
        if args.advanced:
            logger.info(f"Using advanced exporter to download {args.url} to {args.output}")
            exporter = ReflowAdvancedExporter(
                args.url,
                args.output,
                args.workers,
                args.delay,
                not args.no_cms,
                not args.no_css_process
            )
        else:
            logger.info(f"Using basic exporter to download {args.url} to {args.output}")
            exporter = ReflowExporter(
                args.url,
                args.output,
                args.workers,
                args.delay
            )
        
        # Start the crawl
        exporter.crawl_site()
        
        logger.info(f"Export complete! Site has been saved to {args.output}")
        
        # Print summary
        if not args.quiet:
            print("\nExport Summary:")
            print(f"- Site URL: {args.url}")
            print(f"- Output directory: {args.output}")
            print(f"- Exporter: {'Advanced' if args.advanced else 'Basic'}")
            print(f"- Workers: {args.workers}")
            print(f"- Delay: {args.delay} seconds")
            
            if args.advanced:
                print(f"- CMS processing: {'Disabled' if args.no_cms else 'Enabled'}")
                print(f"- CSS processing: {'Disabled' if args.no_css_process else 'Enabled'}")
            
            if hasattr(exporter, 'visited_urls'):
                print(f"- Pages downloaded: {len(exporter.visited_urls)}")
            
            if hasattr(exporter, 'assets_to_download'):
                print(f"- Assets downloaded: {len(exporter.assets_to_download)}")
            
            if hasattr(exporter, 'cms_pages'):
                print(f"- CMS collections detected: {len(exporter.cms_pages)}")
            
            print("\nExport completed successfully!")
        
    except KeyboardInterrupt:
        logger.error("Export interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Export failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 