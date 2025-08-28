import os, re, sys, io, gzip, requests
from lxml import etree
from unidecode import unidecode

M3U_URL = os.environ.get("M3U_URL", "").strip()
REGION = os.environ.get("EPG_REGION", "US").upper()

if not M3U_URL:
    print("❌ M3U_URL variable not set. Set it in Actions → Variables.", file=sys.stderr)
    sys.exit(1)

# Region → epg.pw URL mapping
REGION_URLS = {
    "ALL": "https://epg.pw/xmltv/epg.xml",
    "US":  "https://epg.pw/xmltv/epg_US.xml",
    "CA":  "https://epg.pw/xmltv/epg_CA.xml",
    "UK":  "https://epg.pw/xmltv/epg_UK.xml",
    "AU":  "https://epg.pw/xmltv/epg_AU.xml",
    "MX":  "https://epg.pw/xmltv/epg_MX.xml",
}

def http_get(url):
    r = requests.get(url, timeout=60, allow_redirects=True)
    r.raise_for_status()
    return r

def parse_m3u(text):
    """Return list of channels with keys: name, id (tvg-id), logo, group, url"""
    chs, current = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            attrs = {}
            for m in re.finditer(r'(\w+(?:-\w+)*)="([^"]*)"', line):
                attrs[m.group(1)] = m.group(2)
            m = re.search(r",([^,].*)$", line)
            disp = (m.group(1).strip() if m else "") or attrs.get("tvg-name","")
            current = {
                "name": attrs.get("tvg-name") or disp,
                "id": attrs.get("tvg-id") or "",
                "logo": attrs.get("tvg-logo") or "",
                "group": attrs.get("group-title") or ""
            }
        elif line.startswith("http"):
            if current:
                current["url"] = line
                chs.append(current)
                current = None
    return chs

# --- Name normalization helpers (loose matching) ---

# Terms
