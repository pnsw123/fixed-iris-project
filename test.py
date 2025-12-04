import requests
import json

def test_shamela_api(book_id=897):
    print(f"🕵️‍♂️ Testing Access to Shamela API for Book ID: {book_id}...\n")

    # Potential endpoints based on the 'ragaeeb/shamela' repo documentation
    endpoints = [
        f"https://api.shamela.ws/v4/books/{book_id}",      # V4 Endpoint
        f"https://shamela.ws/api/books/{book_id}",         # Standard API
        f"https://api.shamela.ws/v4/books/{book_id}/json"  # Potential JSON specific
    ]

    success = False

    for url in endpoints:
        try:
            print(f"👉 Trying endpoint: {url}")
            # Identify as a browser to avoid simple blocking
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            print(f"   Status Code: {response.status_code}")
            
            if response.status_code == 200:
                print("   ✅ SUCCESS! The door is open.")
                content_type = response.headers.get('Content-Type', '')
                print(f"   Content-Type: {content_type}")
                
                # If it's JSON, we can read it immediately
                if 'json' in content_type:
                    data = response.json()
                    # Print a snippet to prove we have data
                    print("\n   [Data Snippet]:")
                    print(json.dumps(data, indent=2, ensure_ascii=False)[:500] + "\n   ... (truncated)")
                    
                    # Logic to check for specific tribes (Proof of Content)
                    if 'pages' in data:
                        print(f"\n   📚 Found {len(data['pages'])} pages.")
                        search_term = "الغبان"
                        found = any(search_term in page.get('text', '') for page in data['pages'])
                        if found:
                            print(f"   🎯 PROOF: Found family '{search_term}' in the text!")
                
                # If it's a binary file (SQLite/Database), we acknowledge the download
                else:
                    size_mb = len(response.content) / (1024 * 1024)
                    print(f"   📦 Received Binary Data: {size_mb:.2f} MB (Likely a .db or .bok file)")
                    print("   You would need to save this file and open it with an SQLite viewer.")
                
                success = True
                break # Stop after first success
            
            elif response.status_code == 403:
                print("   ⛔ Access Forbidden (403). They might require an API Key or strict headers.")
            elif response.status_code == 404:
                print("   ❌ Endpoint not found (404).")
            else:
                print("   ⚠️ Connection failed or refused.")
                
        except Exception as e:
            print(f"   💥 Error: {e}")
        
        print("-" * 30)

    if not success:
        print("\n🤔 Conclusion: We couldn't access the data directly with simple requests.")
        print("We might need to use the official 'ragaeeb' library which handles the handshake/auth.")

if __name__ == "__main__":
    test_shamela_api()