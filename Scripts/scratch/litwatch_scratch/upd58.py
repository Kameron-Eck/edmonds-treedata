import io

p = r'G:/My Drive/treedata/Scripts/litwatch_robustness.md'
s = io.open(p, encoding='utf-8').read()

covered = """
### IN FLIGHT - RE-SCORING FIVE YEARS ON THE CITY FOOTPRINT (Q105) - 2026-08-19
Launched the re-score that iteration 57's new reference makes possible. **Result not yet in** - the
job exceeded the foreground limit and is running in the background; reporting it next iteration
rather than guessing at it.

**The design, which is the part worth recording now.** Same prob rasters, same deployed thresholds,
same decimation, same canopy codes - **only the reference footprint differs**:
* ref A = `ccap_2016_hires_lc.tif` - the old rectangle, 80% of the city, missing the forested north
* ref B = `ccap_2016_edmonds.tif` - clipped to `Edmonds Boundry.shp`, 100% of the city

**Any delta is therefore purely footprint**, with no confound from threshold, model version or
canopy definition. Years covered: 2000, 2002, 2013, 2015, 2017. The 2013 row doubles as a check -
it should reproduce the published .7094 on ref A, which validates the harness before its ref-B
numbers are believed.

**The prediction, stated before the result so it can be scored honestly.** The omitted north is
52.58% canopy against the south's 32.30%, and forest is where this model performs best (recall .93
at 30 m+ against .16 below 5 m). **So citywide recall should come out HIGHER than every published
figure**, by a few points. If it comes out lower, something is wrong with either the clip or my
reading of the north/south split, and that would need investigating before anything else.

**Why it matters that this is read-only.** The script writes nothing to `qc_indep_report.csv`. The
project's QC record stays as it is until Kam decides whether the city footprint becomes canonical -
which is a scoping decision, not a technical one, and it changes every number the project has
published.
"""

s = s.replace("\n---\n\n## QUEUE", covered + "\n---\n\n## QUEUE", 1)

io.open(p, 'w', encoding='utf-8').write(s)

s2 = io.open(p, encoding='utf-8').read().rstrip('\n')
s2 += ("\n| 58 | 2026-08-19 | IN FLIGHT - re-scoring 5 years on the city footprint (Q105) | - | "
       "Launched; exceeded the foreground limit and is running in background, so NO RESULT YET - "
       "reporting next iteration rather than guessing. Design: identical prob rasters, thresholds, "
       "decimation and canopy codes; ONLY the reference footprint differs (old 80% rectangle vs "
       "city-clipped 100%), so any delta is purely footprint. 2013 doubles as a harness check "
       "against the published .7094. PREDICTION ON RECORD: citywide recall should be HIGHER, since "
       "the omitted north is 52.6% canopy and forest is where the model does best |\n")
io.open(p, 'w', encoding='utf-8').write(s2)
print("ledger updated")
