import datetime, json, os, time, urllib.error, urllib.request
import xml.etree.ElementTree as ET

THRESHOLD = 67
CAUCUS = {"D": "D", "R": "R", "I": "D"}
YES = {"Yea", "Aye"}
NO = {"Nay", "No"}
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
    q = question.lower()
    d = desc.lower()
    for k in ("quorum", "adjourn", "journal", "speaker", "call of the house"):
        if k in q:
            return 3
    if "providing for consideration" in d:
        return 2
    for k in ("previous question", "recommit", "table"):
        if k in q:
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
    info = {}
    info["roll"] = roll
    info["year"] = year
    info["date"] = meta.findtext("action-date", "")
    info["bill"] = meta.findtext("legis-num", "")
    info["question"] = question
    info["tier"] = tier(question, desc)
    info["impeachment"] = "impeach" in desc.lower()

    members = []
    for rv in root.iter("recorded-vote"):
        leg = rv.find("legislator")
        m = {}
        m["id"] = leg.get("name-id")
        m["name"] = leg.get("unaccented-name") or leg.text
        m["party"] = leg.get("party")
        m["state"] = leg.get("state")
        m["vote"] = rv.findtext("vote", "")
        members.append(m)
