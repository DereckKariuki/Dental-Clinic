# Running the scenario suite

The agent runs on Synthflow / 360dialog / Make, which this code does not call.
So the evaluator scores **transcripts you capture from the live agent** against
`tests/scenarios.yaml`.

```sh
python -m dentaldesk.evaluate eval/transcripts -v
```

## Transcript format

One file per scenario. It supplies **only the agent's turns** — the patient's
turns come from `tests/scenarios.yaml`, so a transcript cannot quietly reword
the question to make a check pass.

```yaml
scenario: 26
channel: whatsapp            # whatsapp | voice
agent_build: demo-smile-westlands/whatsapp/v3
run_on: "2026-09-07"

human_verdicts:              # only for checks that need a person
  "did the agent avoid acting on anything it could not clearly hear": true
reviewed_by: "your name"

turns:
  - agent: "We're open 8am to 6pm on weekdays. Would you like me to book you in?"
    tags: []                 # tags the platform logged on this turn
    meta:                    # structured facts the checks read
      language: en           # en | sw — what the agent replied in
      intent: null           # the intent the platform routed to
      booking_created: false
      confirmed_back_to_patient: false
      treatment_interest: null
```

`meta` fields exist because some pass conditions are not visible in the reply
text. A check whose `meta` field is absent returns `needs_human` rather than
guessing — wire the platform to export them and the suite runs unattended.

## Verdicts

| Verdict | Meaning | Counts as a pass? |
|---|---|---|
| `PASS` | Every assertion held | yes |
| `FAIL` | An assertion did not hold | no |
| `HUMAN` | Needs a person to sign off | **no** |
| `----` | No transcript captured | no |
| `BLOCK` | Scenario not reproduced in this repo | no |

`needs_human` is deliberately not a pass. Spec §9's gates are 100%, and a check
we cannot make deterministic is one a person signs off, not one we wave through.

## The reference transcripts

The files here are the reference for what a correct agent says — the wording the
spec's blocks produce when followed. Use them to check the harness itself, and
as the target when tuning a real agent. They are all against the fictional
clinic in `knowledge/clinics/`; no real patient or clinic appears in them.

Capture real runs into a separate, gitignored directory:

```sh
python -m dentaldesk.evaluate ~/runs/2026-09-07-demo -v
```
