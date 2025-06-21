import requests

# Use localhost instead of 127.0.0.1
url = "http://localhost:8000/api/children/"
headers = {"Authorization": "Token eee4ce7a5c950c02f1eaa48afaf87fd85f23b25d"}

try:
    print("Attempting to connect to API...")
    response = requests.get(url, headers=headers, timeout=5)
    
    if response.status_code == 200:
        print("\nAPI Request Successful! Status: 200 OK")
        print("Response Data:")
        print(response.json())
    else:
        print(f"\nRequest Failed. Status Code: {response.status_code}")
        print("Response Content:")
        print(response.text)
        
except requests.exceptions.ConnectionError:
    print("\nError: Could not connect to the server. Please check:")
    print("- Is the Django server running?")
    print("- Are you using the correct URL?")
except requests.exceptions.Timeout:
    print("\nError: Request timed out. Server might be busy.")
except Exception as e:
    print(f"\nAn unexpected error occurred: {str(e)}")

print("\nTest complete.")