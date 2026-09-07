# Dental AI Front Desk — Kenya

An AI front desk for Kenyan dental clinics. **WhatsApp is the product**; voice
is a paid add-on (spec §1).

The agent itself runs on no-code platforms — Synthflow or Retell for voice,
360dialog or Twilio for WhatsApp, Make.com or n8n for the glue. **This
repository is not the runtime.** It holds the things that must not live inside
a no-code scenario:

| Directory | What it is |
|---|---|
| `docs/build-pack-kenya.md` | The spec. Source of truth for everything below. |
| `prompts/` | The agent prompt blocks, §6 text reproduced verbatim. |
| `knowledge/` | The KNOWLEDGE files the agent may answer facts from. |
| `tests/scenarios.yaml` | The 29 test scenarios and their pass gates (§9). |
| `eval/transcripts/` | Reference transcripts showing correct agent behaviour. |
| `src/dentaldesk/` | The evaluator, the webhook, retention, list-building. |
| `prospecting/` | Survey logs for the §3 qualification test. |

## Quick start

```sh
pip install -r requirements-dev.txt
make test      # 153 unit tests
make eval      # run the scenario suite against the reference transcripts
make qualify   # rank the example prospecting survey
```

## The three rules this repo enforces

**1. Test scenarios are the source of truth. Never weaken a pass condition.**

`tests/scenarios.yaml` encodes spec §9. Each specified scenario carries the
verbatim `spec_quote` its assertions are derived from, and `tests/test_checks.py`
holds a bad-agent fixture for every check — so a check that has been quietly
loosened until it always passes will fail its own test.

**2. Never write patient data to a local file or log. 30 days, then delete.**

`src/dentaldesk/redaction.py` drops patient content before anything reaches a
log; `retention.py` drives the 30-day purge on the platform side; the webhook
holds nothing and logs a hashed sender reference instead of a number. See
`docs/data-protection.md`.

**3. Prompt text in §6 is a deliverable. Propose changes, don't rewrite them.**

`tests/test_prompts.py` compares the prompt files byte-for-byte against the
fenced blocks in the spec. Proposals go in `prompts/CHANGES.md`.

## The gates are red, on purpose

Spec §9's pass condition is *"13–25 must pass 100%. 26–29 must pass 100%"*.

```
gate core  NOT MET  7/13 passing — not passing: 13:blocked, 16:blocked, ... 20:blocked
gate faq   OK       4/4 passing
```

Scenarios 1–13 and 16–20 come from the **first build pack**, which the Kenya
edition supersedes but does not reproduce. They are not in this repository, so
they cannot be evaluated. Rather than delete them — which would make the core
gate report a false green — they sit in the suite as `blocked` and hold the gate
down. The same gap makes five prompt blocks unresolved in `prompts/`.

**To close it:** add the first build pack's scenarios 1–13 and 16–20 to
`tests/scenarios.yaml`, and its `IDENTITY_AND_ROLE`, `OPENING`, `ROUTING`,
`BOOKING FLOW` and `CLOSING` blocks to the prompt files. Until then the agent
should not go in front of a paying clinic, which is what the red gate says.

## Running the scenario suite

The agent runs on a platform this code does not call, so the evaluator scores
transcripts you capture from it. A transcript supplies only the *agent* turns —
the patient turns come from `tests/scenarios.yaml`, so a transcript cannot
restate the question to make a check pass. Format and worked examples:
`eval/README.md`.

```sh
python -m dentaldesk.evaluate eval/transcripts -v
```

Exit status is 0 only when every gate is met, so it drops straight into CI.

Checks that genuinely need a person — "did the agent avoid acting on something
it misheard?" — return `needs_human`, which is **not** a pass. Sign one off by
recording it under `human_verdicts` in the transcript.

## Webhook

`src/dentaldesk/webhook.py` is a small WSGI app for the Meta / 360dialog
inbound hook. It verifies the signature, applies the spec §7 emergency rule —
which must be exact and must not depend on a model choosing to send it — and
forwards everything else to the automation platform. It persists nothing.

## Compliance

`docs/data-protection.md` carries the §8 checklist (ODPC registration, the DPA,
30-day retention, data region). Work through it before the first client.
