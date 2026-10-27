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
