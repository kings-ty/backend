import requests
import json

url = "http://127.0.0.1:8000/api/correctSentence"
data = {"sentence": "I want one babies"} # Example sentence to correct

try:
    response = requests.post(url, json=data)
    response.raise_for_status() # HTTP error handling
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
except requests.exceptions.RequestException as e:
    print(f"error handling: {e}")