import base64, requests, os

def get_token():
    cid = os.getenv("SPOTIFY_CLIENT_ID")
    sec = os.getenv("SPOTIFY_CLIENT_SECRET")
    auth = base64.b64encode(f"{cid}:{sec}".encode()).decode()

    r = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {auth}"},
        data={"grant_type": "client_credentials"},
    )
    r.raise_for_status()
    return r.json()["access_token"]

def search_track(artist, track):
    token = get_token()
    q = f'artist:"{artist}" track:"{track}"'

    r = requests.get(
        "https://api.spotify.com/v1/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": q, "type": "track", "limit": 1},
    )
    r.raise_for_status()
    return r.json()

print(search_track("Annie Lennox", "No More I Love You's"))
