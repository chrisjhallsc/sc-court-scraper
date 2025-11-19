from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import concurrent.futures

# We use 'app' as the name for the Flask application instance.
app = Flask(__name__)
CORS(app)  # This allows your Dashboard to talk to this server

# Configuration for the 4 counties
COUNTIES = {
    'Clarendon': 'https://publicindex.sccourts.org/clarendon/publicindex/',
    'Lee': 'https://publicindex.sccourts.org/lee/publicindex/',
    'Sumter': 'https://publicindex.sccourts.org/sumter/publicindex/',
    'Williamsburg': 'https://publicindex.sccourts.org/williamsburg/publicindex/'
}

def scrape_county(county_name, base_url, search_name):
    """
    This function visits a specific county URL and searches for the name.
    
    FIX: Now includes logic to extract and submit ASP.NET View State variables
    to properly authenticate the search request.
    """
    try:
        session = requests.Session()
        
        # --- Step 1: Get the page to load cookies/tokens and state variables ---
        response = session.get(base_url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract necessary hidden form fields (ASP.NET ViewState and EventValidation)
        view_state = soup.find('input', {'name': '__VIEWSTATE'})
        event_validation = soup.find('input', {'name': '__EVENTVALIDATION'})
        
        # Check if the required elements exist, otherwise use an empty string
        view_state_value = view_state['value'] if view_state else ''
        event_validation_value = event_validation['value'] if event_validation else ''

        # --- Step 2: Prepare the search payload with extracted state ---
        # The key to fixing the "no records" issue is including these hidden fields.
        payload = {
            '__VIEWSTATE': view_state_value,
            '__EVENTVALIDATION': event_validation_value,
            'SearchBox': search_name,
            'btnSearch': 'Search' 
        }
        
        # --- Step 3: Post the search ---
        # We POST to the base URL with the complete form data
        post_response = session.post(base_url, data=payload, timeout=10)
        
        # --- Step 4: Parse Results with BeautifulSoup ---
        # We parse the response from the POST request
        result_soup = BeautifulSoup(post_response.text, 'html.parser')
        
        results = []
        
        # Find the results table (Standard SCCourts ID is css_grid)
        table = result_soup.find('table', {'id': 'css_grid'})
        
        if table:
            rows = table.find_all('tr')[1:] # Skip header
            for row in rows:
                cols = row.find_all('td')
                # We expect at least 5 columns for case number, date, party, type, and status
                if len(cols) >= 5:
                    # Look for the link within the first column (Case Number)
                    case_link = cols[0].find('a')
                    
                    results.append({
                        'caseNumber': cols[0].text.strip(),
                        'date': cols[1].text.strip(),
                        'party': cols[2].text.strip(),
                        'type': cols[3].text.strip(),
                        # Status is the 5th column (index 4)
                        'status': cols[4].text.strip(),
                        # Use the actual link to the case if found, otherwise the base URL
                        'url': f"{base_url}{case_link['href']}" if case_link and 'href' in case_link.attrs else base_url
                    })
                    
        return {'county': county_name, 'data': results, 'status': 'success'}

    except Exception as e:
        # Note: Added print to help with debugging the Render logs
        print(f"Error scraping {county_name}: {e}")
        return {'county': county_name, 'data': [], 'status': 'error'}

@app.route('/api/scan', methods=['GET'])
def scan_courts():
    """
    The Endpoint your Dashboard calls.
    Usage: /api/scan?name=Smith
    """
    search_name = request.args.get('name')
    if not search_name:
        return jsonify({'error': 'Name parameter required'}), 400

    # Run 4 scrapes in parallel (simultaneous) so it's fast
    combined_results = {}
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Create a list of tasks
        futures = [
            executor.submit(scrape_county, name, url, search_name) 
            for name, url in COUNTIES.items()
        ]
        
        # Gather results as they finish
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            combined_results[result['county']] = result['data']

    return jsonify(combined_results)

if __name__ == '__main__':
    # Run the server
    app.run(debug=True, port=5000)
