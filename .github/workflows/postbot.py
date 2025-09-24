import os
import requests
import openai
import schedule
import time
import json
from dotenv import load_dotenv

# -------------------------
# Load environment variables
# -------------------------
load_dotenv()
LINKEDIN_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN")
COMPANY_URN = os.getenv("COMPANY_URN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

CALENDAR_FILE = "content_calendar.json"

# -------------------------
# 1. Generate Post Content
# -------------------------
def generate_post():
    prompt = """
    Generate a professional LinkedIn post (around 150 words) for a company called AiecoOne.
    Focus on AI, worker safety, oil & gas industry innovations, and ESG compliance.
    Include a catchy start and an actionable takeaway.
    """
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )
    return response.choices[0].message.content.strip()

# -------------------------
# 2. Generate AI Image
# -------------------------
def generate_image(post_text, week):
    prompt = f"Create a professional, realistic image for this LinkedIn post:\n{post_text}"
    response = openai.Image.create(prompt=prompt, n=1, size="1024x1024")
    image_url = response['data'][0]['url']

    # Download image locally
    image_path = f"linkedin_post_image_week{week}.png"
    image_data = requests.get(image_url).content
    with open(image_path, "wb") as f:
        f.write(image_data)
    return image_path

# -------------------------
# 3. Upload Image to LinkedIn
# -------------------------
def upload_image_to_linkedin(image_path):
    register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    payload = {
        "registerUploadRequest": {
            "owner": COMPANY_URN,
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "serviceRelationships": [
                {"identifier": "urn:li:userGeneratedContent", "relationshipType": "OWNER"}
            ],
            "supportedUploadMechanism": ["SYNCHRONOUS_UPLOAD"]
        }
    }
    res = requests.post(register_url, json=payload, headers=headers).json()
    upload_url = res['value']['uploadMechanism']['com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
    asset_urn = res['value']['asset']

    with open(image_path, "rb") as f:
        upload_res = requests.put(upload_url, data=f.read(), headers={"Authorization": f"Bearer {LINKEDIN_TOKEN}"})
    if upload_res.status_code in [200, 201]:
        return asset_urn
    else:
        print("❌ Failed to upload image:", upload_res.text)
        return None

# -------------------------
# 4. Post to LinkedIn with image
# -------------------------
def post_to_linkedin(post_text, asset_urn=None):
    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    payload = {
        "author": COMPANY_URN,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post_text},
                "shareMediaCategory": "NONE" if not asset_urn else "IMAGE",
                "media": [] if not asset_urn else [{"status": "READY", "description": {"text": ""}, "media": asset_urn, "title": {"text": ""}}]
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 201:
        print("✅ LinkedIn post published successfully!")
        return True
    else:
        print("❌ Failed to post:", response.status_code, response.text)
        return False

# -------------------------
# 5. Generate monthly content calendar
# -------------------------
def generate_monthly_calendar():
    if os.path.exists(CALENDAR_FILE):
        print("Calendar already exists. Skipping generation.")
        return
    calendar = []
    for week in range(1, 5):
        print(f"Generating post for week {week}...")
        post_text = generate_post()
        image_path = generate_image(post_text, week)
        calendar.append({
            "week": week,
            "text": post_text,
            "image": image_path,
            "posted": False
        })
    with open(CALENDAR_FILE, "w") as f:
        json.dump(calendar, f, indent=2)
    print("✅ Monthly content calendar generated!")

# -------------------------
# 6. Publish next unposted weekly content
# -------------------------
def publish_weekly_post():
    if not os.path.exists(CALENDAR_FILE):
        generate_monthly_calendar()

    with open(CALENDAR_FILE, "r") as f:
        calendar = json.load(f)

    for post in calendar:
        if not post["posted"]:
            print(f"Publishing week {post['week']} post...")
            asset_urn = upload_image_to_linkedin(post["image"])
            success = post_to_linkedin(post["text"], asset_urn)
            if success:
                post["posted"] = True
                with open(CALENDAR_FILE, "w") as f:
                    json.dump(calendar, f, indent=2)
            break
    else:
        print("All posts for this month have been published!")

# -------------------------
# Schedule weekly job
# -------------------------
schedule.every().monday.at("10:00").do(publish_weekly_post)

print("LinkedIn automation agent with monthly content calendar started...")
while True:
    schedule.run_pending()
    time.sleep(60)
