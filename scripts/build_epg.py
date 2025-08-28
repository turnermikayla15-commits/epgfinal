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

# Terms to strip from names for easier matching
STRIP_TOKENS = [
    r"\bhd\b", r"\bsd\b", r"\bfhd\b", r"\b4k\b", r"\buhd\b",
    r"\beast\b", r"\bwest\b", r"\bmtv\b(?=\d)",  # keep plain MTV
    r"\bus\b", r"\busa\b",
    r"\bchannel\b", r"\bnetwork\b", r"\btv\b",
    r"\bfeed\b", r"\balt\b",
]

# e.g., "CNN (US) HD West" -> "cnn"
def norm(s: str) -> str:
    s = unidecode(s or "")
    s = s.lower()
    s = re.sub(r"\(.*?\)", " ", s)       # remove parentheticals
    s = re.sub(r"[^a-z0-9]+", " ", s)    # keep alnum as spaces
    for t in STRIP_TOKENS:
        s = re.sub(t, " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def base_variants(name: str):
    """Generate a few reasonable variants to improve matching."""
    n = norm(name)
    out = {n}
    # Remove trailing 'east/west' words if present (already normalized)
    out.add(re.sub(r"\b(east|west)\b", "", n).strip())
    # Common network suffixes
    out.add(re.sub(r"\b(us|usa)\b", "", n).strip())
    # Compress spaces
    out = {re.sub(r"\s+", " ", v).strip() for v in out if v}
    return {v for v in out if v}

def load_epg(url):
    print(f"Downloading EPG: {url}")
    r = http_get(url)
    data = r.content
    if url.endswith(".gz") or "gzip" in r.headers.get("Content-Type",""):
        try:
            data = gzip.decompress(data)
        except OSError:
            pass
    root = etree.fromstring(data)
    return root

def index_epg_channels(epg_root):
    """Build indexes for id and names -> channel id."""
    id_set = set()
    name_index = {}  # normalized name -> set(channel_ids)
    for ch in epg_root.findall("channel"):
        cid = (ch.get("id") or "").strip()
        if not cid:
            continue
        id_set.add(cid)
        names = [e.text or "" for e in ch.findall("display-name")]
        for nm in names:
            for v in base_variants(nm):
                name_index.setdefault(v, set()).add(cid)
    return id_set, name_index

def match_channels(m3u_channels, id_set, name_index):
    keep_ids = set()
    matched = 0
    id_hits = 0
    name_hits = 0

    for c in m3u_channels:
        # 1) Exact by tvg-id
        cid = c.get("id","").strip()
        if cid and cid in id_set:
            keep_ids.add(cid)
            matched += 1
            id_hits += 1
            continue

        # 2) Looser by name variants
        nm = c.get("name","").strip()
        if not nm:
            continue
        candidates = set()
        variants = base_variants(nm)
        for v in variants:
            if v in name_index:
                candidates |= name_index[v]

        # 2a) If multiple candidates, try to narrow by containment heuristic
        if len(candidates) > 1:
            n = norm(nm)
            narrowed = {cid for cid in candidates if n in base_variants(next(iter(base_variants(nm))))}
            if narrowed:
                candidates = narrowed

        if candidates:
            # choose one deterministically (alphabetical) to avoid flip-flop
            chosen = sorted(candidates)[0]
            keep_ids.add(chosen)
            matched += 1
            name_hits += 1

    return keep_ids, matched, id_hits, name_hits

def filter_epg(epg_root, keep_channel_ids):
    before_ch = len(epg_root.findall("channel"))
    before_pr = len(epg_root.findall("programme"))

    for ch in list(epg_root.findall("channel")):
        if ch.get("id") not in keep_channel_ids:
            epg_root.remove(ch)

    for prog in list(epg_root.findall("programme")):
        if prog.get("channel") not in keep_channel_ids:
            epg_root.remove(prog)

    after_ch = len(epg_root.findall("channel"))
    after_pr = len(epg_root.findall("programme"))
    print(f"Filter EPG: channels {before_ch} → {after_ch}, programmes {before_pr} → {after_pr}")
    return epg_root

def build_once(region_code: str):
    epg_url = REGION_URLS.get(region_code, REGION_URLS["US"])
    epg_root = load_epg(epg_url)

    # Get playlist
    print(f"Downloading M3U: {M3U_URL}")
    m3u = http_get(M3U_URL).text
    chans = parse_m3u(m3u)

    if not chans:
        print("❌ No channels parsed from M3U.", file=sys.stderr)
        return set(), epg_root, 0, 0, 0

    id_set, name_index = index_epg_channels(epg_root)
    keep_ids, matched, id_hits, name_hits = match_channels(chans, id_set, name_index)

    print(f"Match summary [{region_code}]:")
    print(f"  Playlist channels: {len(chans)}")
    print(f"  Matched channels : {matched}  (by id: {id_hits}, by name: {name_hits})")

    return keep_ids, epg_root, len(chans), id_hits, name_hits

def main():
    # First try requested REGION (default US)
    keep_ids, epg_root, total, id_hits, name_hits = build_once(REGION)

    # If nothing matched, fall back to ALL regions (bigger dataset)
    if not keep_ids:
        print("No matches found for region; falling back to ALL regions…")
        keep_ids, epg_root, total, id_hits, name_hits = build_once("ALL")

    # If still nothing, write a minimal file to avoid 0-byte pushes
    os.makedirs("epg", exist_ok=True)
    out = "epg/epg.xml"

    if not keep_ids:
        print("⚠️ Still no matches. Writing the unfiltered EPG header to epg.xml (empty guide).")
        xml = etree.tostring(epg_root, encoding="utf-8", xml_declaration=True)
        with open(out, "wb") as f:
            f.write(xml)
        print(f"✅ Wrote {out} ({len(xml)} bytes)")
        return

    # Filter and write
    epg_root = filter_epg(epg_root, keep_ids)
    xml = etree.tostring(epg_root, encoding="utf-8", xml_declaration=True)
    with open(out, "wb") as f:
        f.write(xml)
    print(f"✅ Wrote {out} ({len(xml)} bytes)")

if __name__ == "__main__":
    main()
