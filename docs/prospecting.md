# Prospecting — the §3 qualification test

Spec §3's test, in three steps:

1. Call the clinic at 1:00pm and again 30 minutes after closing. Log both.
2. WhatsApp them a real patient question at 8pm — *"Hi, do you do implants?
   How much roughly?"* — and time the reply.
3. Read reviews for "hawajibu simu", "no one answers", "never replied".

**Tier A = no WhatsApp reply within 12 hours *and* voicemail on both calls.**
The WhatsApp test is the stronger signal in Kenya. Most clinics fail it.

## Logging a survey

One row per clinic in a CSV. Columns map to `Survey` in
`src/dentaldesk/prospecting/qualify.py`; see `prospecting/example-surveys.csv`.

| Column | Notes |
|---|---|
| `name`, `area`, `kind` | `kind` is `private`, `government`, `mission`, `hospital_department`, `single_chair_low_income` |
| `chairs`, `owner_dentist` | Target is 1–4 chairs with a findable owner-dentist |
| `rating`, `review_count` | Qualify in at 4.3+ and 25+ reviews |
| `services`, `insurers` | Pipe-separated: `implants\|aligners\|veneers` |
| `has_whatsapp`, `runs_ads` | `yes`/`no` |
| `advertises_budget_extraction` | The "from KES 500 extraction" signal — wrong economics |
| `review_phrases` | Pipe-separated snippets you actually found |
| `whatsapp_sent_at`, `whatsapp_replied_at` | ISO 8601. Leave the reply blank if none came. |
| `call_midday`, `call_after_close` | `answered`, `voicemail`, `no_answer` |

```sh
make qualify
python -m dentaldesk.prospecting.qualify prospecting/my-westlands-run.csv --tier A
```

## Tiers

| Tier | Meaning |
|---|---|
| **A** | Failed the WhatsApp test *and* missed both calls — the spec's definition. Lead with the evidence. |
| **B** | Failed one of the two. |
| **C** | Answered both, or **not yet tested**. |
| **SKIP** | Disqualified on the §3 skip list. |

An untested clinic is never Tier A. Without the evidence there is no tier — go
and run the test rather than guessing one. The `todo:` lines in the output say
what is still missing.

`Assessment.opening_line` only returns the spec's opening line for Tier A, so
you can never accidentally claim two voicemails you did not actually collect.

## Note on the data

Clinic names, public numbers and response times are business data, not patient
data, so this is the one place the repo writes a local file. Real survey logs
are gitignored anyway — they carry contact data for people who have not asked
to hear from you.
