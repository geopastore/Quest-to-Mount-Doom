import requests
import json
import time
import pandas as pd

# ======================
# CONFIGURATION
# ======================
CLIENT_ID = "191002"
CLIENT_SECRET = "495dff09b5b6d4ed7a3ad78a560a8b78b352f8dd"
ATHLETE_ID = "2268957"   # replace with your athlete ID
TOKENS_FILE = "tokens.json"
MILESTONES_FILE = "milestones.csv"

STRAVA_TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
STRAVA_UPDATE_ACTIVITY_URL = "https://www.strava.com/api/v3/activities/{}"

# Start date for the challenge
START_DATE = "2025-12-19"  # YYYY-MM-DD


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
    tokens = {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": data["expires_at"]
    }
    return tokens

def get_access_token():
    tokens = load_tokens()
    if time.time() >= tokens["expires_at"]:
        print("Access token expired → refreshing...")
        tokens = refresh_access_token(tokens["refresh_token"])
        save_tokens(tokens)
    return tokens["access_token"]


# ======================
# MILESTONES HANDLING
# ======================
def load_milestones():
    df = pd.read_csv(MILESTONES_FILE)
    df = df.sort_values("Miles")
    return df

def find_current_stage(total_miles, milestones_df):
    df = milestones_df[milestones_df["Miles"] <= total_miles]
    return df.iloc[-1]["Where"] if not df.empty else "Start your journey!"


# ======================
# STRAVA ACTIVITIES
# ======================
def get_latest_activity(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(STRAVA_ACTIVITIES_URL, headers=headers)
    activities = r.json()
    return activities[0] if activities else None

def compute_cumulative_distance(access_token, athlete_id, start_date):
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(STRAVA_ACTIVITIES_URL, headers=headers, params={"per_page": 200})
    activities = r.json()

    total_m = 0
    for a in activities:
        activity_date = a.get("start_date")[:10]  # YYYY-MM-DD
        if activity_date >= start_date:
            total_m += a.get("distance", 0)  # meters
    return total_m / 1609.34  # convert meters to miles

def update_activity_description(activity_id, description, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {"description": description}
    url = STRAVA_UPDATE_ACTIVITY_URL.format(activity_id)
    r = requests.put(url, headers=headers, data=payload)
    print("Updated activity:", r.json())


# ======================
# MAIN
# ======================
def main():
    access_token = get_access_token()
    milestones = load_milestones()

    total_miles = compute_cumulative_distance(access_token, ATHLETE_ID, START_DATE)
    stage = find_current_stage(total_miles, milestones)

    latest_activity = get_latest_activity(access_token)
    if latest_activity is None:
        print("No activities found since start date.")
        return

    activity_id = latest_activity["id"]

    description = (
        f"Quest to Mount Doom ⭕🌋\n\n"
        f"You reached: **{stage}**!\n"
        f"Total Journey: {total_miles:.1f} miles "
        f"({total_miles*1.609:.1f} km)\n"
        f"Start Date: {START_DATE}"
    )

    update_activity_description(activity_id, description, access_token)


if __name__ == "__main__":
    main()
