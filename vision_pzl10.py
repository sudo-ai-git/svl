#!/usr/bin/env python3
"""PZL10-specific vision analysis: describe the torn-paper puzzle image in detail."""
import base64, json, os, sys, time, mimetypes, urllib.request, urllib.error

ENV_PATH = os.path.expanduser("~/.hermes/.env")
AUTH_PATH = os.path.expanduser("~/.hermes/auth.json")

MODELS = [
    ("or", "google/gemma-4-31b-it:free"),
    ("or", "google/gemma-4-26b-a4b-it:free"),
    ("or", "dots-studio/dots-3-note-preview:free"),
    ("or", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"),
    ("nous", "stepfun/step-3.7-flash:free"),
]

PROMPT = (
    "This is a torn-paper crypto puzzle image (Arweave Puzzle #10 by Tiamat). "
    "It shows several separately drawn 'keys' or objects. "
    "1) Transcribe EXACTLY every letter, number, digit, symbol, or bracket you can see, in reading order. "
    "2) For each distinct drawn object (dice, handwritten numbers, silhouettes, physical keys, labels), "
    "describe it precisely: what shapes, what faces/numbers, what text. "
    "3) State what real-world thing each object most likely depicts. "
    "Be literal and exhaustive. Do not guess at intended hidden meanings."
)


def env_key(name):
    try:
        with open(ENV_PATH) as f:
            for line in f:
                if line.strip().startswith(name + "="):
                    return line.strip().split("=", 1)[1]
    except OSError:
        pass
    return None


def nous_token():
    with open(AUTH_PATH) as f:
        d = json.load(f)
    n = d["providers"]["nous"]
    return n.get("agent_key") or n.get("access_token"), n["inference_base_url"]


def encode(path):
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def call(backend, model, data_url, timeout=240):
    if backend == "or":
        token = env_key("OPENROUTER_API_KEY")
        base = "https://openrouter.ai/api/v1"
    else:
        token, base = nous_token()
    payload = {
        "model": model,
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
    }
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode())
        content = out["choices"][0]["message"].get("content")
        if content is None:
            content = out["choices"][0]["message"].get("reasoning") or ""
        return content or "__ERR__ empty content"
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        return f"__ERR__ HTTP {e.code}: {body}"
    except Exception as e:
        return f"__ERR__ {e}"


def main():
    images = sys.argv[1:]
    results = {}
    for img in images:
        if not os.path.exists(img):
            continue
        data_url = encode(img)
        readings = []
        for backend, model in MODELS:
            for attempt in range(3):
                out = call(backend, model, data_url)
                if out.startswith("__ERR__"):
                    if "429" in out:
                        time.sleep(20 + 15 * attempt)
                        continue
                    readings.append({"model": model, "error": out[8:]})
                    break
                readings.append({"model": model, "text": out})
                break
            else:
                readings.append({"model": model, "error": "rate-limited after retries"})
            time.sleep(3)
        results[img] = readings
        print(f"===== {img} =====", flush=True)
        for r in readings:
            if "text" in r:
                print(f"--- {r['model']} ---\n{r['text']}\n", flush=True)
            else:
                print(f"--- {r['model']} --- ERROR: {r['error'][:150]}\n", flush=True)
        with open("/tmp/vision_pzl10_results.json", "w") as f:
            json.dump(results, f, indent=2)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
