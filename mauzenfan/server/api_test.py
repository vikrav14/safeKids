import requests

# API configuration
url = "http://127.0.0.1:8000/api/children/"
headers = {"Authorization": "Token eee4ce7a5c950c02f1eaa48afaf87fd85f23b25d"}

try:
    print("Attempting to connect to API...")
    
    # Make the API request
    response = requests.get(url, headers=headers)
    
    # Check for successful response
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
except Exception as e:
    print(f"\nAn unexpected error occurred: {str(e)}")

print("\nTest complete.")