# Proposed prompt changes

Spec rule: prompt text in §6 of `docs/build-pack-kenya.md` is a deliverable.
Propose changes here and get them agreed before editing `voice_agent.md` or
`whatsapp_agent.md`. `tests/test_prompts.py` fails if the verbatim blocks drift
from the spec, so an unagreed edit is caught in CI.

Template:

```
## <short title>
Block:        <e.g. PRICING>
Channel:      voice | whatsapp | both
Problem:      what goes wrong today, and which test scenario shows it
Proposed:     the exact replacement text
Risk:         which scenarios could regress
Status:       proposed | agreed | rejected
```

---

## 1. Voice FAQ deflection asks for a number the caller is already on
Block:        FAQ HANDLING
Channel:      voice
Problem:      The "Factual question NOT in KNOWLEDGE" line reads "let me get
              reception to call you back on [NUMBER]. Is that the best one?".
              On voice, `[NUMBER]` is the caller's own CLI, which the agent may
              not have on a withheld number. Scenario 28 depends on this line
              firing, so the fallback needs to be defined rather than left to
              the model.
Proposed:     No change to the spec wording. Add an assembly-time rule: if CLI
              is unavailable, `[NUMBER]` renders as "the best number for you"
              and the agent asks for it. This is a KNOWLEDGE/assembly change,
              not a prompt-text change.
Risk:         None to scenarios 26–29; the deflection and callback offer are
              unchanged.
Status:       proposed
