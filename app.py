import os
import re
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup

# -------------------------------------------------------------------
# Logging setup
# -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("sc-court-scraper")

# -------------------------------------------------------------------
# Flask app + CORS
# -------------------------------------------------------------------
app = Flask(__name__)
CORS(app)  # You can later restrict origins if needed.

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------
COUNTY_URLS = {
    "Clarendon": "https://www.clerkoftrialcourt.com/Clarendon/search_results.php",
    "Lee": "https://www.clerkoftrialcourt.com/Lee/search_results.php",
    "Sumter": "https://www.clerkoftrialcourt.com/Sumter/search_results.php",
    "Williamsburg": "https://www.clerkoftrialcourt.com/Williamsburg/search_results.php",
}

MAX_WORKERS = int(os.getenv("MAX_WORKERS", len(COUNTY_URLS)))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 30))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# -------------------------------------------------------------------
# Requests session with retries (more robust than raw requests.post)
# -------------------------------------------------------------------
session = requests.Session()

retry_config = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
)

adapter = HTTPAdapter(max_retries=retry_config)
session.mount("http://", adapter)
session.mount("https://", adapter)


# -------------------------------------------------------------------
# Scraper logic
# -------------------------------------------------------------------
def scrape_county(county_name: str, url: str, search_name: str) -> dict:
    """
    Perform a POST search on a single county's court record website.
    Returns a dict with either:
      { "county": <name>, "results": [ ... ] }
      or
      { "county": <name>, "error": "<message>" }
    """
    logger.info(f"[{county_name}] Starting scrape for search_name={search_name!r}")
    results = []

    payload = {
        "search_type": "P",  # Search by party/person
        "party_name": search_name,
        "submit": "Search",
    }

    try:
        resp = session.post(url, data=payload, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "html.parser")

        # Find the main search results table
        search_results_table = soup.find("table", {"summary": "Search Results"})
        if not search_results_table:
            # Explicit "no records" message
            no_records_msg = soup.find(
                string=re.compile(
                    r"No records found matching your search criteria", re.IGNORECASE
                )
            )
            if no_records_msg:
                logger.info(f"[{county_name}] No records found.")
                return {"county": county_name, "results": []}

            logger.warning(
                f"[{county_name}] No search results table or 'no records' message found. "
                "Site structure may have changed."
            )
            return {"county": county_name, "results": []}

        tbody = search_results_table.find("tbody")
        rows = tbody.find_all("tr") if tbody else search_results_table.find_all("tr")

        # Skip header row if present
        if len(rows) > 1:
            rows = rows[1:]
        else:
            rows = []

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            try:
                case_link = cols[0].find("a")
                case_number = (
                    case_link.text.strip() if case_link else cols[0].get_text(strip=True)
                )

                raw_case_url = case_link.get("href") if case_link else None
                case_url = urljoin(url, raw_case_url) if raw_case_url else None

                date = cols[1].get_text(strip=True)
                party = cols[2].get_text(strip=True)
                case_type = cols[3].get_text(strip=True)
                status = cols[4].get_text(strip=True)

                results.append(
                    {
                        "county": county_name,
                        "caseNumber": case_number,
                        "date": date,
                        "party": party,
                        "type": case_type,
                        "status": status,
                        "url": case_url,
                    }
                )
            except Exception as e:
                logger.error(f"[{county_name}] Error parsing row: {e}")
                continue

        logger.info(f"[{county_name}] Scrape complete. {len(results)} record(s) found.")
        return {"county": county_name, "results": results}

    except requests.exceptions.HTTPError as e:
        logger.error(f"[{county_name}] HTTP error: {e}")
        return {"county": county_name, "error": f"HTTP error: {e}"}
    except requests.exceptions.RequestException as e:
        logger.error(f"[{county_name}] Connection error: {e}")
        return {"county": county_name, "error": f"Connection error: {e}"}
    except Exception as e:
        logger.exception(f"[{county_name}] Unexpected error during scraping: {e}")
        return {"county": county_name, "error": f"Unexpected error: {e}"}


# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify(
        {
            "status": "ok",
            "service": "SC Court Scraper API",
            "message": "Use /api/scan?name=LAST,FIRST to search.",
        }
    )


@app.route("/api/scan", methods=["GET"])
def scan_courts():
    """
    Search all configured counties concurrently for a given name.
    Example: GET /api/scan?name=DOE,JOHN
    """
    search_name = request.args.get("name")
    if not search_name:
        return jsonify({"error": "Missing 'name' parameter."}), 400

    # Simple normalization (trim extra spaces)
    normalized_name = " ".join(search_name.split())
    logger.info(f"Scan requested for name={normalized_name!r}")

    results_by_county = {}
    errors = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(scrape_county, county, url, normalized_name): county
            for county, url in COUNTY_URLS.items()
        }

        for future in as_completed(futures):
            county = futures[future]
            try:
                result = future.result()
            except Exception as e:
                logger.exception(f"[{county}] Unhandled exception: {e}")
                errors[county] = f"Unhandled exception: {e}"
                continue

            if "error" in result:
                errors[county] = result["error"]
            else:
                results_by_county[county] = result.get("results", [])

    response = {
        "query": normalized_name,
        "queriedAt": datetime.utcnow().isoformat() + "Z",
        "counties": list(COUNTY_URLS.keys()),
        "results": results_by_county,
    }
    if errors:
        response["errors"] = errors

    return jsonify(response), 200


if __name__ == "__main__":
    # Local dev server; Render will use gunicorn instead.
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
