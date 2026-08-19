import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### Search 47 - INTERVAL-CENSORED & DEMOGRAPHIC FRAMING - IDs 181-182
The deliverable is called a per-crown temporal VALIDITY INTERVAL. Thirty-five iterations in, this
is the first search of the statistical framework that name describes.

**OUR DATA IS INTERVAL-CENSORED, AND THE OBVIOUS HANDLING OF IT IS A KNOWN ERROR (ID 181).**
When subjects are assessed periodically, the event is known only to have occurred BETWEEN two
visits. An epoch-pair canopy series produces exactly that: *this crown was present in 2013 and
absent in 2016*. The warning that matters:

> assigning the event to the MIDPOINT or END of the interval is a known source of bias and invalid
> inference.

Midpoint assignment is precisely what a canopy-loss analysis would do without thinking - plot
losses at 2014.5 and fit a trend. The Turnbull estimator handles interval censoring properly. This
should be settled before any per-crown loss date is analysed, plotted, or handed to a policy
audience, because the bias enters at the moment of tabulation rather than at the model.

**AND THE DELIVERABLE IS A DEMOGRAPHIC PRODUCT, NOT ONLY A MAPPING ONE (ID 182, Hilbert et al.
2019, AUF).** Survival curves, life tables and mortality rates are the native vocabulary for
per-crown outcomes over time, and urban forestry already has that literature. Reframing this way
also makes our numbers comparable to existing urban-forest research rather than only to remote
sensing.

**IT ALSO SUPPLIES THE PRIOR WE HAVE BEEN GUESSING AT.** Typical street-tree annual mortality is
**3.5-5.1%**, with 0.6-68.5% across cohort studies and 0-30% for repeated inventories of uneven-aged
trees. Compounded over an epoch gap:

| gap | @3.5%/yr | @5.1%/yr |
|---|---|---|
| 2 yr | 6.9% | 9.9% |
| 3 yr | 10.1% | 14.5% |
| 4 yr | 13.3% | 18.9% |
| 8 yr | 24.8% | 34.2% |

**Search 41 assumed 4.0% and 6.0% discordance and concluded 750 paired points resolve a 2.6 pp
effect.** At a 3-4 year gap the LOSS side alone plausibly reaches 10-19% for street trees, which
lands in the "heavy false change" row where precision degrades to 3.7 pp. **Our paired-precision
estimate may be optimistic**, and Q50 (measure the real discordant rate) moves from prudent to
necessary.

**The honest counterweight, which may rescue it.** These are STREET-TREE COUNT mortality rates, and
our measurement is canopy AREA at a point. Small trees dying remove little canopy, growth of
survivors adds it, and whole-canopy turnover is far lower than street-tree turnover. So the
discordance at a randomly placed point is likely well below these figures - but nobody has
checked, and the direction of the error is the one that matters.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

s = s.replace("""- **Q50.** What is the true discordant (change) rate between our year-pairs? Paired precision
  depends entirely on it, and our estimates (4%/1.4%, 6%/3.4%) are guesses. The P2 agreement
  partition could bound it from raster data before any human interpretation, which would let us
  size the sample properly instead of assuming.""",
"""- **Q50.** What is the true discordant (change) rate between our year-pairs? **NOW URGENT
  (Search 47).** Street-tree annual mortality of 3.5-5.1% compounds to 10-19% over a 3-4 year gap,
  which is well above the 4-6% our Search 41 precision estimate assumed and lands in the range where
  750 points no longer resolve 2.6 pp. Counterweight: those are tree-COUNT rates and we measure
  canopy AREA at a point, where turnover is lower. **Measurable from the P2 partition before any
  human interpretation** - and it must be, because the sample size depends on it.
- **Q61.** Is per-crown loss being tabulated at interval MIDPOINTS anywhere in the pipeline or the
  planned analysis? Midpoint assignment for interval-censored events is a documented source of bias
  (ID 181), and it is the natural thing to do when plotting a loss trend. Check before any temporal
  trend is drawn; use Turnbull-style estimation instead.
- **Q62.** Should the deliverable be reported demographically - survival curves and life tables
  rather than percentage-cover time series? It is the native framing for per-crown outcomes, makes
  our results comparable to urban-forest research rather than only to remote sensing, and survives
  the epoch-pair constraint (Q60) that percentage-cover trajectories do not.""")

old_q_start = s.index("## QUEUE - uncovered angles, highest value first")
old_q_end = s.index("---\n\n## OPEN QUESTIONS")
new_q = """## QUEUE - uncovered angles, highest value first

1. **Turnbull / non-parametric estimation for interval-censored events** - the concrete method
   behind Q61, and the deliverable's own statistics.
2. **Geometric vs thematic accuracy for per-object products (Q41)** - oldest unaddressed item.
3. **Conformal interval SHARPNESS for structured outputs** - unanswered half of Q11, deferred six
   times.
4. **Canopy AREA turnover vs tree-COUNT mortality** - the counterweight in Q50; what does the
   urban-forest literature say about area-based turnover rates specifically?
5. **Spatially-aware pseudo-labelling** - the good half of SpADANN.
6. **How the Landsat/MODIS harmonization community validates a multi-decade series.**
7. **Instance-norm / whitening for style removal.**
8. **Shadow masking as IGNORE vs removal.**
9. **Ladder-side-tuning and cheap foundation-model adaptation.**
10. **Broadleaf / deciduous-specific crown segmentation** - known blind spot, still unread.

**NOT a literature item, still the highest-leverage action:** recover the acquisition dates.

"""
s = s[:old_q_start] + new_q + s[old_q_end:]

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 35 | 2026-08-18 | Search 47 - interval-censored & demographic framing | 181-182 | "
       "FIRST SEARCH OF THE FRAMEWORK THE DELIVERABLE IS NAMED AFTER. Our data is interval-censored "
       "and assigning events to interval MIDPOINTS is a known bias - exactly what a loss-trend plot "
       "would do (Q61). Deliverable is a DEMOGRAPHIC product: survival curves, life tables. "
       "Street-tree mortality 3.5-5.1%/yr compounds to 10-19% over a 3-4yr gap, ABOVE the 4-6% "
       "Search 41 assumed -> paired-precision estimate may be optimistic, Q50 now urgent |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
