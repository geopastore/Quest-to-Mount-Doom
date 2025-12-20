from flask import Flask, redirect, request, render_template
import requests
import sqlite3
import time
import pandas as pd
import os

app = Flask(__name__)

# ======================
# CONFIG
# ======================
CLIENT_ID = os.environ["STRAVA_CLIENT_ID"]
CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
STRAVA_UPDATE_ACTIVITY_URL = "https://www.strava.com/api/v3/activities/{}"
DB_FILE = "db.sqlite"
MILESTONES_FILE = "milestones.csv"


# ======================
# HELPER FUNCTIONS
# ======================

def refresh_access_token(refresh_token):
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    r = requests.post(STRAVA_TOKEN_URL, data=payload)
    data = r.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": data["expires_at"]
    }


def get_access_token(user):
    if time.time() >= user["expires_at"]:
        print(f"Access token expired for athlete {user['athlete_id']} → refreshing...")
        tokens = refresh_access_token(user["refresh_token"])
        # update DB
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""
            UPDATE users
            SET access_token=?, refresh_token=?, expires_at=?
            WHERE athlete_id=?
        """, (tokens["access_token"], tokens["refresh_token"], tokens["expires_at"], user["athlete_id"]))
        conn.commit()
        conn.close()
        return tokens["access_token"]
    return user["access_token"]


def load_milestones():
    df = pd.read_csv(MILESTONES_FILE)
    return df.sort_values("Miles")


def find_current_stage(total_miles, milestones_df):
    reached = milestones_df[milestones_df["Miles"] <= total_miles]
    return reached.iloc[-1]["Where"] if not reached.empty else "The Shire"


def get_activities(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    r = requests.get(STRAVA_ACTIVITIES_URL, headers=headers, params={"per_page": 200})
    return r.json()


def compute_cumulative_distance(activities, start_date):
    total_m = 0
    for a in activities:
        activity_date = a["start_date"][:10]
        if activity_date >= start_date:
            total_m += a.get("distance", 0)
    return total_m / 1609.34  # miles


def append_activity_description(activity, text, access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    existing = activity.get("description") or ""
    updated = existing + "\n\n" + text if existing else text
    url = STRAVA_UPDATE_ACTIVITY_URL.format(activity["id"])
    r = requests.put(url, headers=headers, data={"description": updated})
    print("Updated activity:", r.json())


def update_all_users():
    milestones = load_milestones()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT athlete_id, access_token, refresh_token, expires_at, auth_date FROM users")
    users = [
        {
            "athlete_id": row[0],
            "access_token": row[1],
            "refresh_token": row[2],
            "expires_at": row[3],
            "auth_date": row[4]
        } for row in c.fetchall()
    ]
    conn.close()

    for user in users:
        access_token = get_access_token(user)
        activities = get_activities(access_token)
        if not activities:
            print(f"No activities for athlete {user['athlete_id']}")
            continue

        total_miles = compute_cumulative_distance(activities, user["auth_date"])
        stage = find_current_stage(total_miles, milestones)
        latest_activity = activities[0]

        text = (
            f"Quest to Mount Doom ⭕🌋\n"
            f"Reached: {stage}\n"
            f"Total Journey: {total_miles:.1f} mi ({total_miles*1.609:.1f} km)\n"
            f"Start Date: {user['auth_date']} — app by G.Pastore"
        )

        append_activity_description(latest_activity, text, access_token)


# ======================
# FLASK ROUTES
# ======================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/authorize")
def authorize():
    redirect_uri = os.environ["BASE_URL"] + "/callback"
    strava_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
        f"&approval_prompt=auto"
        f"&scope=activity:read_all,activity:write"
    )
    return redirect(strava_url)


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Error: No code provided"

    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code"
    }
    r = requests.post(STRAVA_TOKEN_URL, data=payload)
    data = r.json()

    if "athlete" not in data:
        return f"Error: {data}"

    athlete_id = data["athlete"]["id"]
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    expires_at = data["expires_at"]
    auth_date = time.strftime("%Y-%m-%d", time.gmtime())

    # Save to DB
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id INTEGER UNIQUE,
            access_token TEXT,
            refresh_token TEXT,
            expires_at INTEGER,
            auth_date TEXT
        )
    """)
    c.execute("""
        INSERT OR REPLACE INTO users
        (athlete_id, access_token, refresh_token, expires_at, auth_date)
        VALUES (?, ?, ?, ?, ?)
    """, (athlete_id, access_token, refresh_token, expires_at, auth_date))
    conn.commit()
    conn.close()

    # Update immediately after authorization
    update_all_users()

    return f"Authorization successful! Athlete ID: {athlete_id}"


# ======================
# RUN APP
# ======================
if __name__ == "__main__":
    app.run()
