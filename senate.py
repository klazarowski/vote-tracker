import datetime, os, time, urllib.error, urllib.request
import xml.etree.ElementTree as ET
from tracker import load, save, CAUCUS, YES, NO, THRESHOLD, DATA

SYES = YES | {"Guilty"}
SNO = NO | {"Not Guilty"}
BASE = "https://www.senate.gov/legislative/LIS/roll_call_votes"


def session_info(year):
    congress = (year - 1789) // 2 + 1
    session = 1 if year % 2 == 1 else 2
    return congress, session


def fetch(congress, session, n):
    url = f"{BASE}/vote{congress}{session}/vote_{congress}_{session}_{n:05d}.xml"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (vote-tracker)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            root = ET.fromstring(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except ET.ParseError:
        return None
    if root.tag != "roll_call_vote" or root.find("members") is None:
        return None
    return root


def tier(question, title):
    q = question.lower()
    t = title.lower()[:80]
    for k in ("quorum", "adjourn", "sergeant at arms"):
        if k in q:
            return 3
    if "cloture" in q:
        return 1
    procedural = ("motion to table", "motion to proceed", "point of order", "motion to discharge",
                  "motion to waive", "motion to recommit", "motion to commit", "motion to postpone")
    for k in procedural:
        if k in q or k in t:
            return 2
    return 1


def process(year, n, root):
    question = root.findtext("question", "")
    title = root.findtext("vote_title", "") or question
    doc = root.findtext("vote_document_text", "")
    parts = " ".join(root.findtext("vote_date", "").split()).split(", ")
    info = {}
    info["chamber"] = "senate"
    info["roll"] = n
    info["year"] = year
    info["date"] = ", ".join(parts[:2])
    info["bill"] = root.findtext("document/document_name", "")
    info["question"] = title[:120]
    info["tier"] = tier(question, title)
    info["impeachment"] = "guilty" in question.lower() or "impeach" in (title + doc).lower()

    members = []
    for mem in root.iter("member"):
        m = {}
        m["id"] = mem.findtext("lis_member_id", "")
        m["name"] = mem.findtext("last_name", "")
        m["party"] = mem.findtext("party", "")
        m["state"] = mem.findtext("state", "")
        m["vote"] = mem.findtext("vote_cast", "")
        members.append(m)

    tally = {}
    for m in members:
        c = CAUCUS.get(m["party"], m["party"])
        t = tally.setdefault(c, {"yes": 0, "no": 0})
        if m["vote"] in SYES:
            t["yes"] += 1
        elif m["vote"] in SNO:
            t["no"] += 1

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
        c = CAUCUS.get(m["party"], m["party"])
        side, unity = position[c]
        base = dict(info)
        base.update(m)
        base["unity_pct"] = unity
        base["party_side"] = side
        if m["vote"] not in SYES and m["vote"] not in SNO:
            base["type"] = "absence"
            entries.append(base)
        elif side is None or unity < THRESHOLD:
            continue
        else:
            member_side = "yes" if m["vote"] in SYES else "no"
            if member_side != side:
                base["type"] = "defection"
                entries.append(base)
    return info, entries


def main():
    os.makedirs(DATA, exist_ok=True)
    year = datetime.date.today().year
    congress, session = session_info(year)
    state = load("senate_state.json", {"year": year, "last_roll": 0})
    if state["year"] != year:
        state = {"year": year, "last_roll": 0}
    votes = load("senate_votes.json", [])
    log = load("senate_log.json", [])
    n = state["last_roll"] + 1
    while True:
        root = fetch(congress, session, n)
        if root is None:
            break
        info, entries = process(year, n, root)
        votes.append(info)
        log.extend(entries)
        state["last_roll"] = n
        n += 1
        time.sleep(0.3)
    state["checked"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save("senate_state.json", state)
    save("senate_votes.json", votes)
    save("senate_log.json", log)


if __name__ == "__main__":
    main()