import os, re, sys, io, gzip, requests, datetime
from lxml import etree
from unidecode import unidecode

M3U_URL = os.environ.get("M3U_URL", "").strip()
REGION = os.environ.get("EPG_REGION", "US").upper()

if not M3U_URL:
    print("❌ M3U_URL variable not set. Set it in Actions → Variables.", file=sys.stderr)
    sys.exit(1)

# Region → epg.pw URL mapping (expandable)
REGION_URLS = {
    "ALL": "https://epg.pw/xmltv/epg.xml",
    "US":  "https://epg.pw/xmltv/epg_US.xml",
    "CA":  "https://epg.pw/xmltv/epg_CA.xml",
    "UK":  "https://epg.pw/xmltv/epg_UK.xml",
    "AU":  "https://epg.pw/xmltv/epg_AU.xml",
    "MX":  "https://epg.pw/xmltv/epg_MX.xml",
}
EPG_URL = REGION_URLS.get(REGION, REGION_URLS["US"])

def http_get(url):
    r = requests.get(url, timeout=60, allow_redirects=True)
    r.raise_for_status()
    return r

def parse_m3u(text):
    # Return list of dicts with keys: name, id (tvg-id), logo, group
    chs = []
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            # Extract attributes like tvg-id, tvg-name, tvg-logo, group-title
            attrs = {}
            # Parse key="value" pairs
            for m in re.finditer(r'(\w+(?:-\w+)*)="([^"]*)"', line):
                attrs[m.group(1)] = m.group(2)
            # Display name after comma
            m = re.search(r",([^,].*)$", line)
            disp = m.group(1).strip() if m else ""
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

def norm(s):
    s = unidecode(s or "")
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', '', s)
    return s

def load_epg(url):
    print(f"Downloading EPG: {url}")
    r = http_get(url)
    data = r.content
    if url.endswith(".gz") or (r.headers.get("Content-Type","").endswith("gzip")):
        data = gzip.decompress(data)
    root = etree.fromstring(data)
    return root

def filter_epg(epg_root, wanted_ids, wanted_names):
    # Keep only channels/programmes that match our wanted set
    wanted_norm_names = {norm(n) for n in wanted_names if n}
    wanted_ids_set = set(wanted_ids)

    # Build set of channel ids present
    keep_channel_ids = set()

    # First pass: figure which channels to keep
    for ch in epg_root.findall("channel"):
        cid = ch.get("id") or ""
        name_elems = ch.findall("display-name")
        names = [e.text or "" for e in name_elems]
        # Match by id
        if cid in wanted_ids_set:
            keep_channel_ids.add(cid)
            continue
        # Or by name (normalized)
        for n in names:
            if norm(n) in wanted_norm_names:
                keep_channel_ids.add(cid)
                break

    # Filter channels
    for ch in list(epg_root.findall("channel")):
        if ch.get("id") not in keep_channel_ids:
            epg_root.remove(ch)

    # Filter programmes
    for prog in list(epg_root.findall("programme")):
        if prog.get("channel") not in keep_channel_ids:
            epg_root.remove(prog)

    return epg_root

def main():
    # 1) Download playlist
    print(f"Downloading M3U: {M3U_URL}")
    m3u = http_get(M3U_URL).text

    # 2) Parse channels
    chans = parse_m3u(m3u)
    wanted_ids = [c["id"] for c in chans if c["id"]]
    wanted_names = [c["name"] for c in chans if c["name"]]

    if not wanted_ids and not wanted_names:
        print("❌ No channels parsed from M3U (no tvg-id or names).", file=sys.stderr)
        sys.exit(1)

    # 3) Download region EPG
    epg_root = load_epg(EPG_URL)

    # 4) Filter down to only our channels
    epg_root = filter_epg(epg_root, wanted_ids, wanted_names)

    # 5) Write result
    os.makedirs("epg", exist_ok=True)
    out = "epg/epg.xml"
    xml = etree.tostring(epg_root, encoding="utf-8", xml_declaration=True)
    with open(out, "wb") as f:
        f.write(xml)
    print(f"✅ Wrote {out} ({len(xml)} bytes)")

if __name__ == "__main__":
    main()
