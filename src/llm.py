#!/usr/bin/env python3
"""
llm.py — the one seam. Everything in this project that reaches a model goes
through here, and nothing else may (`docs/roadmap.md`, "the first LLM call in
this project" — guarantee 14, a grep test the same shape as `READER`'s).

`ask()` is the only function that performs a network call, and it is always
handed to a caller as an injectable parameter — `tools/loop.py`'s own `ask=`
is the shape this borrows — so the test suites never touch the network
(guarantee 2). `ENDPOINT` and `MODEL` are each defined exactly once, held to
that by a grep test the same way `READER` already is in `markdown.py`.

Stdlib only: `urllib.request` and `json`. `pyproject.toml`'s
`dependencies = []` stays true (decision 5, 2026-09-11) — `requests` would
save a few lines and cost the one property this project has defended even for
`jsonschema`.
"""
import json
import os
import urllib.error
import urllib.request

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Measured 2026-09-17 against 2,207 Wikipedia fragments with ground truth, in
# two arms -- headings kept and headings stripped. The table is in
# docs/decisions.md. The short version: gpt-4o-mini, the first default, was
# the worst of four models tested. It had 12 of 13 batches rejected and scored
# 39.3% page accuracy once headings were removed; gemini-3.8-flash had 0
# rejected and scored 99.4%, matching claude-opus-5 at a sixth of the price.
#
# The release's own working hypothesis -- "semantic categorisation will not
# need the most expensive models" -- is confirmed, but with a floor under it:
# two cheap models were below the bar and this one is at it. Changing this
# constant without re-running that measurement is how the floor gets lost.
MODEL = "google/gemini-3.8-flash"

TIMEOUT_S = 180
MAX_RETRIES = 3

# The models that pass the measurement above are reasoning models: they spend
# output tokens on a reasoning trace before answering. Two consequences, both
# of which broke the sweep that produced the table.
#
# Without a cap, a 100-fragment answer can be truncated -- the response comes
# back with `content: null` and `finish_reason: "length"`, and the old code
# returned that None straight to the caller, which died inside
# `_parse_response` with an opaque AttributeError far from the cause.
#
# `reasoning: {"exclude": True}` asks the provider not to bill or return the
# trace. This layer wants a label, not an argument for it.
MAX_OUTPUT_TOKENS = 8000


class LLMError(RuntimeError):
    """A call that came back, but with nothing usable in it.

    Separate from the transport failures `ask` retries: a refusal, a
    truncation, or a response shaped differently than expected is not worth
    retrying and must name what it saw, so the caller is not left guessing.
    """

# Static, not fetched — see docs/roadmap.md's `--cost-calculation` section
# and this release's own report. The draft spec's prose says the price is
# "fetched"; guarantee 1 says --cost-calculation makes no network call *with
# or without* --model, and the verify script's NEW check for guarantee 1
# points the endpoint at a closed port with no --model restriction. The two
# read as contradictory, and this implementation sides with the guarantee:
# a small, hand-maintained table, in USD per million input tokens, that will
# go stale and says so. A model missing from it prices as "unknown" rather
# than guessed at.
PRICE_TABLE = {
    # The four measured on 2026-09-17, marked with what they scored for
    # page accuracy on the harder arm (headings stripped). The rest are
    # unmeasured and priced only so --cost-calculation can answer for them.
    "google/gemini-3.8-flash": 0.75,            # 99.4% -- the default
    "anthropic/claude-opus-5": 5.00,            # 98.7% -- the ceiling
    "google/gemini-2.5-flash-lite": 0.10,       # 81.2% -- below the bar
    "openai/gpt-4o-mini": 0.15,                 # 39.3% -- below the bar
    "google/gemini-2.5-flash": 0.30,
    "anthropic/claude-sonnet-4.6": 3.00,
    "openai/gpt-4.1-mini": 0.40,
    "deepseek/deepseek-chat": 0.26,
}


def endpoint() -> str:
    """`ENDPOINT`, unless `COMPOST_LLM_ENDPOINT` overrides it.

    The override exists for exactly one caller: the verify script's
    guarantee-1 check points this at a closed port to prove
    `--cost-calculation` cannot reach the network even if something upstream
    of it tried. Nothing else should ever set this.
    """
    return os.environ.get("COMPOST_LLM_ENDPOINT", ENDPOINT)


def ask(system: str, user: str, model: str | None = None,
        api_key: str | None = None) -> str:
    """One OpenRouter chat completion. Returns the assistant's text.

    Never called by a suite (guarantee 2) — a suite that needs a model
    response reads a canned fixture and injects a fake `ask=` instead.
    """
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set — read it from the environment "
            "at the point of use, never store it (CLAUDE.md)")
    body = json.dumps({
        "model": model or MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "reasoning": {"exclude": True},
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint(), data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    last_err: Exception | None = None
    for _ in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                data = json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            last_err = e                      # transport: worth retrying
            continue
        # Everything below is a response that arrived. Retrying it would just
        # buy the same answer again, so each of these raises instead.
        try:
            choice = data["choices"][0]
        except (KeyError, IndexError, TypeError):
            raise LLMError(
                f"{model or MODEL} returned no choices: {str(data)[:200]}")
        text = (choice.get("message") or {}).get("content")
        if isinstance(text, str) and text.strip():
            return text
        raise LLMError(
            f"{model or MODEL} returned no usable text "
            f"(finish_reason={choice.get('finish_reason')!r}). A reasoning "
            f"model truncated at MAX_OUTPUT_TOKENS={MAX_OUTPUT_TOKENS} "
            f"returns this; a smaller --batch-size is the usual fix.")
    raise LLMError(f"llm call failed after {MAX_RETRIES} attempts: {last_err}")


def key_usage(api_key: str | None = None) -> dict:
    """`GET /api/v1/key` — costs nothing, reports `usage` and
    `limit_remaining`. Not gated behind any injectable seam: it is read-only
    and free, the same standing `--cost-calculation` itself has, but it is
    still routed through this module because it is still a network call.
    """
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    # Derived from endpoint(), not hardcoded: the override exists so a test
    # can point every call in this module somewhere closed, and a second
    # literal URL here would quietly escape it.
    base = endpoint().rsplit("/chat/completions", 1)[0]
    req = urllib.request.Request(
        f"{base}/key", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))["data"]


def estimate_tokens(text: str) -> int:
    """A rough, offline, always-labelled estimate: ~4 characters per token.

    Not exact and cannot be, honestly: as far as this project can establish,
    Anthropic publishes no offline tokenizer, and counting tokens is itself
    an API call for at least one named model family — which would defeat
    `--cost-calculation`'s one hard promise of making no network call
    (decision 4, 2026-09-11). Every caller of this must label its output as
    an estimate; the character and call counts around it are exact and must
    say so too.
    """
    return max(1, round(len(text) / 4))
