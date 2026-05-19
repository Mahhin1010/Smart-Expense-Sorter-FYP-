import requests

API_KEY = "AIzaSyAXQ3v0H6G6piB5SxDCG9znjpslXJRwnd4" # Note the lowercase l at the end
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={API_KEY}"

payload = {
    "contents": [{"parts": [{"text": "Explain how AI works in a few words"}]}]
}
headers = {"Content-Type": "application/json"}

try:
    response = requests.post(URL, json=payload, headers=headers)
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.text}")
except Exception as e:
    print(f"Request failed: {e}")
