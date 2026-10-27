"""Compatibility for the budget replacement of the retired GPT-4.1 nano.

GPT-6 Luna is $0.10/M input and $0.50/M output (standard pricing).
This replacement and its output-price increase were explicitly approved.
"""


def resolve_retired_model(model):
    # Existing managed environment overrides may still name the retired model.
    if model in {"gpt-4.1-nano", "gpt-4.1-nano-2025-04-14"}:
        return "gpt-6-luna"
    return model


def chat_model_params(params):
    params = dict(params)
    model = resolve_retired_model(params.get("model"))
    params["model"] = model
    if model in {"gpt-6-luna"}:
        # Both reasoning and visible output share the existing hard token cap.
        limit = params.pop("max_tokens", params.get("max_completion_tokens", 2000))
        params["max_completion_tokens"] = limit
        params.pop("temperature", None)
        params["reasoning_effort"] = "none"
    return params


def replacement_payload_problem(payload):
    """Reject observed Luna source-insufficiency narration, retaining short news."""
    import html
    import re
    if not isinstance(payload, dict):
        return None
    def plain(value):
        if not isinstance(value, str):
            return ""
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value))).casefold().replace("’", "'").strip(' .!?:"')
    heading=plain(payload.get("headline"))
    if re.fullmatch(r"(?:no (?:schedule|conference|event|source|article|story) details (?:were )?provided(?: for .*)?|article offers no details(?: on .*)?)", heading):
        return "replacement_model_missing_source_details"
    for field in ("body", "excerpt", "narration_text"):
        text=plain(payload.get(field))
        if re.match(r"the (?:submitted|supplied|provided) (?:text|content|source)\b", text) and re.search(r"\b(?:does not include|doesn't include|does not provide|doesn't provide|lacks)\b", text):
            return "replacement_model_missing_source_details"
    return None


def create_model_completion(client, params):
    """Apply the replacement contract before an existing response parser sees it."""
    import json
    import re
    options=chat_model_params(params)
    response=client.chat.completions.create(**options)
    if options.get("model") == "gpt-6-luna":
        text=response.choices[0].message.content
        try:
            payload=json.loads(text)
        except (TypeError, ValueError):
            match=re.search(r"\{[\s\S]*\}", text or "")
            try:
                payload=json.loads(match.group()) if match else None
            except ValueError:
                payload=None
        problem=replacement_payload_problem(payload)
        if problem:
            raise ValueError(problem)
    return response
