import requests
import json

# ===========================
# ⚡ EDIT THESE BEFORE RUNNING
# ===========================

session_token = Token TWprd01UY3pNdy5hU1FFV2cuNjJURV9vcWZ1V2NOdFk2Z2ZIZjVraF9ibGlB
campaign_name = "Thailand Floods 2025"
campaign_description = "Mapping flood-affected areas in Southern Thailand for disaster response."
organisations = [1]  # HOT organization ID

# ===========================
# Send POST request
# ===========================
api_url = "https://tasks.hotosm.org/api/v2/campaigns/"  # ✅ Fixed URL
headers = {
    "Authorization": session_token,
    "Accept-Language": "en",
    "Content-Type": "application/json"
}

campaign_data = {
    "name": campaign_name,
    "logo": campaign_logo,
    "url": campaign_url,
    "description": campaign_description,
    "organisations": organisations
}

try:
    print("🚀 Creating campaign...")
    response = requests.post(api_url, headers=headers, json=campaign_data)
    
    if response.status_code == 201:
        print("✅ Campaign created successfully!")
        print("📋 Response:")
        print(json.dumps(response.json(), indent=2))
    elif response.status_code == 409:
        print("⚠️ Campaign with this name already exists.")
    elif response.status_code == 401:
        print("❌ Invalid session token. Please check your authorization.")
    elif response.status_code == 403:
        print("❌ You don't have permission to create campaigns.")
    elif response.status_code == 400:
        print("❌ Bad request. Check your parameters.")
        print(response.json())
    else:
        print(f"❌ Error {response.status_code}: {response.text}")
        
except requests.exceptions.ConnectionError:
    print("❌ Connection error. Check your internet connection.")
except Exception as e:
    print(f"❌ Exception occurred: {str(e)}")

input("\nPress Enter to exit...")
