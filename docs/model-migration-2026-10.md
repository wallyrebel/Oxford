# Budget model replacement — October 27, 2026

The owner approved replacing retired GPT-4.1 nano calls with GPT-6 Luna at
standard prices of $0.10/M input and $0.50/M output (old nano: $0.10/$0.40).
The output token rate increases 25%; total cost depends on actual token usage.
No retirement date is currently listed for GPT-6 Luna. Existing managed overrides
that name the retired nano alias or snapshot are mapped at the API boundary.

Use reasoning_effort="none", omit sampling parameters, and preserve the existing
completion-token cap, JSON/output validators, publication modes, deduplication,
source/editorial checks and schedules. No higher-priced failover tier is added.
GPT-5 nano was tested but not deployed; its December 11 shutdown is too soon.
Other models that are only scheduled for future retirement are left unchanged.
No API credentials are copied or stored. The SDK floor matches the tested release.

Sources: https://developers.openai.com/api/docs/models/gpt-6-luna,
https://developers.openai.com/api/docs/models/gpt-4.1-nano,
https://developers.openai.com/api/docs/deprecations.
