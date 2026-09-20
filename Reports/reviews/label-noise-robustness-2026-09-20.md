<!-- litkb-review workstream=01a0be9c-899a-7852-b3de-cff7a9812596 -->

# Label noise, legacy labels, and supervising other years from one hand-labelled year

## Scope

This review answers one question: how robust is CNN semantic segmentation of aerial imagery to noisy or legacy training labels, and what does that imply for supervising other years with labels projected from one hand-labelled year. It is the operational proving run of the litkb review path, written unattended.

Its only source is the brief of workstream 01a0be9c-899a-7852-b3de-cff7a9812596. Four expectations were dropped off as hunt requests before any full text was read, so that the priors could be graded against the text rather than adjusted to it. Twelve uses were then recorded against four works, each carrying a quote the database located and verified in the extracted block; every citation below names one of those verified spans, and nothing here rests on an abstract, a memory, or a search result.

Two limits on what was read. First, retrieval was lexical only — the vector leg of the search is off in this deployment — so a passage that shares no words with the queries used could not surface, and absence of a finding here is not absence in the corpus. Second, roughly half the stored blocks encode their line breaks in a form this session could not transmit through the recording tool, so every span recorded and quoted below lies within a single line of its block. Several therefore begin or end mid-sentence. They are byte-exact and they are the spans the database verified, but they are narrower than the sentences they come from, and a reader who wants the full sentence should open the block.

Nothing in this review was measured on Edmonds imagery. The implications drawn for projected labels are the papers' claims placed next to our situation, not results from our archive.

## How far the robustness claim reaches

The motivation for training on imperfect labels is stated as the alternative to hand annotation, namely to "train the classifier from existing legacy data or crowd-sourced" [Kaiser_2017_learning-aerial-image-segmentation p.1 #01a0abc8-d741-73e6-834b-3bf2bf3943ab] maps.

The paper's own summing-up of how far that goes is that pre-training with "large-scale OSM labels can replace the vast majority of manual" [Kaiser_2017_learning-aerial-image-segmentation p.13 #01a0abc8-d83a-749a-87a5-1917eebe40fa] labels.

The same tolerance appears in a different task and a different failure mode, where a model trained on misaligned polygons still learned to align them by leaning on the tendency of neural "networks to be robust to a certain amount of noise and does" [Girard_2019_noisy-supervision-correcting-misaligned p.1 #01a0abcc-65d9-797b-bf46-9d81da34b9ef] not require a special loss.

## Where the noise stops being free

Measured against a small manual baseline, training on noisy labels alone did come out ahead: "This set up achieves an F1-score of 0.779, beating baseline" [Kaiser_2017_learning-aerial-image-segmentation p.9 #01a0abc8-d7f3-7886-9b1c-de0274f44335] Ia by 1.5 percent points. Against an equal volume of pixel-accurate labels the comparison reverses, because with equally large "quantities of pixel-accurate labels, performance drops by 10" [Kaiser_2017_learning-aerial-image-segmentation p.9 #01a0abc8-d7f3-7886-9b1c-de0274f44335] percent points.

The conclusion states the same trade plainly: segmentation can be learned from map labels without manual labelling "effort albeit at the cost of reduced segmentation accuracy." [Kaiser_2017_learning-aerial-image-segmentation p.13 #01a0abc8-d83a-749a-87a5-1917eebe40fa]

Not all of the disagreement between two label sources is random error, and the part that is definitional does not average out, because one source is described this way: "it labels overhanging tree canopies that occlude parts of the impervious ground (including streets) as tree, whereas streets in" [Kaiser_2017_learning-aerial-image-segmentation p.6 #01a0abc8-d7b2-73df-8180-ca7f520a4b37] the OSM labels include pixels under trees.

## What an accepted canopy product measured

After automated mapping and manual editing, "Per-pixel assessment of the final, edited map indicated an overall accuracy of 96%" [MacFaden_2012_high-resolution-tree-canopy p.18 #01a0abc9-8062-77f9-bd0a-95e0130c0076] for the seven-class land-cover map.

Most of that was reached before any editing, since the automated "approach created a draft Tree Canopy class whose accuracy exceeded 90%." [MacFaden_2012_high-resolution-tree-canopy p.21 #01a0abc9-8093-708e-83f9-d91948970017]

## Season and illumination across dates

Canopy mapping that rested on imagery alone was judged to have been "limited if based exclusively on a mix of leaf-on and leaf-off multispectral orthoimagery." [MacFaden_2012_high-resolution-tree-canopy p.21 #01a0abc9-8093-708e-83f9-d91948970017]

The change-detection literature states the same difficulty as a property of the signal, that due to seasonal changes "or altered illumination, the observed gray levels may be significantly different even in the corresponding unchanged territories." [Benedek_2015_multilayer-markov-random-field p.12 #01a0abc6-ecbc-73e1-b932-ccfffffba295]

What that paper offers against the problem is narrower and more hedged than the drop-off assumed, being a claim about one feature of one of the three compared models, the intensity co-occurrence "statistics (ICS) feature of CXM may correctly classify large homogeneous regions, even if the observed pixel value changes are high." [Benedek_2015_multilayer-markov-random-field p.12 #01a0abc6-ecbc-73e1-b932-ccfffffba295]

## Expectations not supported

Four expectations were dropped off before reading. Two came back confirmed and are carried by the cited sentences above; two did not, and are entered here.

- **CONTRADICTED — hunt_request 01a0be9c-ddd2-7d83-8e2c-feb6eae0853d** (ref 10.1109/tgrs.2017.2719738). Expected claim, as dropped off: "Kaiser et al. report that a model trained only on OpenStreetMap-derived labels OUTPERFORMS a model trained on manually labelled, pixel-accurate ground truth of the same city." The verified quotes say the opposite at equal data volume. The page 9 span records a drop of ten percentage points against the baseline trained on equally large quantities of pixel-accurate labels, and the page 13 span records reduced segmentation accuracy as the cost of removing manual labelling altogether. Both are set out in the section headed *Where the noise stops being free*, which also carries the one result the expectation over-generalised from: the noisy-label model did beat a baseline built on a small manual set. The distinction the expectation lost is between beating a little hand labelling and beating a lot of it.
- **UNCONFIRMED — hunt_request 01a0be9c-febe-7cf5-85fa-a643d441e9b6** (ref 10.1016/j.isprsjprs.2015.02.006). Expected claim, as dropped off: "Multilayer Markov random field change detection between aerial images of different dates handles differing illumination and sensor conditions between the two dates." Nothing ingested has confirmed or refuted it. The work is linked and extracted, and it was searched for this; what was found is entered in the section headed *Season and illumination across dates*, recorded as context rather than support, because the text states the difficulty for pixel differencing and then makes a hedged claim about one feature of one model, and says nothing about differing sensors. The sensor half of the expectation was not addressed at all. A related 2009 work by the same first author does speak to image pairs taken in different seasonal conditions, but a use recorded against that work cannot resolve this request, which is bound to the 2015 paper.

The two that came back confirmed, entered here for completeness only: hunt_request 01a0be9c-cb64-7f6f-9d13-33a8739c2261 (robustness to label noise and replacement of manual effort) and hunt_request 01a0be9c-ee42-7933-a124-c597a97e946f (canopy accuracy above 90%). The second was confirmed on its accuracy half only; the drop-off also asserted that the product is used as a reference product, and no verified quote in this workstream speaks to that, so no sentence above asserts it.

## Sources

| work | key | pages cited |
|---|---|---|
| Kaiser and colleagues (2017) | `Kaiser_2017_learning-aerial-image-segmentation` | 1, 6, 9, 13 |
| MacFaden and colleagues (2012) | `MacFaden_2012_high-resolution-tree-canopy` | 18, 21 |
| Benedek and colleagues (2015) | `Benedek_2015_multilayer-markov-random-field` | 12 |
| Girard and colleagues (2019) | `Girard_2019_noisy-supervision-correcting-misaligned` | 1 |
