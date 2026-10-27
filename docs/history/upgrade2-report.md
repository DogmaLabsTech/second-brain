# Upgrade 2 report: the local decider says "I don't know" (2026-10-16)

- **What changed:** the local decider's round 5 is now in use. It was trained on 417 "unsure" practice texts (off-topic,
  cut-off speech, things with no job). Each answer now needs to be sure enough to be trusted, or it's sent on.
- **Before → after (110 fair test texts):**
  - Right: 84.5% → 90.0%.
  - Sure and wrong (confident and mistaken): 9 → 6 texts (8.2% → 5.5%).
  - Unsure texts caught: 14 of 25 → 22 of 25.
- **Caveat:** the sure-bars were picked on the same 110 texts, so the real rate may be a little higher. <user>'s own
  real asks aren't in the test yet.
- **Decision for <user>:** none needed now. Say if you want the second decider to take the uncertain asks (current rule for
  non-private texts), or if you want "Sorry, say that again?" to show up for private texts as it does now.
