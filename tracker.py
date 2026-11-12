import datetime, json, os, time, urllib.error, urllib.request
import xml.etree.ElementTree as ET

THRESHOLD = 67                            # % of a party that must agree for a party position
CAUCUS = {"D": "D", "R": "R", "I": "D"}   # independents measured against Democrats
YES, NO = {"Yea", "Aye"}, {"Nay", "No"}
DATA = "data"

def load(name, default):
    path = os.path.join(DATA, name)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default

def save(name, obj):
    with open(os.path.join(DATA, name), "w") as f:
        json.dump(obj, f)

def fetch(year, roll):
    url = f"https://clerk.house.gov/evs/{year}/roll{roll:03d}.xml"
    req = urllib.request.Request(url, headers={"User-Agent": "vote-tracker"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            root = ET.fromstring(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except ET.ParseError:
        return None
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root

def tier(question, desc):
    q, d = question.lower(), desc.lower()
    if any(k in q for k in ("quorum", "adjourn", "journal", "speaker", "call of the house")):
        return 3
    if "providing for consideration" in d or any(k in q for k in ("previous question", "recommit", "table")):
        return 2
    return 1

def process(year, roll, root):
    meta = root.find(".//vote-metadata")
    if meta is None:
        print("Unexpected format for roll", roll, "- root tag:", root.tag)
        print(ET.tostring(root)[:800])
        raise SystemExit(1)
    question = meta.findtext("vote-question", "")
    desc = meta.findtext("vote-desc", "")
    info = {"roll": roll, "year": year, "date": meta.findtext("action-date", ""),
            "bill": meta.findtext("legis-num", ""), "question": question,
            "tier": tier(question, desc),
