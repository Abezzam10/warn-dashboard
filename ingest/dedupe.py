"""Flag possible duplicate notices. Duplicates are marked, never dropped."""
import sys
from common import DATA, dump_json, load_json


def main():
    validated = load_json(DATA / "intermediate" / "validated.json")
    notices = validated["notices"]
    seen = {}
    dupes = 0
    for n in notices:
        key = (n["employer"].lower(), n["state"], n["location"].lower(),
               n["notice_date"] or n["effective_date"], n["workers_announced"])
        if key[3] and key in seen:
            n["duplicate_of"] = seen[key]
            dupes += 1
        else:
            seen[key] = n["id"]
    validated["validation"]["possible_duplicates"] = dupes
    dump_json(validated, DATA / "intermediate" / "validated.json")
    print(f"dedupe: {dupes} possible duplicates flagged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
