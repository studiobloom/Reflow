# Webflow Exporter

A tool to export Webflow sites to static HTML, preserving the structure, styling, converting CMS to static content.

## Features

- Downloads all pages from a Webflow site
- Preserves the site structure
- Downloads and organizes all assets (images, CSS, JavaScript)
- Detects and extracts CMS collections
- Fixes relative links to work in the exported site
- Processes CSS files to fix asset URLs
- Multithreaded asset downloading for faster exports

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/webflow-exporter.git
   cd webflow-exporter
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Usage

```
python webflow_exporter.py https://your-webflow-site.com
```

This will download the site to the `output` directory by default.

### Command-line Options

- `--output`, `-o`: Specify the output directory (default: `output`)
- `--workers`, `-w`: Maximum number of concurrent download workers (default: 5)
- `--delay`, `-d`: Delay between requests to avoid rate limiting (default: 0.2 seconds)
- `--no-cms`: Disable following and processing CMS collection pages
- `--no-css-process`: Disable processing CSS files to fix asset URLs
- `--verbose`, `-v`: Enable verbose logging
- `--quiet`, `-q`: Suppress all output except errors
- `--log-file`: Save logs to a file

Example with multiple options:
```
python webflow_exporter.py https://your-webflow-site.com --output my-exported-site --workers 10 --delay 0.5 --verbose --log-file export.log
```

## How It Works

1. The exporter starts by downloading the homepage of the Webflow site.
2. It then extracts all links from the homepage and follows them to download all pages.
3. While processing each page, it identifies assets (images, CSS, JavaScript) and adds them to a download queue.
4. It also detects CMS collections and extracts information about them.
5. After crawling all pages, it downloads all assets using a thread pool for efficiency.
6. Finally, it saves information about CMS collections to JSON files.

## CMS Collections

The exporter detects CMS collections in the Webflow site and saves information about them to two JSON files in the output directory:

1. `cms_pages.json`: Contains information about individual CMS pages, including their collection IDs and slugs.
2. `cms_collections.json`: Contains more detailed information about collections, including their items and the pages they appear on.

## Limitations

- The exporter only downloads pages that are linked from the homepage or other pages in the site. If a page is not linked, it won't be downloaded.
- It doesn't handle authentication, so it can only download public sites.
- Some dynamic features of the site may not work in the exported version.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 