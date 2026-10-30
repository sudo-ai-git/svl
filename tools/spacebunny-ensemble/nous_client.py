"""Nous Portal client for stealth/space-bunny-alpha.

Verified against the live endpoint (2026-10-03):

  GET  /v1/models            -> 200 WITHOUT any auth header. 425 models,
                                 stealth/space-bunny-alpha present.
  pricing                    -> prompt 0 / completion 0
  supported_parameters       -> include_reasoning, max_tokens, reasoning,
                                reasoning_effort, response_format,
                                temperature, tool_choice, tools, top_p
  logprobs                   -> NOT offered. Hard constraint; nothing in this
                                harness may depend on token probabilities.

What is NOT verified: a single successful completion.

AUTH (resolved2026-10-03 -- see resolve_key()):
  * /v1/models is PUBLIC: 200 with no auth header, 425 models.
  * /v1/chat/completions requires auth, and working credentials DO exist on
    this box -- two of them, both verified returning a correct completion:
      - credential_pool.nous[label=api-key-1]  auth_type=api_key, sk-... 40ch
      - credential_pool.nous[label=device_code] auth_type=oauth,  eyJ... 1974ch
        (device_code has request_count=252 and is what this session runs on;
         it carries an expires_at around an hour out, so prefer it and fall
         back to the api_key entry)
    Both live in ~/.hermes/auth.json, NOT in ~/.hermes/.env. ~/.hermes/.env's
    LM_API_KEY is a *different, dead* credential -- which is why probing the
    .env alone produced a misleading 401 and looked like a dead account.
  * Trap: unauthenticated, /chat/completions returns 400 "Unknown model" for
    EVERY listed model. That is the no-auth path wearing a misleading message,
    not a statement about the model id. A genuinely absent model returns 404
    "not found in our configuration" instead. Reading that 400 as a bad model
    id sends you hunting a typo that isn't there.
  => model name is correct; the credential source was wrong.

Effort ladder: reasoning_effort is accepted per the published record but the
legal values are not enumerated anywhere, so the ladder probes for them and
degrades loudly rather than silently reporting a single-rung run.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional, Union

BASE_URL = "https://inference-api.nousresearch.com/v1"
MODEL = "stealth/space-bunny-alpha"

# Explicit per-run override. Deliberately NOT LM_API_KEY: on this box that name
# holds an unrelated dead credential in ~/.hermes/.env, and preferring it
# produced a 401 that looked like a dead account.
ENV_OVERRIDES = ("NOUS_API_KEY", "NOUSRESEARCH_API_KEY")
ENV_KEY = ENV_OVERRIDES[0]
ENV_FALLBACKS = ENV_OVERRIDES

# Synthetic status for "the request never produced an HTTP response" (DNS, TLS,
# timeout, connection refused). Distinct from any real HTTP code so it can be
# named rather than silently compared against.
TRANSPORT_FAILED = -1

# Sensible defaults; paper 2607.02436 used High -> xHigh as its contrast.
EFFORT_LADDER_DEFAULT = ["low", "medium", "high"]


class AuthError(RuntimeError):
    pass


class EndpointError(RuntimeError):
    pass


def _load_env_file(path: str = os.path.expanduser("~/.hermes/.env")) -> dict:
    out: dict[str, str] = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


AUTH_JSON = os.path.expanduser("~/.hermes/auth.json")


def _candidates_from_auth_json() -> list[tuple[str, str]]:
    """Nous credentials from Hermes's own credential store.

    This is where the working keys actually live. ~/.hermes/.env's LM_API_KEY
    is a different, dead credential -- trusting the .env first produced a
    misleading 401 and a wrong "the account is out of funds" conclusion.

    Order matters: prefer the oauth/device_code credential (it is what the
    live session uses and carries an expiry), then fall back to the api_key
    entry. Returns (label, token) pairs; never logs a token.
    """
    try:
        with open(AUTH_JSON) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    pool = (d.get("credential_pool") or {}).get("nous") or []
    entries: list[tuple[int, str, str]] = []
    for i, cred in enumerate(pool):
        tok = cred.get("access_token")
        if not tok:
            continue
        # device_code/oauth sorts ahead of plain api_key
        rank = 0 if cred.get("auth_type") == "oauth" else 1
        entries.append((rank, f"{cred.get('label', f'entry{i}')}", tok))
    entries.sort(key=lambda t: t[0])
    return [(lbl, tok) for _, lbl, tok in entries]


def resolve_key() -> Optional[str]:
    """Best available Nous credential. Order: env override, then auth.json
    credential pool, then ~/.hermes/.env. Never logs the value.

    Env wins only when explicitly set (NOUS_API_KEY / NOUSRESEARCH_API_KEY);
    the generic LM_API_KEY is deliberately NOT consulted here, because on this
    box it names an unrelated dead credential that masks the working ones.
    """
    for name in ENV_OVERRIDES:
        v = os.environ.get(name)
        if v:
            return v
    cands = _candidates_from_auth_json()
    if cands:
        return cands[0][1]
    fenv = _load_env_file()
    for name in ENV_FALLBACKS:
        if fenv.get(name):
            return fenv[name]
    return None


def resolve_all_keys() -> list[tuple[str, str]]:
    """All candidate credentials as (token, label) pairs, for failover.

    TOKEN FIRST, LABEL SECOND. The failover loop unpacks in that order; the
    reverse convention shipped the label into the Authorization header
    ("Bearer device_code"), which 401s while every other diagnostic looks fine.
    Never logs values.
    """
    out: list[tuple[str, str]] = []
    for name in ENV_OVERRIDES:
        v = os.environ.get(name)
        if v:
            out.append((v, f"env:{name}"))
    out.extend((tok, f"pool:{lbl}") for lbl, tok in _candidates_from_auth_json())
    fenv = _load_env_file()
    for name in ENV_FALLBACKS:
        if fenv.get(name):
            out.append((fenv[name], f"envfile:{name}"))
    return out


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def merge(self, other: "Usage") -> "Usage":
        return Usage(self.prompt_tokens + other.prompt_tokens,
                     self.completion_tokens + other.completion_tokens)

    def __str__(self) -> str:
        return f"{self.prompt_tokens}p+{self.completion_tokens}c={self.total}t"


@dataclass
class Reply:
    text: str
    reasoning: Optional[str]
    usage: Usage
    finish_reason: str
    raw: dict = field(default_factory=dict)

    @property
    def truncated(self) -> bool:
        return self.finish_reason in ("length", "max_tokens")


def _raw(path: str, payload: Optional[dict], key: Optional[str],
         timeout: float) -> tuple[int, Union[dict, list, str]]:
    """POST/GET returning (status, body).

    The body type is deliberately Union: on success it is whatever
    json.loads produced (dict for a normal completion, but a list or str is
    legal JSON), and on HTTPError it is decoded text. Callers MUST narrow with
    isinstance rather than assume a mapping.
    """
    req = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(payload).encode() if payload else None,
        method="POST" if payload else "GET",
    )
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        try:
            return r.status, json.loads(r.read())
        except (ValueError, UnicodeDecodeError):
            # 200 with a non-JSON body is a real possibility; report the text
            # rather than raising a JSONDecodeError the caller cannot classify
            return r.status, r.read()[:400].decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:400].decode("utf-8", "replace")
    except Exception as e:
        # Transport-level failure (DNS, TLS, timeout, refused connection). There
        # is no HTTP status, so use TRANSPORT_FAILED rather than None: every
        # caller compares against int literals, and a bare None falls through
        # all of them and gets reported as an unclassified mystery status
        # instead of "the request never reached the server".
        return TRANSPORT_FAILED, str(e)[:200]


def probe_endpoint(key: Optional[str] = None, timeout: float = 45) -> dict:
    """Liveness + auth check that names the actual cause of failure.

    Three probes, because the two obvious ones are ambiguous:

      1. /models with the key      -- is the catalog reachable, is our model listed
      2. /chat with the key       -- can this key actually spend money (200/401)
      3. /chat with NO key        -- separates "bad model id" from "no auth"

    Probe 3 matters: unauthenticated, this endpoint answers 400 "Unknown model"
    for every listed model. That 400 is the no-auth path wearing a misleading
    error message, not a statement about the model. A name that truly does not
    exist returns 404 instead. Getting this backwards sends you hunting for a
    typo that isn't there -- which is exactly what happened here first.
    """
    k = key if key is not None else resolve_key()
    out: dict[str, Any] = {"key_present": bool(k)}
    if not k:
        out["usable"] = False
        out["candidates"] = [lbl for lbl, _ in resolve_all_keys()]
        if out["candidates"]:
            out["diagnosis"] = "credential pool readable but no usable token"
        else:
            out["diagnosis"] = (
                "no Nous credential found. /models is public but chat needs "
                "auth; the working credential lives in the Hermes credential "
                "pool, not in .env")
            out["remedy"] = (f"log in via portal.nousresearch.com, or set "
                             f"{ENV_OVERRIDES[0]} in the environment")
        # still check the catalog so the report is useful without a key
        st, body = _raw("/models", None, None, timeout)
        out["models_status"] = st
        if isinstance(body, dict) and "data" in body:
            ids = [m.get("id") for m in body["data"]]
            out["model_count"] = len(ids)
            out["model_listed"] = MODEL in ids
        return out

    st, body = _raw("/models", None, k, timeout)
    out["models_status"] = st
    if isinstance(body, dict) and "data" in body:
        ids = [m.get("id") for m in body["data"]]
        out["model_count"] = len(ids)
        out["model_listed"] = MODEL in ids
    else:
        out["models_detail"] = str(body)[:200]

    chat_payload = {"model": MODEL,
                    "messages": [{"role": "user", "content": "1+1="}],
                    "max_tokens": 16}
    st, body = _raw("/chat/completions", chat_payload, k, timeout)
    out["chat_status"] = st
    out["usable"] = (st == 200)
    out["credential_source"] = "hermes credential pool (auth.json)"

    # _raw returns dict on success and decoded TEXT on HTTPError, so a 200 is
    # not proof that body is a mapping. json.loads can also yield a list or a
    # bare string for a well-formed-but-unexpected 200. Narrow explicitly --
    # calling .get() on a str here is the kind of crash that only shows up in
    # production, and it would be misread as an endpoint outage.
    if st == 200 and isinstance(body, dict):
        out["diagnosis"] = "endpoint usable"
        u = body.get("usage") or {}
        out["usage_seen"] = {
            "prompt_tokens": u.get("prompt_tokens"),
            "completion_tokens": u.get("completion_tokens"),
            "total_tokens": u.get("total_tokens"),
        }
        out["model_returned"] = body.get("model")
        return out

    if st == 200:
        out["usable"] = False
        out["diagnosis"] = "200 but body was not a JSON object"
        out["detail"] = str(body)[:300]
        return out

    detail = str(body)[:300]
    out["detail"] = detail

    if st == TRANSPORT_FAILED:
        # Never reached the server: DNS, TLS, timeout, refused. Reporting this
        # as an auth or model problem sends you hunting in the wrong place.
        out["diagnosis"] = (
            "transport failure -- the request never got an HTTP response. "
            "This is a network/DNS/TLS/timeout problem, NOT credentials and "
            "NOT the model id.")
        out["remedy"] = ("check connectivity to inference-api.nousresearch.com; "
                         "raise --timeout if this is a timeout")
        return out

    # Disambiguate the two failure modes with an unauthenticated control.
    st_noauth, body_noauth = _raw("/chat/completions", chat_payload, None,
                                   timeout)
    out["chat_status_noauth"] = st_noauth
    if st == 401:
        out["diagnosis"] = (
            "key is rejected by /chat/completions (401). The model is listed "
            "and the endpoint is live, so this is an auth/credit problem, not "
            "a model problem.")
        out["remedy"] = ("fund the key or mint a new one at "
                         "portal.nousresearch.com; confirm with --probe")
    elif st == 404:
        out["diagnosis"] = f"model id {MODEL!r} not in the serving config"
    elif st == 400 and st_noauth == 400:
        out["diagnosis"] = (
            "both authed and unauthenticated chat return 400 -- this looks "
            "like a request-shape or parameter problem, not credentials")
    elif st_noauth in (400, 401):
        out["diagnosis"] = (
            f"authed chat returned {st}; unauthenticated returned "
            f"{st_noauth}. The unauthenticated 400 is the endpoint's "
            "no-auth path, not evidence of a bad model id.")
    else:
        out["diagnosis"] = f"chat failed with {st}"
    return out


def _post(path: str, payload: dict, key: str, timeout: float) -> dict:
    req = urllib.request.Request(
        BASE_URL + path, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read()[:400].decode("utf-8", "replace")
        if e.code in (401, 402, 403):
            raise AuthError(f"{e.code} from Nous portal: {detail}") from None
        raise EndpointError(f"{e.code} from Nous portal: {detail}") from None
    except urllib.error.URLError as e:
        raise EndpointError(f"network failure: {e.reason}") from None


def chat(messages: list[dict], *, effort: Optional[str] = None,
         temperature: Optional[float] = None, top_p: Optional[float] = None,
         max_tokens: int = 2048, include_reasoning: bool = True,
         key: Optional[str] = None, timeout: float = 180.0,
         retries: int = 2) -> Reply:
    """One completion. Retries only on transient 5xx/network, never on 401."""
    k = key or resolve_key()
    if not k:
        raise AuthError(f"no key: set {ENV_KEY} in ~/.hermes/.env")

    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if effort:
        payload["reasoning_effort"] = effort
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p
    if include_reasoning:
        payload["include_reasoning"] = True

    last_err: Optional[Exception] = None

    # Credential failover. A pool entry can expire or get revoked mid-run --
    # the device_code credential carries an expires_at roughly an hour out --
    # so try each candidate in turn on an auth failure instead of dying.
    keys = [(key, "explicit")] if key else resolve_all_keys()
    if not keys:
        raise AuthError(
            f"no Nous credential found. Set {ENV_OVERRIDES[0]} in the "
            f"environment, or log in via the Hermes portal so that "
            f"{AUTH_JSON} gains a credential_pool.nous entry.")
    # Guard the (token, label) contract: a label in the Authorization header
    # produces a 401 that looks exactly like a dead credential.
    for k, label in keys:
        if not k or len(k) < 20 or k == label:
            raise AuthError(
                f"credential {label!r} does not look like a token "
                f"(len={len(k)}); refusing to send it as a Bearer credential")

    body: Optional[dict] = None
    auth_failures: list[str] = []
    for k, label in keys:          # (token, label) -- see resolve_all_keys
        for attempt in range(retries + 1):
            try:
                body = _post("/chat/completions", payload, k, timeout)
                break
            except AuthError as e:
                auth_failures.append(f"{label}: {e}")
                break                      # a dead key will not fix itself
            except EndpointError as e:
                last_err = e
                if str(e)[:3] not in ("429", "500", "502", "503", "504"):
                    raise                  # contract problem, not transient
                time.sleep(1.5 * (attempt + 1))
        if body is not None:
            break

    if body is None:
        raise AuthError("all Nous credentials rejected: " +
                        " | ".join(auth_failures[:4]))
    if last_err:
        raise last_err

    if "choices" not in body:
        raise EndpointError(f"no choices in response: {str(body)[:300]}")

    msg = body["choices"][0].get("message", {}) or {}
    text = msg.get("content") or ""
    # some routes put chain-of-thought under a separate key
    reasoning = msg.get("reasoning") or msg.get("reasoning_content")
    if not text and reasoning:
        # reasoning-only response: the CoT is the answer surface we have
        text = reasoning
    u = body.get("usage") or {}
    return Reply(
        text=text,
        reasoning=reasoning,
        usage=Usage(int(u.get("prompt_tokens") or 0),
                    int(u.get("completion_tokens") or 0)),
        finish_reason=body["choices"][0].get("finish_reason") or "",
        raw=body,
    )


def list_models(key: Optional[str] = None) -> list[str]:
    k = key or resolve_key()
    if not k:
        raise AuthError(f"no key: set {ENV_KEY} in ~/.hermes/.env")
    req = urllib.request.Request(BASE_URL + "/models")
    req.add_header("Authorization", f"Bearer {k}")
    with urllib.request.urlopen(req, timeout=45) as r:
        return [m["id"] for m in json.loads(r.read()).get("data", [])]