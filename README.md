# Custom EPG Auto‑Builder (from your M3U)

This repo **builds a custom XMLTV EPG** that matches the channels in **your M3U** and publishes it at a **stable URL** you can paste into TiviMate, Kodi/Jellyfin, Channels DVR, etc.

## What it does

- Downloads **your M3U** (you set `M3U_URL`).
- Downloads a **large public EPG** (country‑wide) and **filters/remaps** it to only the channels in your M3U (using `tvg-id` first, then a smart name match).
- Saves the result to `epg/epg.xml` on `main` and keeps it updated on a schedule (every 6 hours by default).

## One‑time setup

1) Create a new GitHub repo and upload these files (keep folder structure).  
2) In the repo, set **Actions → Variables**:
   - `M3U_URL` = your playlist URL (example: `http://m3u4u.com/m3u/m/w5798zj3yjayqzm8k4n1`)
   - (optional) `EPG_REGION` = one of: `ALL`, `US`, `CA`, `UK`, `AU`, `MX` … (default `US`)
3) Ensure **Actions** are allowed (Settings → Actions → General).  
4) Run the workflow once manually (Actions → “Build Custom EPG” → “Run workflow”).

## Your permanent EPG URL

After the first successful run, your guide will be here:
```
https://raw.githubusercontent.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPO>/main/epg/epg.xml
```

Paste that in your player’s **EPG URL** field. (Playlist URL stays your original M3U.)

## Notes

- Uses the public EPG from epg.pw (country files) then filters to your channels.
- Prioritizes matching by `tvg-id`. If missing, falls back to fuzzy name matching (punctuation/spacing‑insensitive).
- If you want a different source (like iptv‑org/epg), you can add more sources in the workflow with extra URLs.
