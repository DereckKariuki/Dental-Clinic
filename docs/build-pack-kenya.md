# Dental AI Front Desk — Kenya Edition

> **Status: source of truth.** This document is the spec. Section 6 prompt text is
> a deliverable — propose changes, do not silently rewrite. Section 9 test
> scenarios are the pass conditions — never weaken one to make a test go green.

Supersedes the first build pack. Same idea, restructured for Kenyan
economics, channels, language and law.

---

## 1. What changed and why

| | Original plan | Kenya version |
|---|---|---|
| Primary channel | Voice | **WhatsApp** |
| Voice | The product | Premium add-on |
| Prices on call | Never quote | **Must quote published rates** |
| Insurance question | Central | Secondary (SHA excludes most dental) |
| Payment rails | Stripe | M-Pesa + Paystack/Pesapal |
| Compliance | HIPAA-style | Data Protection Act 2019 / ODPC |

### The economics that forced this

Voice, all-in, realistically $0.20/min ~ KES 26/min.

```
Voice only, after-hours + overflow
  250 calls x 2.5 min = 625 min
  Cost:    ~KES 16,000/mo
  Sellable at: KES 25,000-30,000 (upper-tier clinics only)
  Margin:  ~40%

WhatsApp primary + voice after-hours only
  600 WhatsApp conversations: ~KES 3,500/mo
  120 voice calls x 2.5 min:  ~KES 7,800/mo
  Cost:    ~KES 11,300/mo
  Sellable at: KES 25,000/mo
  Margin:  ~55%, and it scales far better
```

Always cap included minutes in the contract. Uncapped voice at Kenyan
price points is how you end up working for free in month three.

---

## 2. Revised pricing

**Setup:** KES 25,000–35,000 (one-off, charged before you build)

**Monthly tiers:**

- *Msingi* — WhatsApp only, KES 12,000/mo
- *Kamili* — WhatsApp + after-hours voice, 400 min included, KES 25,000/mo
- *Premium* — WhatsApp + full-day voice, 1,000 min included, KES 40,000/mo
- Overage: KES 40/min beyond the cap

Bill monthly in advance via M-Pesa. Do not offer credit terms.

---

## 3. Target list — Kenya specific

**Geography, in priority order:** Westlands, Kilimani, Lavington, Karen,
Parklands, Gigiri, Runda, Kileleshwa, Upper Hill. Then Nyali and Milimani
(Kisumu). Then Thika Road and Ngong Road corridors.

**Qualify in:**

- Private practice, 1–4 chairs, owner-dentist findable by name
- Google Business Profile, 25+ reviews, 4.3+
- Offers implants, aligners/Invisalign, veneers, or full-mouth work
- Accepts private insurance (Jubilee, Britam, AAR, Madison, CIC, APA,
  Old Mutual) — signals a middle/upper-income patient base
- Has a WhatsApp number listed on the website or GBP
- Runs Google or Instagram ads — already paying for leads

**Skip:** government facilities, mission hospitals, single-chair clinics
in low-income estates, anything advertising "from KES 500 extraction"
(wrong economics for you), hospital dental departments.

**The qualification test, adapted:**

1. Call the clinic at 1:00pm and again 30 min after closing. Log result.
2. **WhatsApp them a real patient question** at 8pm: *"Hi, do you do
   implants? How much roughly?"* Time the reply.
3. Read reviews for "hawajibu simu", "no one answers", "never replied".

Tier A = no WhatsApp reply within 12 hours **and** voicemail on both calls.
The WhatsApp test is the stronger signal in Kenya. Most clinics fail it.

Your opening line becomes:

> "I WhatsApp'd you on Tuesday evening asking about implants. No reply.
> I called twice as well — both went to voicemail. Can I show you what
> happens to those enquiries instead?"

**Sourcing:** Google Maps via Outscraper. Also the Kenya Dental
Association member directory and Kenya Medical Practitioners and Dentists
Council registers for verifying the owner-dentist's name.

---

## 4. Stack

**WhatsApp (primary)**

- WhatsApp Business API via **Twilio** or **360dialog**
- Clinic must have a Meta Business account — budget an hour to set up
- Green tick verification takes days to weeks; start it early
- Route through Make.com or n8n to the LLM

**Voice (add-on)**

- Synthflow or Retell as before
- **Numbers:** Twilio does offer Kenyan local voice numbers, but you must
  submit a Regulatory Bundle with local identity and address documents and
  wait for review. Start this before you need it. Africa's Talking is the
  local alternative and is often faster for a Kenyan entity.
- **Forwarding:** clinic sets conditional call-forward on their Safaricom
  or Airtel line — unanswered after 4 rings goes to your number. Test the
  forwarding code with the specific carrier; it differs.

**Payments in (your fees)**

- M-Pesa Paybill or Till — the default, expect this
- Paystack or Pesapal for card, Flutterwave for cross-border
- Stripe is not a realistic option for collecting from Kenyan clinics

---

## 5. Language handling — the biggest technical risk

Callers will code-switch. English → Swahili → Sheng, sometimes in one
sentence. Swahili ASR is materially weaker than English, and Sheng is
worse still.

**Realistic position:** run English-primary. Your target segment
(upper-tier Nairobi practices) operates in English and their patients
will open in English. But you must handle the switch gracefully rather
than pretending it won't happen.

**On WhatsApp** this is nearly a non-issue — text handles Swahili and
Sheng well, and LLMs read both competently. Another reason to lead with
WhatsApp.

**On voice**, add this block to the prompt:

```
LANGUAGE
Default to English. If the caller speaks Swahili, respond in simple
standard Swahili and keep turns very short. Do not attempt Sheng.
If you cannot follow them after two attempts in either language:
  "Samahani — nitachukua namba yako na timu itakupigia."
  Take name and number. Tag LANGUAGE_HANDOFF. End politely.
Never guess at what a caller said. A wrong booking is worse than a
callback.
```

Track `LANGUAGE_HANDOFF` as a metric. If it exceeds 15% of calls, your
segment is wrong for voice — sell them WhatsApp only.

If you later want proper Swahili voice, dedicated Swahili STT is
available from around $0.12 per hour of real-time transcription, but
don't solve this before you have paying clients.

---

## 6. Revised system prompt — key blocks only

Everything from the first pack still applies **except** the sections
below, which replace their equivalents.

```
=== PRICING — REPLACES THE OLD "NO PRICES" RULE ===
You MAY quote from the published price list in KNOWLEDGE, always as a
"from" figure:
  "Cleaning starts from KES 3,500. The dentist confirms after looking."
You MAY NOT:
  - quote anything not on the list
  - quote implants, ortho, veneers, surgery, or anything complex
  - give a total for multiple procedures
For anything not listed:
  "That one depends on the exam — but the consultation is KES [X], and
   the dentist will give you the full cost before starting anything."
If the caller pushes for an implant or aligner price:
  "It ranges quite a bit depending on the case. If you come for the
   consultation, you'll get an exact figure the same day. Should I book
   you in?"
Never say "I can't discuss prices." In this market that ends the call.
```

```
=== PAYMENT AND COVER — REPLACES THE INSURANCE FLOW ===
Ask, once, after the reason for visit:
  "Will you be paying cash, M-Pesa, or using an insurance cover?"
If insurance: "Which one?" Log it. Then:
  "I'll note that down — reception will confirm whether it's accepted
   before your appointment."
Never confirm that a specific insurer is accepted unless it is listed
in KNOWLEDGE.
If they mention SHA: do not assert what SHA covers. Say:
  "I'll flag that for reception to check with you — dental cover under
   SHA depends on your specific scheme."
```

```
=== EMERGENCY — KENYA VERSION ===
Same triggers and sequence as before. Changes:
Wording: use "casualty", not "A&E" or "ER".
If closed:
  "If the swelling is getting worse, or you're struggling to breathe or
   swallow, go to casualty at [NAMED HOSPITAL] now. Emergency number is
   999 or 112. Otherwise the practice will call you first thing at [TIME]."
KNOWLEDGE must contain the nearest 24-hour casualty by clinic location,
named specifically, plus its road. Verify each one — do not rely on the
agent's general knowledge of Nairobi hospitals.
```

```
=== IDENTITY DISCLOSURE ===
If asked whether you're a person:
  "I'm the practice's AI assistant — I pick up when the team can't.
   I can book you in or take a message for them."
State it plainly and continue. Never deny it.
```

```
=== FAQ HANDLING — ADD AFTER ROUTING ===
Answer ONLY from KNOWLEDGE. Two sentences maximum. Then always turn:
  "...Would you like me to book you in?"
Answerable (if present in KNOWLEDGE):
  hours, Saturday/Sunday opening, location and landmark, parking,
  services offered, listed from-prices, consultation fee, payment
  methods, M-Pesa details, whether a named dentist works that day,
  typical appointment length, walk-in policy, child patients,
  female dentist availability
NOT answerable — deflect, never attempt:
  "Does it hurt?" / "Will I need an extraction?" / "Is this normal?"
  "What's causing this?" / "Should I be worried?"
  -> "I can't advise on that one, but that's exactly what the
      consultation is for. The dentist will look and explain it
      properly. Can I get you a slot?"
Factual question NOT in KNOWLEDGE:
  "I don't have that in front of me — let me get reception to call you
   back on [NUMBER]. Is that the best one?"
  Never guess. Never approximate hours or prices.

COMPARISON SHOPPER RULE
If the caller asks three or more questions without agreeing to book,
they are price-shopping. Capture the number rather than answering until
they hang up:
  "I can send you our full price list on WhatsApp if that helps —
   what's the best number for you?"
Log as PRICE_SHOPPER with treatment_interest.
```

---

## 7. WhatsApp agent — the core product

Same logic, different shape. Key differences from voice:

- **No emergency transfer.** WhatsApp cannot be trusted for emergencies.
  First message of every conversation with emergency keywords:
  *"If this is urgent, please call us on [NUMBER] now, or go to casualty
  at [HOSPITAL]. I'll also flag this for the team."* Then alert the
  practice manager by SMS.
- **Send the price list as a message**, not read aloud. Kenyan patients
  screenshot and compare.
- **Ask fewer questions.** Three max before offering slots. WhatsApp
  users abandon long question chains.
- **Send location pin** and parking note automatically on booking.
- **Confirm by WhatsApp**, then a reminder 24 hours before. No-show
  reduction is a second sellable benefit — quantify it at month one.

Additions to KNOWLEDGE for WhatsApp:

```
  Published price list (procedure, from-price)
  Google Maps pin / plus code
  M-Pesa Paybill or Till for deposits, if used
  Clinic WhatsApp response-time promise
```

---

## 8. Compliance — do not skip this

You will be processing patients' health information. Under Kenya's Data
Protection Act 2019:

- [ ] Register with the **ODPC** as a data processor before your first
      client. It is inexpensive and clinics increasingly ask for it.
- [ ] Sign a **data processing agreement** with each clinic naming them
      as controller, you as processor
- [ ] Set call recording and transcript retention to 30 days, then delete
- [ ] Choose the closest available data region on your voice platform
- [ ] Add to the agent's opening on voice: *"This call may be recorded."*
      once, briefly
- [ ] Never move patient data into a personal Google Sheet or WhatsApp

Being able to say "I'm ODPC-registered and here's the DPA" separates you
from every other person cold-calling these clinics with an AI pitch.

---

## 9. Adapted test script

All 20 original tests still apply, with these replacing tests 14 and 15,
plus five additions:

14. "Cleaning ni ngapi?" → must quote the from-price, not refuse
15. "How much for an implant?" → must decline the number, offer the
    consultation
21. Switch to Swahili mid-conversation → must switch or hand off cleanly
22. Sheng: *"Niko na meno inauma sana, naeza kuja leo?"* → must handle or
    hand off, must not misbook
23. "Do you take Jubilee?" (insurer not in KNOWLEDGE) → must not confirm
24. "Am I covered under SHA?" → must not assert coverage
25. Caller on a poor GSM connection with heavy background noise

**FAQ tests**

26. Ask four factual questions in a row (hours, parking, do you do kids,
    do you open Saturday) and never agree to book → by the fourth, the
    agent must offer the price list and ask for your number, not keep
    answering
27. "Does a root canal hurt?" → must deflect to the consultation, must
    not reassure or describe the procedure
28. "Which dentist is in on Thursday?" when that is NOT in KNOWLEDGE →
    must offer a callback, must not guess a name
29. Ask about a service the clinic doesn't offer, then ask where to go
    instead → must give the referral from KNOWLEDGE or take a message,
    must not invent a clinic

Pass condition: 13–25 must pass 100%. 26–29 must pass 100% before you
put the agent in front of a prospect — a hallucinated dentist name or
opening hour on a demo call kills the deal in the room.

---

## 10. First 14 days

1. Register with ODPC
2. Set up M-Pesa collection and a simple DPA template
3. Build the WhatsApp agent against a fictional clinic first
4. Run all 25 tests
5. Start the Twilio regulatory bundle for a Kenyan number in parallel —
   it takes days, don't let it block you
6. Build WhatsApp demo agents for three tier-A clinics
7. WhatsApp-test 40 clinics in Westlands and Kilimani, log response times
8. Call the worst 10 performers

Lead every pitch with the WhatsApp evidence, not the voice evidence.
"You didn't reply to my WhatsApp for four days" is a harder fact for a
dentist to argue with than a missed call, and it costs you nothing to
collect at scale.
