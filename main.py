import requests
import json
import time
import os
from datetime import datetime, timezone

import pandas as pd

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
STRAVA_ACTIVITY_URL = "https://www.strava.com/api/v3/activities/{}"  # GET detail + PUT update

START_DATE = "2025-12-19"  # YYYY-MM-DD

# How many of the most recent activities to (re)label each run.
# Bump this to e.g. 15 for a single run to repair older labels, then set it back to 5.
UPDATE_LAST_N = 15

# Marker that identifies the block this script adds to a description.
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
def get_activities(access_token, after_date):
    """Return every activity on or after after_date, paging through the API.

    The list endpoint returns at most 200 activities per request, so we page
    with `page` until an empty page comes back. The `after` filter (epoch
    seconds) keeps us from fetching history older than the quest.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    dt = datetime.strptime(after_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    after_epoch = int(dt.timestamp()) - 86400  # a day of buffer for timezones

    all_activities = []
    page = 1
    while True:
        params = {"per_page": 200, "page": page, "after": after_epoch}
        r = requests.get(STRAVA_ACTIVITIES_URL, headers=headers, params=params)
        batch = r.json()
        if not isinstance(batch, list):
            raise RuntimeError(f"Strava API error while listing activities: {batch}")
        if not batch:                 # empty page means nothing left to fetch
            break
        all_activities.extend(batch)
        page += 1
        time.sleep(1)                 # stay comfortably within the rate limit
    return all_activities

def get_activity_detail(activity_id, access_token):
    """Fetch a single activity, which (unlike the list endpoint) includes the description."""
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(STRAVA_ACTIVITY_URL.format(activity_id), headers=headers)
    return r.json()

def strip_quest_block(description):
    """Remove any previously added Quest block, keeping the athlete's own text."""
    if not description:
        return ""
    idx = description.find(APP_SIGNATURE)
    return description[:idx].rstrip() if idx != -1 else description.rstrip()

def set_activity_description(activity_id, quest_text, access_token):
    """Rewrite an activity's Quest block, preserving anything the athlete wrote.

    Reads the current description first, so the block is replaced rather than
    stacked, and skips the write entirely when nothing would change.
    """
    detail = get_activity_detail(activity_id, access_token)
    current = detail.get("description") or ""
    base = strip_quest_block(current)
    updated = (base + "\n\n" + quest_text) if base else quest_text

    if updated == current:
        print(f"Activity {activity_id} already correct, skipping.")
        return

    headers = {"Authorization": f"Bearer {access_token}"}
    requests.put(STRAVA_ACTIVITY_URL.format(activity_id),
                 headers=headers, data={"description": updated})
    print(f"Updated activity {activity_id}")

# ======================
# MAIN
# ======================
def main():
    access_token = get_access_token()
    milestones = load_milestones()
    activities = get_activities(access_token, START_DATE)

    # Precise trim (the `after` filter is coarse by a day of buffer).
    activities = [a for a in activities if a["start_date"][:10] >= START_DATE]
    if not activities:
        print("No activities found since START_DATE.")
        return

    # Sort by date ascending (oldest first).
    activities_sorted = sorted(activities, key=lambda a: a["start_date"])

    # The most recent activities are the ones we (re)label this run.
    to_update_ids = {a["id"] for a in activities_sorted[-UPDATE_LAST_N:]}

    cumulative_m = 0
    for activity in activities_sorted:
        cumulative_m += activity.get("distance", 0)
        total_miles = cumulative_m / 1609.34
        total_km = cumulative_m / 1000.0
        stage = find_current_stage(total_miles, milestones)

        if activity["id"] in to_update_ids:
            text = (
                f"Quest to Mount Doom ⭕🌋\n"
                f"Reached: {stage}\n"
                f"Total Journey: {total_miles:.1f} mi ({total_km:.1f} km)\n"
                f"Start Date: {START_DATE} app by G.Pastore\n"
                f"\n"
                f"https://geopastore.github.io/Quest-to-Mount-Doom/"
            )
            set_activity_description(activity["id"], text, access_token)

if __name__ == "__main__":
    main()
