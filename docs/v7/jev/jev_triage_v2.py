"""Jev triage, protocol v2 (pass 2 of the v7 loop).

Fixes found in pass 1:
  - every cyclic rotation of the real options (none_of_these always last),
    so every option visits every position;
  - one question per request, so answers are independent;
  - an extra R4 variant with the adoption wording removed from the state,
    to test whether the prompt was priming owner_gate.

Usage: python -I jev_triage_v2.py <rulings.jev.json> <out_dir> [tag]
"""
import copy
import hashlib
import json
import os
import sys
import urllib.request

URL = "https://api.typesafe.ai/v1/systemone"
REPEATS = 2
SETTLE_P = 0.60
POSITION_SWING = 0.20


def call(body, key):
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def rotations(criteria):
    keys = [k for k in criteria if k != "none_of_these"]
    for i in range(len(keys)):
        rot = keys[i:] + keys[:i] + ["none_of_these"]
        yield i, {k: criteria[k] for k in rot}


def neutral_state(state):
    s = copy.deepcopy(state)
    s["the_line"] = s["the_line"].split(" Sleep passes are held")[0]
    return s


def main():
    src, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    spec = json.load(open(src, encoding="utf-8"))
    key = os.environ["TYPESAFE_API_KEY"]
    model = spec["protocol"]["model"]
    variants = [(qid, q, spec["state"], qid) for qid, q in spec["questions"].items()]
    if "r4_pointer" in spec["questions"]:
        r4 = copy.deepcopy(spec["questions"]["r4_pointer"])
        r4["instructions"] = r4["instructions"].split(" Under every option")[0]
        variants.append(("r4_pointer", r4, neutral_state(spec["state"]), "r4_pointer_neutral"))
    tag = sys.argv[3] if len(sys.argv) > 3 else "v2"

    log = open(os.path.join(out, f"requests_{tag}.jsonl"), "w", encoding="utf-8")
    summary = {"protocol": "v2: all cyclic rotations, one question per request, "
                           f"{REPEATS} repeats; settled = same top in every rotation with mean p >= {SETTLE_P} "
                           f"and no option swinging >= {POSITION_SWING} across rotations",
               "model_versions": set()}
    for qid, q, state, label in variants:
        per_rot = []
        for rot_i, crit in rotations(q["criteria"]):
            answers = []
            for rep in range(REPEATS):
                body = {"state": state, "model": model,
                        "questions": {qid: {"type": "choice", "instructions": q["instructions"], "criteria": crit}}}
                resp = call(body, key)
                summary["model_versions"].add(resp.get("model"))
                h = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
                log.write(json.dumps({"variant": label, "rotation": rot_i, "repeat": rep,
                                      "request_sha256": h, "request": body, "response": resp}) + "\n")
                answers.append(resp["answers"][qid])
            opts = list(crit)
            mean = {o: sum(a["probabilities"][o] for a in answers) / REPEATS for o in opts}
            per_rot.append({"order": opts, "mean": mean, "choices": [a["choice"] for a in answers]})
            print(f"{label} rot{rot_i}: " + ", ".join(f"{o}={mean[o]:.3f}" for o in opts), flush=True)
        opts = list(q["criteria"])
        tops = [max(r["mean"], key=r["mean"].get) for r in per_rot]
        swing = {o: round(max(r["mean"][o] for r in per_rot) - min(r["mean"][o] for r in per_rot), 4) for o in opts}
        avg = {o: round(sum(r["mean"][o] for r in per_rot) / len(per_rot), 4) for o in opts}
        top = tops[0]
        settled = (len(set(tops)) == 1 and all(r["mean"][top] >= SETTLE_P for r in per_rot)
                   and max(swing.values()) < POSITION_SWING)
        summary[label] = {"status": "settled" if settled else "contested", "top_by_rotation": tops,
                          "mean_over_rotations": avg, "position_swing": swing, "rotations": per_rot}
    summary["model_versions"] = sorted(v for v in summary["model_versions"] if v)
    json.dump(summary, open(os.path.join(out, f"summary_{tag}.json"), "w"), indent=2)
    for label in [v[3] for v in variants]:
        s = summary[label]
        print(label, s["status"], s["top_by_rotation"], "avg", s["mean_over_rotations"], "swing", s["position_swing"])


if __name__ == "__main__":
    main()
