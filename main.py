import requests
import json
import time
import pandas as pd
import os

# ======================
# CONFIGURATION
# ======================
CLIENT_ID = os.environ["STRAVA_CLIENT_ID"]
CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]
ATHLETE_ID = os.environ["ATHLETE_ID"]

TOKENS_FILE = "tokens.json"
MILESTONES_FILE = "milestones.csv"

STRAVA_TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
STRAVA_UPDATE_ACTIVITY_URL = "https://www.strava.com/api/v3/activities/{}"

START_DATE = "2025-12-19"  # YYYY-MM-DD

# Text used to detect already-updated activities
APP_SIGNATURE = "Quest to Mount Doom"

# ======================
# TOKEN HANDLING
# ======================
def load_tokens():
    with open(TOKENS_FILE) as f:
        return json.load(f)

def save_tokens(tokens):
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=4)

def refresh_access_token(refresh_token):
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    r = requests.post(STRAVA_TOKEN_URL, data=payload)
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"Token refresh failed: {data}")
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": data["expires_at"]
    }

def get_access_token():
    tokens = load_tokens()
    if time.time() >= tokens["expires_at"]:
        print("Access token expired → refreshing...")
        tokens = refresh_access_token(tokens["refresh_token"])
        save_tokens(tokens)
    return tokens["access_token"]

# ======================
# MILESTONES
# ======================
def load_milestones():
    df = pd.read_csv(MILESTONES_FILE)
    df.columns = df.columns.str.strip()  # remove extra spaces
    df["Miles"] = pd.to_numeric(df["Miles"], errors="coerce")
    df = df.dropna(subset=["Miles"])
    return df.sort_values("Miles")

def find_current_stage(total_miles, milestones_df):
    reached = milestones_df[milestones_df["Miles"] <= total_miles]
    return reached.iloc[-1]["Where"] if not reached.empty else "The Shire"

# ======================
# STRAVA
# ======================
def get_activities(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(STRAVA_ACTIVITIES_URL, headers=headers, params={"per_page": 200})
    return r.json()

def append_activity_description(activity, text, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    existing = activity.get("description") or ""
    updated = existing + "\n\n" + text if existing else text
    url = STRAVA_UPDATE_ACTIVITY_URL.format(activity["id"])
    r = requests.put(url, headers=headers, data={"description": updated})
    print(f"Updated activity {activity['id']}")

# ======================
# MAIN
# ======================
def main():
    access_token = get_access_token()
    milestones = load_milestones()
    activities = get_activities(access_token)

    if not activities:
        print("No activities found.")
        return

    # Filter only activities since START_DATE
    activities_filtered = [a for a in activities if a["start_date"][:10] >= START_DATE]

    # Sort by date ascending (oldest first)
    activities_sorted = sorted(activities_filtered, key=lambda x: x["start_date"])

    # Only consider last 5 activities
    last_5 = activities_sorted[-5:]

    cumulative_m = 0
    for activity in activities_sorted:
        # Increment cumulative distance
        cumulative_m += activity.get("distance", 0)
        total_miles = cumulative_m / 1609.34
        stage = find_current_stage(total_miles, milestones)

        # Only update if this activity is one of the last 5
        if activity in last_5:
            existing_description = activity.get("description") or ""
            if APP_SIGNATURE in existing_description:
                print(f"Activity {activity['id']} already updated — skipping.")
                continue

            text = (
                f"Quest to Mount Doom ⭕🌋\n"
                f"Reached: {stage}\n"
                f"Total Journey: {total_miles:.1f} mi ({total_miles*1.609:.1f} km)\n"
                f"Start Date: {START_DATE} app by G.Pastore"
            )
            append_activity_description(activity, text, access_token)

if __name__ == "__main__":
    main()
