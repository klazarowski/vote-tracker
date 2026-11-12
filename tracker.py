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
            for el in root.iter():
                if "}" in el.tag: el.tag = el.tag.split("}", 1)[1]
            return root
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except ET.ParseError:
        return None

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
            "tier": tier(question, desc), "impeachment": "impeach" in desc.lower()}

    members = []
    for rv in root.iter("recorded-vote"):
        leg = rv.find("legislator")
        members.append({"id": leg.get("name-id"),
                        "name": leg.get("unaccented-name") or leg.text,
                        "party": leg.get("party"), "state": leg.get("state"),
                        "vote": rv.findtext("vote", "")})

    tally = {}
    for m in members:
        t = tally.setdefault(CAUCUS.get(m["party"], m["party"]), {"yes": 0, "no": 0})
        if m["vote"] in YES: t["yes"] += 1
        elif m["vote"] in NO: t["no"] += 1

    position = {}
    for c, t in tally.items():
        total = t["yes"] + t["no"]
        if total == 0 or t["yes"] == t["no"]:
            position[c] = (None, 0)
        else:
            side = "yes" if t["yes"] > t["no"] else "no"
            position[c] = (side, round(100 * max(t["yes"], t["no"]) / total, 1))

    entries = []
    if info["tier"] == 3:
        return info, entries
    for m in members:
        side, unity = position[CAUCUS.get(m["party"], m["party"])]
        base = {**info, **m, "unity_pct": unity, "party_side": side}
        if m["vote"] not in YES | NO:
            entries.append({**base, "type": "absence"})
        elif side is None or unity < THRESHOLD:
            continue
        elif ("yes" if m["vote"] in YES else "no") != side:
            entries.append({**base, "type": "defection"})
    return info, entries

def main():
    os.makedirs(DATA, exist_ok=True)
    year = datetime.date.today().year
    state = load("state.json", {"year": year, "last_roll": 0})
    if state["year"] != year:
        state = {"year": year, "last_roll": 0}
    votes, log = load("votes.json", []), load("log.json", [])
    roll = state["last_roll"] + 1
    while (root := fetch(year, roll)) is not None:
        info, entries = process(year, roll, root)
        votes.append(info)
        log.extend(entries)
        state["last_roll"] = roll
        roll += 1
        time.sleep(0.3)
    state["checked"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save("state.json", state); save("votes.json", votes); save("log.json", log)

if __name__ == "__main__":
    main()
