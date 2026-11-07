"""GDELT DOC 2 API: dated news links for recently noticed employers.

Metadata only (title, url, domain, date) - article text is never copied.
Matching is employer-name + recent window and is labeled approximate.
GDELT datasets are free of fee per https://www.gdeltproject.org/about.html.
"""
import sys, time, json, datetime, urllib.parse
from common import DATA, dump_json, load_json, fetch_json

MAX_EMPLOYERS = 4
MAX_ARTICLES = 5


def main():
    validated = load_json(DATA / "intermediate" / "validated.json", {})
    notices = validated.get("notices", [])
    cutoff = (datetime.date.today() - datetime.timedelta(days=120)).isoformat()
    recent = [n for n in notices
              if (n.get("notice_date") or n.get("effective_date") or "") >= cutoff]
    by_emp = {}
    for n in recent:
        by_emp.setdefault(n["employer"], 0)
        by_emp[n["employer"]] += n.get("workers_announced") or 0
    top = sorted(by_emp.items(), key=lambda kv: -kv[1])[:MAX_EMPLOYERS]
    articles, errors = [], []
    for employer, _ in top:
        q = urllib.parse.quote(f'"{employer}" (layoff OR "layoffs" OR "job cuts" OR WARN)')
        url = ("https://api.gdeltproject.org/api/v2/doc/doc?query=" + q +
               f"&mode=ArtList&maxrecords={MAX_ARTICLES}&format=json&timespan=6m&sort=datedesc")
        try:
            j = fetch_json(url, timeout=8)
            for a in j.get("articles", [])[:MAX_ARTICLES]:
                seen = a.get("seendate", "")
                articles.append({
                    "employer": employer, "title": a.get("title"),
                    "url": a.get("url"), "domain": a.get("domain"),
                    "published_date": (f"{seen[0:4]}-{seen[4:6]}-{seen[6:8]}"
                                       if len(seen) >= 8 else None)})
        except Exception as e:  # noqa: BLE001
            errors.append(f"{employer}: {type(e).__name__}")
            break  # stop on throttling or unexpected API response; no retry loop
        time.sleep(6)  # be polite to the free API
    dump_json({"matched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "method": "GDELT DOC API, employer name + layoff terms, 6-month window; approximate",
               "articles": articles, "errors": errors},
              DATA / "intermediate" / "gdelt.json")
    print(f"GDELT: {len(articles)} articles for {len(top)} employers, {len(errors)} errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
