"""Jev triage of Moneta v6 rulings R1-R5, per the protocol in rulings.jev.json.

Usage: python -I jev_triage.py <rulings.jev.json> <out_dir>
Writes requests.jsonl (every request + raw response) and summary.json.
"""
import hashlib
import json
import os
import sys
import urllib.request

URL = "https://api.typesafe.ai/v1/systemone"


def ordered(criteria, order):
    keys = [k for k in criteria if k != "none_of_these"]
    if order == "reversed_with_none_of_these_last":
        keys = list(reversed(keys))
    keys.append("none_of_these")
    return {k: criteria[k] for k in keys}


def call(body, key):
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    spec = json.load(open(src, encoding="utf-8"))
    proto = spec["protocol"]
    key = os.environ["TYPESAFE_API_KEY"]
    model = sys.argv[3] if len(sys.argv) > 3 else proto["model"]
    log = open(os.path.join(out, "requests.jsonl"), "w", encoding="utf-8")
    runs = {qid: {} for qid in spec["questions"]}
    versions = set()
    for order in proto["orders"]:
        for rep in range(proto["repeats_per_order"]):
            questions = {
                qid: {"type": q["type"], "instructions": q["instructions"],
                      "criteria": ordered(q["criteria"], order)}
                for qid, q in spec["questions"].items()
            }
            body = {"state": spec["state"], "model": model, "questions": questions}
            h = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
            resp = call(body, key)
            versions.add(resp.get("model"))
            log.write(json.dumps({"order": order, "repeat": rep, "request_sha256": h,
                                  "request": body, "response": resp}) + "\n")
            for qid, a in resp["answers"].items():
                runs[qid].setdefault(order, []).append(a)
            print(f"[{order} #{rep}] {resp.get('model')} "
                  + ", ".join(f"{q}={a['choice']}" for q, a in resp["answers"].items()), flush=True)
    summary = {"model_versions": sorted(v for v in versions if v)}
    for qid, by_order in runs.items():
        mean = {}
        for order, answers in by_order.items():
            opts = answers[0]["probabilities"].keys()
            mean[order] = {o: sum(a["probabilities"][o] for a in answers) / len(answers) for o in opts}
        tops = {order: max(m, key=m.get) for order, m in mean.items()}
        same = len(set(tops.values())) == 1
        top = next(iter(tops.values()))
        settled = same and all(m[top] >= 0.60 for m in mean.values())
        summary[qid] = {
            "status": "settled" if settled else "contested",
            "top_by_order": tops,
            "mean_probabilities_by_order": {o: {k: round(v, 4) for k, v in m.items()} for o, m in mean.items()},
            "confidence": {o: [round(a["confidence"], 4) for a in ans] for o, ans in by_order.items()},
            "repeat_stable": {o: len({a["choice"] for a in ans}) == 1 for o, ans in by_order.items()},
        }
    json.dump(summary, open(os.path.join(out, "summary.json"), "w"), indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
