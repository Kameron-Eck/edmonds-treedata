import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 27 - batch norm under domain shift - 2026-08-18 - IDs 140-141
**Q9 ANSWERED, and v039 was right - but for a reason we had not articulated.**

The apparent contradiction was: v039 set `FREEZE_ENCODER_BN=True` because BN drift was the prime
suspect for the E6 cliff, while every BN-adaptation method (AdaBN, TENT) requires the opposite.
Both are correct, because **they disagree about WHEN the statistics are estimated, not about
whether BN carries domain information.**

* **Both camps agree BN encodes DOMAIN-SPECIFIC statistics** (ID 140, Li et al. 2018, Pattern
  Recognition, peer-reviewed). That is the shared premise.
* **Freezing is right when statistics would be estimated from small, noisy, off-distribution
  batches** - the standard fine-tuning guidance, and precisely our situation at the E6 cliff
  (citywide coarse pool, batch 32, ~83% background before the v039 sampler fix).
* **AdaBN estimates over the WHOLE target domain, offline** - not per batch. So it never had the
  instability that motivated our freeze. v039 and AdaBN were never really in conflict.

**The design that resolves it (ID 141, Chang et al. CVPR 2019, DSBN):** do not choose. Keep a
**separate BN branch per domain**, all other weights shared. Each branch is estimated over a whole
domain offline, so there is no small-batch instability, and each year gets statistics matched to
its own radiometry.

**And it composes with iteration 11.** One BN branch per **RADIOMETRIC CLUSTER**, not per agency -
because agency predicts the nearest neighbour only 47% of the time. This is the strongest
candidate the loop has produced for replacing the per-(sensor x era) anchor idea with something
the network actually implements rather than something we assert in a config.

**A cheap variant worth knowing:** fine-tuning ONLY the BN affine parameters (scale and shift)
reportedly reaches performance close to full fine-tuning, with faster convergence. Given our
Colab-only training budget and labels for one year, per-year BN-affine-only tuning is about the
cheapest per-domain adaptation available - far cheaper than the full per-year fine-tunes we run now.

**What this does NOT resolve:** whether the E6 cliff would still appear with the v039 sampler fix
in place. The freeze and the sampler fix landed together, so the freeze has never been tested
alone on a healthy sampler. Q9 becomes an experiment, not a reading question.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

old_q9 = """- **Q9.** Is `FREEZE_ENCODER_BN=True` (v039, adopted empirically on 2016) actually right
  across all 18 years, or did we generalize a one-year result? It now sits in direct
  conflict with every BN-adaptation method. Cheap to test: unfreeze on two contrasting
  years and re-score against C-CAP."""

new_q9 = """- **Q9.** Is `FREEZE_ENCODER_BN=True` (v039) right across all 18 years? **RESOLVED AS A
  CONFLICT (Search 27):** there was none. Freezing is correct when statistics come from small,
  noisy batches (our case at the E6 cliff); AdaBN estimates over the whole target domain offline,
  so it never faced that instability. DSBN (ID 141) does both - a BN branch per domain.
  **Residual experiment:** the freeze and the v039 sampler fix landed together, so the freeze has
  never been tested alone on a healthy sampler. Unfreeze on two contrasting years and re-score.
- **Q25.** Would per-domain BN branches (DSBN), keyed on the iteration-11 radiometric clusters,
  outperform our current per-year full fine-tunes? It is cheaper (shared weights, per-domain
  statistics only) and it implements the anchor idea in the network rather than asserting it in
  config. Untested, and it depends on Q19/Q22 - the clusters must be re-derived over all 18
  acquisitions first, including the 2002/2012 the current screen omitted.
- **Q26.** Does BN-affine-only fine-tuning suffice per year? Reported near-parity with full
  fine-tuning at a fraction of the cost. If true for us it changes the Colab budget completely -
  and it would let us adapt years we currently cannot afford to retrain."""

assert old_q9 in s, "Q9 anchor not found"
s = s.replace(old_q9, new_q9, 1)

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 15 | 2026-08-18 | Search 27 - batch norm under domain shift | 140-141 | "
       "Q9 RESOLVED: no real conflict - freeze is right for small noisy batches, AdaBN estimates "
       "over the whole domain offline. DSBN (per-domain BN branches) does both and composes with "
       "the iteration-11 radiometric clusters - strongest candidate yet to replace agency-keyed "
       "anchors. BN-affine-only tuning may give near-parity at a fraction of Colab cost |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
