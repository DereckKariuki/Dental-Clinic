# Data protection — Kenya

Under the **Data Protection Act 2019** the clinic is the data controller and we
are the data processor. This file is the operational side of spec §8.

## Checklist — before the first client

- [ ] Register with the **ODPC** as a data processor
- [ ] Sign a **data processing agreement** with each clinic, naming them as
      controller and us as processor
- [ ] Set call recording and transcript retention to **30 days**, then delete
- [ ] Choose the closest available data region on the voice platform
- [ ] Add *"This call may be recorded."* to the voice opening, once, briefly
- [ ] Never move patient data into a personal Google Sheet or WhatsApp

Being able to say "I'm ODPC-registered and here's the DPA" separates you from
everyone else cold-calling these clinics with an AI pitch.

## What that means for this code

**Patient data never touches local storage.** Not a file, not a log line, not a
scratch CSV. The record of a conversation lives on the platform that processed
it, inside the retention window, and nowhere else.

| Concern | Where it is handled |
|---|---|
| Message bodies, names, numbers in logs | `redaction.py` — sensitive keys are dropped whole, not merely pattern-scrubbed |
| Log handlers as a last line of defence | `redaction.install_log_redaction()` |
| Identifying a conversation in logs/metrics | `InboundMessage.sender_ref`, a truncated SHA-256, never the number |
| 30-day deletion | `retention.py`, `RETENTION_DAYS = 30` |
| Webhook persistence | There is none. The WSGI app holds a message for the life of one request. |

`redact()` is best-effort pattern matching over free text. It is a backstop, not
a basis for storing anything — which is why `redact_mapping()` drops known
patient-content keys entirely rather than trying to scrub their values.

## Retention

`retention.py` drives deletion against a platform API, working from ids and
timestamps; it never copies record content locally. Implement `RecordStore` per
platform:

```python
from dentaldesk.retention import purge

report = purge(my_store)          # deletes everything older than 30 days
report = purge(my_store, dry_run=True)   # lists what would go
```

A record exactly 30 days old is due. One failed deletion does not abort the
run — the report names what failed so it can be retried. Audit output is counts
and record ids only.

Run it on a schedule per clinic, and keep the reports: they are the evidence
that the retention clause in the DPA is actually being honoured.

## Emergencies

Spec §7: WhatsApp carries **no emergency transfer**. The safety message and the
practice-manager SMS are decided in `webhook.handle_inbound`, not by the model,
and the hospital is read from KNOWLEDGE — never from the model's general
knowledge of Nairobi hospitals (spec §6). If KNOWLEDGE lacks a verified
casualty, `emergency_message()` raises rather than improvising.
