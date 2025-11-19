import os
import json
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
# The 'requests' library is typically used for making HTTP calls, 
# but in a real scraper, it would be used to fetch the court website content.
# For this demonstration, we'll use a standard library instead of simulating
# a dependency installation that might fail.

# --- MOCK DATA FOR DEMONSTRATION ---
# In a live system, this data would come from the actual court website scrape.
MOCK_RESULTS_JOSHUA_BLUE = {
    'Clarendon': [
        {'caseNumber': '2024-CP-14-00123', 'date': '08/15/2024', 'party': 'Joshua Blue', 'type': 'Foreclosure', 'status': 'Active', 'url': 'http://courtlink.co/clarendon/123'},
        {'caseNumber': '2023-CD-14-00456', 'date': '12/01/2023', 'party': 'Joshua Blue', 'type': 'Civil Dispute', 'status': 'Disposed', 'url': 'http://courtlink.co/clarendon/456'}
    ],
    'Lee': [],
    'Sumter': [
        {'caseNumber': '2024-CD-43-00789', 'date': '05/20/2024', 'party': 'Joshua Blue', 'type': 'Eviction', 'status': 'Pending', 'url': 'http://courtlink.co/sumter/789'}
    ],
    'Williamsburg': []
}
# ------------------------------------

app = Flask(__name__)
# Enable CORS for all origins, allowing your HTML dashboard to connect from any domain.
CORS(app)

# The list of counties to scan (must match the frontend)
COUNTIES = ['Clarendon', 'Lee', 'Sumter', 'Williamsburg']

def scrape_county_data(county_name: str, search_name: str) -> list:
    """
    SIMULATED SCRAPER FUNCTION:
    In a real application, this function would contain the complex
    logic using libraries like Requests and BeautifulSoup/Selenium 
    to navigate to the specific county court website and scrape the results.
    
    For the purposes of deployment demonstration, this simulates the success/failure 
    and mock data retrieval.
    """
    print(f"--- SIMULATING SCRAPE for {county_name}: Searching for '{search_name}' ---")
    
    # If the user searched for 'Joshua Blue', return the mock data
    if search_name.lower() == 'joshua blue':
        # Simulate a slight delay to mimic web scraping time
        import time
        time.sleep(random.uniform(0.5, 1.5))
        return MOCK_RESULTS_JOSHUA_BLUE.get(county_name, [])

    # For any other name, simulate a "No Records Found" result
    return []


@app.route('/api/scan', methods=['GET'])
def scan_courts():
    """
    Main API endpoint to trigger the multi-county scan.
    """
    search_name = request.args.get('name', '').strip()
    
    if not search_name:
        return jsonify({"error": "Missing 'name' query parameter."}), 400

    print(f"\n[API REQUEST RECEIVED] Starting scan for: '{search_name}'")

    # Dictionary to hold all final results
    all_results = {}
    
    # Iterate through all configured counties and run the simulated scrape
    for county in COUNTIES:
        try:
            # Call the simulated scraping function
            county_results = scrape_county_data(county, search_name)
            all_results[county] = county_results
            print(f"  -> {county}: Found {len(county_results)} record(s).")
            
        except Exception as e:
            # In a real scenario, handle specific scraping errors per county
            print(f"  -> ERROR during scrape of {county}: {str(e)}")
            # Return an empty list or an error flag for the county
            all_results[county] = [] 
    
    print("[API RESPONSE SENT] Scan complete.")
    return jsonify(all_results), 200

@app.route('/', methods=['GET'])
def home():
    """Simple health check endpoint."""
    return "SC Court Monitor API is running. Use /api/scan?name=...", 200

if __name__ == '__main__':
    # When deploying, the hosting platform usually handles the port. 
    # Locally, we use 5000.
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
