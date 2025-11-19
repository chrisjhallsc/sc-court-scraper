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
    """
    try:
        session = requests.Session()
        
        # Step 1: Get the page to load cookies/tokens
        response = session.get(base_url, timeout=10)
        
        # Step 2: Prepare the search payload
        # NOTE: Field names are based on standard SCCourts forms, but may need
        # minor adjustment if the website HTML changes.
        payload = {
            'SearchBox': search_name,
            'btnSearch': 'Search' 
        }
        
        # Step 3: Post the search
        post_response = session.post(base_url, data=payload, timeout=10)
        
        # Step 4: Parse Results with BeautifulSoup
        soup = BeautifulSoup(post_response.text, 'html.parser')
        
        results = []
        
        # Find the results table (this selector is an EXAMPLE)
        table = soup.find('table', {'id': 'css_grid'}) 
        
        if table:
            rows = table.find_all('tr')[1:] # Skip header
            for row in rows:
                cols = row.find_all('td')
                if len(cols) > 3:
                    results.append({
                        'caseNumber': cols[0].text.strip(),
                        'date': cols[1].text.strip(),
                        'party': cols[2].text.strip(),
                        'type': cols[3].text.strip(),
                        'status': cols[4].text.strip() if len(cols) > 4 else 'Unknown',
                        'url': base_url 
                    })
                    
        return {'county': county_name, 'data': results, 'status': 'success'}

    except Exception as e:
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
