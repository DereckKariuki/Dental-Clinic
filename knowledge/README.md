# KNOWLEDGE

One YAML file per clinic in `clinics/`. This is the *only* source the agent may
answer facts from (spec §6, FAQ HANDLING: "Answer ONLY from KNOWLEDGE... Never
guess. Never approximate hours or prices.").

`schema.py` in `src/dentaldesk/knowledge.py` validates every file. A clinic that
fails validation must not be put in front of a patient.

## Rules that the schema enforces

| Rule | Spec | Enforcement |
|---|---|---|
| Nearest 24-hour casualty is named specifically, with its road | §6 emergency | `emergency.casualty.name` + `.road` required, non-empty |
| Casualty must be verified by a human, not the model | §6 emergency | `emergency.casualty.verified_on` + `verified_by` required |
| Prices are "from" figures only | §6 pricing | every `price_list` entry needs `from_price_kes` |
| Never quote implants, ortho, veneers, surgery, complex | §6 pricing | `quotable: false` forced for those categories |
| Never confirm an insurer unless listed | §6 payment | `insurers_accepted` is a closed list; empty is valid and means "confirm nothing" |
| Do not assert SHA coverage | §6 payment | SHA may not appear in `insurers_accepted` |
| Referral must come from KNOWLEDGE, never invented | §9 test 29 | `services_not_offered[].referral` required |
| Price list, maps pin, M-Pesa, response promise | §7 | required for WhatsApp-enabled clinics |

## Deliberate omissions

Some facts are left out on purpose so the agent's "I don't have that in front of
me" path is exercised. `unknowns` lists them. The fictional clinic omits the
per-day dentist roster, which is what scenario 28 tests — do not "fix" this by
adding a Thursday roster.

## Patient data

None. KNOWLEDGE is clinic reference data only. No patient ever appears in this
directory. See `docs/data-protection.md`.
