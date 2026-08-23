# The Edmonds Tree-Canopy Imagery Campaign, Plain English

*A running, non-technical account of the effort to collect better historical aerial
photos of Edmonds. This page is rewritten in place after each update — read it as
the current picture, not a stacked log.*

## 1. What this campaign is

This campaign is part of a larger project studying how Edmonds' tree canopy — its
trees and green cover — has changed between 2000 and 2024, using historical aerial
photographs of the city. Most of the aerial photos we currently have on hand are
compressed copies pulled from web mapping services — similar in spirit to zooming
into an online map — which look fine at a glance but have had real detail smoothed
away, and don't cover every year we'd like. This campaign goes back to the original
sources — county and federal map servers, and eventually the counties directly — to
collect sharper, truer copies of these photos, fill in more years of coverage, and,
wherever possible, capture a "near-infrared" version of each one. Near-infrared is a
color of light just beyond red that human eyes can't see but healthy leaves reflect
strongly — it's the single most useful clue a photo can carry for telling "this is a
tree" apart from everything else in the picture.

## 2. Where things stand right now

*(as of 1:40 PM Pacific, August 23, 2026)*

- Biggest news of the day: the 2018 coverage gap is closed. The project had zero
  citywide photo coverage for 2018 until now; a county server delivery (6-inch
  detail, real infrared, ~21 cm sharp) fills it, and every year from 2015 through
  2024 now has at least one infrared-bearing photo set.
- Fourth replacement: 2023. The old federal copy covered just 69% of the study
  rectangle and was slightly softened by its server; the true originals (from a
  public archive Microsoft hosts) give full coverage and 41% more real detail, all
  shot the same day, October 7, 2023.
- Three historical black-and-white years landed (1990, 1998, 2001) — kept as
  historical context but deliberately left out of the machine-learning training
  set, since they're single-color only. None has a known flight date, so they're
  honestly marked "date not found" rather than guessed.
- A small but important tool bug was caught and fixed: a wrong guess at a web
  address used to crash an entire download batch; now one bad guess is recorded as
  a single failure and the rest of the batch keeps going.
- Google Drive's backlog cleared: Kam emptied the trash, and all the files that had
  been waiting — the 2021 and 2015 county photos, plus the still-quarantined NOAA
  land-cover files — copied over.
- Now downloading: the county's 2002, 2003, and 2007 color photos; the 2002 one is
  mainly a check for whether it duplicates the original 2002 photo already secured
  this morning.
- Running total: 16 files landed today, 4 full years replaced (2016, 2002, 2021,
  2023), the 2018 gap closed, and the catalogue now documents 44 rows.
- Still waiting on Kam: the four drafted permission emails and the duplicate-2017
  decision. Still waiting on NOAA: the land-cover licence answer.

## 3. What happens next

- Let the 2002/2003/2007 batch finish; if 2002 turns out to duplicate the original
  already secured this morning, skip storing it a second time.
- Kam sends the four drafted permission emails and decides on the duplicate 2017
  file.
- Once NOAA answers the land-cover licence question, release that file from
  quarantine for use as a scoring reference.
- Continue through the remaining planned years in batches, saving 2020, 2022, and
  2024 for last, each with its own small test and sign-off.
- Keep an eye out for more gap years like 2018 turned out to be — the county and
  federal archives have already given more than expected.

## 4. Timeline

*(newest first)*

### 1:00–1:40 PM — Tally: 16 files landed, 4 years replaced, the 2018 gap closed

Today's running total is now 16 new or replacement photo files landed, four full
years upgraded to measured-better versions (2016, 2002, 2021, and 2023), and — the
biggest single win of the day — the 2018 coverage gap closed entirely. The
project's catalogue now documents 44 rows. Two things are still waiting on Kam: the
four drafted permission emails, and a decision on the duplicate 2017 file.

### 1:00–1:40 PM — Now downloading: the county's 2002, 2003, and 2007 color photos

A new download batch is running for the county's own 2002, 2003, and 2007 color
photos. The 2002 one is mostly a check rather than a true addition: it exists to
test whether it's simply a duplicate of the original 2002 government photo already
secured earlier today — if it matches, that will be recorded and the county copy
won't be stored a second time.

### 1:00–1:40 PM — Three historical black-and-white years land: 1990, 1998, and 2001

Three older, black-and-white photo sets landed today: 1990 (a coarser 10-foot
pixel size), 1998 (which turns out, per a file path the server accidentally
revealed, to actually be a Washington State Department of Natural Resources
product), and 2001 (scanned from film, and honestly measured at roughly 1 meter per
pixel — noticeably blurrier than its official, nominal resolution claimed). None of
the three has a known flight date anywhere in the records, so rather than guess,
they're catalogued plainly as "date not found." All three are being kept as
historical context, but deliberately left out of the set the computer model
actually trains on, since they only carry a single black-and-white band rather than
full color.

### 1:00–1:40 PM — A wrong guess crashes a download, and teaches two lessons

While reaching for the 2019 federal photos, the downloader guessed a web address
that turned out to be wrong — Microsoft names its 2019 folder "wa_60cm_2019" but
its 2023 folder "wa_060cm_2023," a small, inconsistent difference (a missing zero)
between years. That wrong guess used to crash the entire download batch; the tool
has now been fixed so a single failed guess is simply recorded as one failure while
everything else keeps going. The fix was tested and saved to the project's
permanent records, and the 2019 download is now re-running with the correct
address.

### 1:00–1:40 PM — Fourth replacement: 2023, sourced from a Microsoft-hosted public archive

The 2023 federal photo has been replaced, the fourth full replacement of the day.
The version the project had been holding was cut off at just 69% of the study
rectangle and slightly softened by the server it came from; the 8 original files —
pulled from a copy of the same federal photos that Microsoft hosts publicly
online — give full coverage and measurably more real detail, 41% more on a fair,
like-for-like comparison. Their file names confirm every one of the 8 was
photographed on the same single day, October 7, 2023.

### 1:00–1:40 PM — The 2018 gap is filled: the project's biggest missing year now has real coverage

Until today, the project had no citywide photo coverage at all for 2018 — the
timeline jumped straight from 2017 to 2019, with only the small, limited Edmonds
Marsh drone survey (and its fake infrared band) standing in for that year. That gap
is now closed: Snohomish County's server turns out to also carry the state imagery
consortium's 6-inch 2018 flight, photographed on a single day, August 7, 2018 — by
pure coincidence, the same calendar date as the 2015 flight, just three years
apart. It landed as an 11.5-gigabyte, four-band file with genuine near-infrared,
resolving real detail down to about 21 cm. With this file in hand, every year from
2015 through 2024 now has at least one summer-or-fall photo set that includes a
real infrared band.

### 1:00–1:40 PM — Google Drive's backlog clears: Kam empties the trash

Kam emptied Google Drive's trash today, finally reclaiming the space that
yesterday's deleted one-terabyte folder had been silently holding onto. That
unblocked a backlog of files waiting to be copied to Drive: the 2021 and 2015
county photos went through, along with the still-quarantined NOAA land-cover
files — which, worth noting, live in a quarantine folder on Drive too, never in the
folder the project's actual pipeline reads from.

### 12:00–12:50 PM — Tally: 11 files landed, three years now measurably replaced

The day's running total is now 11 new or replacement photo files landed, with three
full years upgraded to measured-better versions: 2016, 2002, and 2021. The
project's catalogue — the master list every downloaded file gets formally logged
into — now documents 39 rows. True to how this whole campaign has run, every single
claim about a new file's quality is being independently measured on arrival, never
just taken on faith.

### 12:00–12:50 PM — A new batch begins: the only 2018 photos anywhere, plus three historical black-and-white years

A fresh batch of downloads is now running. It includes the 2018 county photos at
6-inch detail — notable because, as far as the project has found, this is the only
aerial coverage of Edmonds from 2018 anywhere, and it includes a real infrared
band. Alongside it: three small, older black-and-white photo sets from 1990, 1998,
and 2001, which push the project's historical record further back in time.

### 12:00–12:50 PM — The land-cover reference file checks out: 99.8% agreement with what we already had

The large NOAA land-cover reference map (1.4 gigabytes) has now fully arrived, and
it was checked category by category against the smaller cutout of the same map the
project has already been using to score its results. The two agree on 99.8% of
pixels — the tiny remaining disagreements are just boundary jitter from slightly
different map projections, not real differences in how the land is classified.
That's reassuring: the scoring reference already in use is confirmed trustworthy,
and the new, larger file will eventually add wider coverage and clearer
provenance — documentation of exactly where the data came from and how it was
produced. For now it stays untouched in the same set-aside folder as before, still
waiting on NOAA's answer about the licence.

### 12:00–12:50 PM — The 2015 county photos land — sharper, but no real infrared after all

The county's own 2015 photos also arrived — essentially a third copy of the same
August 7, 2015 flight the federal (NAIP) photos captured earlier today, but the
county's version is about three times sharper (roughly one foot per pixel versus
the federal set's one meter). Its fourth color band was supposed to be
near-infrared but, like the Marsh drone survey earlier, turned out to be an empty
placeholder rather than real infrared data — so, recorded honestly, it's being
filed as a plain three-color photo, not a four-band one.

### 12:00–12:50 PM — The 2021 photo replaced: same photos, but genuinely sharper this time — the third replacement of the day

The 2021 county photo is the third full replacement of the campaign, and it fixes
the second of the two badly cropped files the project started the day with (2016
was the first, fixed this morning). The new download covers the project's entire
study rectangle — the old copy covered under 40% of it — at the same fine, 6-inch
detail. This time, unlike the 2016 replacement, the new file is also measurably
sharper: on a fair, same-grid comparison it carries 43% more real detail than the
old one. The reason isn't a different or better original photograph — it's the
exact same 2021 flight — but the old download tool had quietly asked the server to
soften the pixels slightly on the way down, while the new tool copies them exactly
as recorded. The full download came through in 875 pieces with zero failures,
totaling 10.8 gigabytes.

### 10:42 AM — Four permission emails drafted, waiting on Kam to send

Four emails — each one only Kam can send — were drafted and saved to a file for his
review: one to King County asking for original, uncompressed imagery tiles,
including the 2000 color-infrared photos that are the source for our earliest year;
one to Snohomish County about its licensing position and for flight logs that would
pin down the exact dates the 2020, 2022, and 2024 photos were taken; one to the
state's imagery-sharing consortium asking about access to their sharper 6-inch
products; and one to NOAA about the land-cover map's contradictory licence wording.
Two more small items are waiting on Kam alongside the emails: emptying Google
Drive's trash to actually reclaim the space from yesterday's folder deletion, and
deciding what to do about a duplicate copy of the 2017 photo already on file. (The
full numbers behind today's 2016 replacement are recorded in IMAGERY_FACTS.md,
section 10, for anyone who wants the technical detail.)

### 10:15–10:40 AM — Federal photos start downloading; a slow start gets fixed

Attention shifted to a new batch: federal aerial photos for 2015, 2017, and 2021
from NAIP — the National Agriculture Imagery Program, a USDA (the federal
agriculture department) effort that photographs the whole country every year or
two, freely available — plus a NOAA land-cover reference map for 2021 (C-CAP). All
of these include a near-infrared band. The download started slowly: one file at a
time at only about 1 megabyte per second, on pace to take 90 minutes for 5.9
gigabytes of data. The tool was changed to fetch six files simultaneously instead of
one, and the download restarted without losing progress — files that had already
finished were kept, and a couple of partially-downloaded ones were cleaned up
first. The land-cover map is being kept in a "quarantine" folder that no part of the
project's software will read from, because its posted usage terms contradict
themselves about whether it can be used to help check a computer model — one part of
the fine print says no for five years, another part says something narrower. NOAA
has been asked to clarify.

### 10:10 AM — The new 2016 photo is now safely stored in two places, and the project is officially using it

The new 2016 photo is now saved in both of the project's storage locations — the
local computer and Google Drive — as the exact same file (2,586,179,492 bytes on
each, matching the roughly 2.59 GB reported earlier), matched by a verified
checksum, its digital fingerprint. The project's catalogue — its master list of
which imagery file represents each year — was updated to point 2016 at this new
file; the old, superseded file isn't deleted, just kept on hand and clearly labeled
as replaced. An automated catalogue check confirmed all 18 entries in that list are
in good order, and a separate pre-flight check — a go/no-go check the project always
runs before expensive computing jobs — also came back clean. One side effect,
expected and by design: the next time the computer-training process touches 2016
imagery, it will automatically rebuild its tile cache — small pre-cut pieces of the
photo — from scratch, since the system always checks whether the source photo has
changed before reusing old pieces.

### 10:05 AM — A second measurement bug found and fixed: pixel size was being over-read by 2.5%

A second bug turned up in the measuring tools themselves: the inherited method for
computing a photo's true pixel size — how much ground each dot covers — was
consistently reading about 2.5% too high (31.3 cm instead of the correct 30.48 cm,
which is exactly one foot). The cause: that method converts the map's grid into
GPS-style latitude/longitude to measure distances, but this particular map's grid is
tilted relative to true geographic north, and the conversion didn't fully account
for the tilt. It's now fixed to convert the units directly and exactly, with the old
approach kept only as a rough cross-check rather than the source of truth. With the
bug fixed, a fair comparison shows the old and new 2016 photos actually resolve
almost exactly the same amount of real detail (a ratio of 1.01) — which makes sense,
since they're built from the same original photographs. This also revises what was
reported at 9:30 AM below: the "18% more detail" reading from that early pilot test
turned out to be an artifact of this same bug. The real, confirmed advantage of the
new photo isn't extra sharpness — it's complete coverage of the city and pixels that
are the camera's true, unblurred readings rather than a server-smoothed copy.

### 10:00 AM — A rejection that taught us our own rule was wrong, not the file

When the finished 2016 photo was checked against the project's acceptance rule, it
was unexpectedly rejected — the rule said it only covered 82% of the project's
"study rectangle," the fixed rectangular boundary used to line up every year's photo
so they all overlap exactly. But the file wasn't the problem; the rule was. That
rectangle's northwest corner sits over Puget Sound, and no aerial photo — old or
new — will ever have pixels over open water, so measuring coverage against the whole
rectangle (water included) was never a fair test; the project already knew roughly
83% of that rectangle is land. A fairer, second measurement was added: coverage of
Edmonds' actual city boundary, water excluded. By that measure, the new photo covers
100% of the city — the old, clipped photo we'd been using covered only 67%. Verdict:
the new photo replaces the old one, with no downsides found.

### 9:55 AM — All 234 pieces became one picture, and a spot check found nothing wrong

The downloaded pieces of the 2016 photo were stitched together into a single file —
2.59 gigabytes, roughly the size of a two-hour movie downloaded in HD. To make sure
the stitching itself hadn't introduced any mistakes, 12 pieces were picked at random
and compared, dot for dot, against the same spot in the finished picture; every one
matched exactly, with zero differences. This means we now have one seamless,
verified photo of Edmonds from 2016, built honestly from checked pieces rather than
a patchwork with hidden seams — and it's the file that may go on to replace the
older, blurrier 2016 photo we've been using. Next: measure it properly and make that
call.

### 9:40–9:50 AM — The full 2016 download finished clean: 234 pieces, zero failures

The complete photo was pulled from Snohomish County's map server in 234 pieces, and
every single one arrived successfully — none missing, corrupted, or refused. Thirty
of those pieces came back empty, but in a telling pattern: they form a neat diagonal
staircase in the northwest corner, tracing the shoreline of Puget Sound. That's
expected — there's no land under open water, so there's nothing to photograph
there. The whole download took about 9.5 minutes at an average speed of 5.8
megabytes per second, a bit slower than the 10–13 MB/s predicted. The cause: each of
the download's parallel connections could only pull about 2 megabytes per second on
its own, and the server quietly ignored our request to compress the data before
sending it. Fix for next time: open more parallel connections to make up the
difference. Getting a clean, complete download on the very first real run is a
strong sign the new tool actually fixed the old one's problems.

### 9:30 AM — A small real-world test catches two surprises before the big download

Before committing to downloading the whole 2016 photo, a small test was run over a
real 500-meter (roughly five-city-block) square of it. The results were reassuring:
the pieces stitched together matched a plain, direct download of the same area
exactly (zero differences); a check comparing "copy the real pixel" against "blend
neighboring pixels" came back identical, proving the server was honoring our request
and handing back real, unblended camera readings; the fourth color band checked out
as genuine near-infrared, not a fake or empty channel; and there was no fingerprint
of JPEG-style quality loss anywhere in the file. Two things did surprise us. First, a
standard sharpness measurement (measured in centimeters of ground distance — smaller
means crisper) actually read worse on the new, correctly-scaled photo (41 cm) than
on the old "zoomed-in" copy we already had (34 cm) — even though the new version
appeared to contain 18% more real detail. The reason given at the time: that
sharpness ruler can't measure anything finer than one pixel, so comparing two photos
with different pixel sizes gives a misleading answer; the rule going forward was to
only compare sharpness between photos on the same pixel grid. Second, asking the
server to compress the data on its way to us made no difference at all, and
requesting the largest possible piece size caused the server to fail outright — so
the download kept using modest, roughly-2,000-pixel pieces. *(Correction, 10:05 AM:
that "18% more detail" reading was later found to be thrown off by a separate units
bug in the measuring tool — see the 10:05 AM entry above for the corrected,
fairer comparison.)*

### 9:25 AM — Twelve practice runs against a fake, deliberately broken server, all passed

Before ever touching the real map server, the new downloading tool was rehearsed
against a pretend one built to fail in specific ways: pieces that arrive cut off
partway through, pieces the server refuses to hand over at all, a piece that simply
never shows up, and a response with fewer color bands than expected (missing the
near-infrared channel). In every case, the tool correctly noticed and flagged the
problem rather than quietly accepting bad data. This is the rehearsal that earns a
tool the right to run against a real server with real time and real data on the
line.

### 9:05 AM — The old download tool turns out to have 15 problems; a new one is built from scratch

A review of the download script last used in March turned up 15 separate defects.
Among the more serious: it silently told the server to blur every photo slightly,
even when no blurring should have been needed at all; when the server refused to
hand over a piece, the old tool just left a blank gap in the final picture with no
record that anything had gone wrong; and if you changed even one small setting
partway through a long download, it would forget everything already downloaded and
start over from zero. A new downloader was written from scratch around fixes for all
15 issues. It also keeps a "ledger" — a running receipt of every single piece it
downloads, including its size, a fingerprint to prove it wasn't corrupted, and how
long it took — so an interrupted download can pick up where it left off, and so we
can tell exactly where and why things slow down. This mattered because these
downloads run long and unattended; a tool that quietly hides its own failures could
waste hours before anyone noticed.

### 9:00 AM — Kam approves the campaign and sets four ground rules

Kam reviewed the plan for re-collecting Edmonds' historical aerial photos and gave
it the go-ahead, with four decisions. First, proceed with downloading every year
Snohomish County has available through its public map website — treating public
availability as workable permission for now, while still sending the county a
formal licensing question in parallel. Second, clear space on Google Drive by
deleting an old, one-terabyte (about a thousand gigabytes) folder of derived
imagery that can be regenerated later if ever needed; it turned out this folder had
actually already been deleted the day before, so the only step left is for Kam to
empty Google Drive's "trash," the one part only he can do, from a browser. Third,
get the 2016 photo at its true full sharpness — each dot on the ground genuinely one
foot across — rather than the artificially "zoomed-in" half-foot version the map
server shows by default, which has invented extra, blurrier detail. Fourth, treat
the three sharpest, largest years — 2020, 2022, and 2024, roughly 23 gigabytes each
— with extra care: run a small test first for each one, and check with Kam before
committing to the full download. These four rules now govern every download in the
campaign.

## 5. Glossary

*Technical terms used above, explained simply. This list grows as new terms appear.*

- **Band** — one layer of color information in a photo. An ordinary photo has three
  bands (red, green, blue); some of ours have a fourth, near-infrared. A
  black-and-white photo has just one band — brightness only, no color.
- **Bilinear ("blur-resample")** — a way of filling in a photo that blends
  neighboring pixels together, softening detail. The opposite of nearest-neighbor.
- **C-CAP** — a NOAA (the federal ocean and weather agency) reference map that
  classifies coastal land into categories like forest, grass, pavement, and water.
  We're getting it to independently check our own tree-detection results against,
  not to train the computer model on.
- **Catalogue** — the master list the project's software reads to know exactly
  which imagery file represents each year. Updating an entry is what makes a newly
  downloaded photo the one actually used going forward.
- **Checksum / fingerprint** — a short code calculated from a file's exact contents;
  if even one bit of the file changes, the fingerprint changes too, so it's used to
  prove a copy is exact.
- **Chunk / piece** — one of the roughly 230 postcard-sized pieces the map server
  hands out at a time; the pieces are stitched back together into one big picture.
- **Dot-for-dot / byte-for-byte check** — comparing two files value by value to
  confirm they're truly identical, not just similar-looking.
- **Header check** — confirming what's inside a file, or whether two files are
  identical, by reading just its starting information and a few small sample pieces
  over the internet — without downloading the whole thing. This caught a duplicate
  15.8 GB file for free.
- **Ledger** — a running receipt the new tool keeps of every piece it downloads: its
  size, its fingerprint, and how long it took. Lets an interrupted download resume,
  and lets us diagnose slow spots.
- **LZ77 compression** — a request to have the server shrink a file on its way to us
  without losing any quality (unlike JPEG, which throws detail away to save space).
  In our first real test, the server ignored this request.
- **NAIP** — the National Agriculture Imagery Program, a USDA (the federal
  agriculture department) effort that photographs the entire country from the air
  every year or two, mainly to monitor farmland. The photos are free to use and
  happen to cover Edmonds too.
- **NIR (near-infrared)** — a color of light just past red, invisible to human eyes
  but visible to cameras. Healthy leaves reflect it strongly, making it the single
  most useful clue for telling trees and plants apart from roads, roofs, and
  everything else in a photo.
- **Offline test** — a rehearsal where the new tool runs against a fake, scripted
  stand-in for the real map server, built to fail in specific ways, so we can prove
  the tool handles problems correctly before it ever touches the real thing.
- **Pilot** — a small trial download from the actual, real server (as opposed to an
  offline test), done over a small area before committing to a large, expensive
  download.
- **Pixel / pixel size ("resolution")** — a pixel is one dot in a digital photo;
  pixel size is how much real ground that one dot covers. Smaller pixel size means
  finer detail. "True 1-foot" means each dot genuinely represents one foot of
  ground, as measured by the camera — not a "zoomed-in" copy where a computer has
  invented extra, blurrier dots to look more detailed than it really is.
- **Pre-flight check** — an automated check the project runs before any expensive
  computing job, to catch problems early rather than waste time or money on a run
  that was doomed from the start.
- **Provenance** — the documented history of where a file actually came from and how
  it was produced. Better provenance means the project can trace a file back to its
  original source with more confidence.
- **Quarantine (folder)** — a folder set aside so that no part of the project's
  software will automatically read from it — used when a file's licensing terms
  aren't yet clear enough to trust it for use.
- **Staircase pattern** — a diagonal, step-shaped area with no photo data. In the
  2016 test, this traced the shoreline of Puget Sound — there's no land there to
  photograph.
- **Study rectangle** — the fixed rectangular boundary the project uses so every
  year's photo lines up on the same grid. Because Edmonds sits on Puget Sound, part
  of this rectangle is always open water with no usable photo data — which is why
  the project also checks coverage against the actual city boundary, not just the
  rectangle.
- **Superseded** — labeled as replaced by a newer, better file. A superseded file is
  never deleted, just kept on hand and clearly marked so it's not used by mistake.
- **Tile cache** — small, pre-cut pieces of a photo, saved ahead of time so the
  computer-training process doesn't have to re-cut them on every run. Whenever the
  source photo changes, the project automatically notices and rebuilds these
  pieces — a bit of one-time extra work done automatically, not a sign of a
  problem.
- **USGS** — the U.S. Geological Survey, the federal agency that conducted some of
  the original aerial photography this project is tracking down, including the 2002
  flight.
- **WAGDA** — the Washington GIS Data Archive, a University of Washington service
  that hosts original, uncompressed government survey imagery for public download.
  It turned out to be the source of the 2002 photo's true original tiles.
