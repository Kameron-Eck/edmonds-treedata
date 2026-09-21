<!-- litkb-review workstream=01a0bf4b-6844-7507-963c-9fdb66c58c68 -->

# Label noise, projected labels, and CNN segmentation of aerial imagery

## Scope

The question put to the knowledge base was how robust CNN semantic segmentation of aerial imagery is to noisy or legacy training labels, and what that implies for supervising other years with labels projected from one hand-labelled year. Only the first half of that question is answered below. The second half is an inference about this project's own pipeline, and no quote in this workstream's brief states it, so this review does not draw it: what follows is the record of what the ingested texts say, and the step from there to a decision about projecting 2020 labels onto other years is left to whoever makes that decision.

Four expectations were dropped off before any full text was read, and each was then resolved against the full text through search. A fifth work, on misaligned annotations, was reached through search on the same topic and is cited here on the same terms. Everything cited comes from this workstream's brief; nothing was read from an abstract, from memory, or from outside the knowledge base.

The review is narrow in three ways worth stating. It rests on a single study's comparison of noisy against accurate labels, so the magnitudes it reports are that one study's, under that study's training-set sizes, and are not general constants. It reads nothing on the specific operation this project performs, which is projecting labels forward and backward in time across an imagery archive. And it makes no assessment of canopy segmentation accuracy for any year of the Edmonds archive, because no such measurement is in the knowledge base.

## What the record shows about tolerance to label noise

An observation already standing in the field is recorded by Kaiser and colleagues: "On the other hand, it has
been observed that they are rather robust against noise in
the training labels." [Kaiser_2017_learning-aerial-image-segmentation p.1 #01a0abc8-d741-73e6-834b-3bf2bf3943ab].

The study reports that less manual annotation effort is needed when noisy large-scale data is exploited: "We report our results
that indicate that satisfying performance can be obtained with
significantly less manual annotation effort, by exploiting noisy
large-scale training data." [Kaiser_2017_learning-aerial-image-segmentation p.1 #01a0abc8-d741-73e6-834b-3bf2bf3943ab].

That finding is qualified by the size of the training set: "We find in this study that training on noisy labels does
work well, but only with substantially larger training sets." [Kaiser_2017_learning-aerial-image-segmentation p.2 #01a0abc8-d74d-72b2-a931-9f7761645ce5].

Pre-training on the noisy labels can replace most of the manual ones: "Indeed, pre-training with
large-scale OSM labels can replace the vast majority of manual
labels." [Kaiser_2017_learning-aerial-image-segmentation p.13 #01a0abc8-d83a-749a-87a5-1917eebe40fa].

Because of this, Measured against a baseline trained from scratch on the same high-accuracy labels, the reported gain is 7 percent points, to 0.837: "Performance
increases by 7 percent points to 0.837 over baseline Ia, where
the model is trained from scratch on the same high-accuracy
labels." [Kaiser_2017_learning-aerial-image-segmentation p.10 #01a0abc8-d7fc-7fe4-a723-d1bd2a186912].

## Where the noisy labels fell short of pixel-accurate labels

At small training-set size, training on noisy labels does not reach the performance of hand-labelled, pixel-accurate data: "Whereas with small training sets (≈ 2 km2
) it does not reach
the performance of hand-labelled, pixel-accurate training data." [Kaiser_2017_learning-aerial-image-segmentation p.2 #01a0abc8-d74d-72b2-a931-9f7761645ce5].

Against a baseline trained on equally large quantities of pixel-accurate labels, the drop is stated as 10 percent points: "Compared to baseline II, i.e. training with equally large
quantities of pixel-accurate labels, performance drops by 10
percent points." [Kaiser_2017_learning-aerial-image-segmentation p.9 #01a0abc8-d7f3-7886-9b1c-de0274f44335].

The authors state the cost alongside the saving: "Semantic segmentation of overhead images can indeed
be learned from OSM maps without any manual labeling
effort albeit at the cost of reduced segmentation accuracy." [Kaiser_2017_learning-aerial-image-segmentation p.13 #01a0abc8-d83a-749a-87a5-1917eebe40fa].

## Misalignment as a source of label noise

Girard and colleagues describe misaligned annotation polygons as producing noisy supervision: "We study the multi-modal cadaster map
alignment problem for which available annotations are misaligned polygons, resulting in noisy supervision." [Girard_2019_noisy-supervision-correcting-misaligned p.1 #01a0abcc-65d4-796c-846f-f351d1e52756].

They report that iteratively training a better alignment model to correct the annotations reduces the noise of the dataset: "We show that it is possible to
reduce the noise of the dataset by iteratively training a better
alignment model to correct the annotation alignment." [Girard_2019_noisy-supervision-correcting-misaligned p.1 #01a0abcc-65d4-796c-846f-f351d1e52756].

## Canopy reference products and imagery that spans dates

MacFaden and colleagues report the accuracy of the draft canopy class their automated approach produced: "This automated
approach created a draft Tree Canopy class whose accuracy exceeded 90%." [MacFaden_2012_high-resolution-tree-canopy p.21 #01a0abc9-8093-708e-83f9-d91948970017].

They report that canopy mapping based only on a mix of leaf-on and leaf-off multispectral orthoimagery would have been limited, and impossible in shadowed areas without lidar: "Indeed, tree-canopy mapping in shadowed areas would have been impossible without LIDAR, and effective canopy mapping in other parts of the city would have been
limited if based exclusively on a mix of leaf-on and leaf-off multispectral orthoimagery." [MacFaden_2012_high-resolution-tree-canopy p.21 #01a0abc9-8093-708e-83f9-d91948970017].

Benedek and colleagues state what must be expected of two image samples separated by a large time lag: "Even for a given specific problem the data comparison may be
notably challenging, considering that due to the large time lag
between two consecutive image samples, one must expect seasonal changes, differences in the obtained data quality and resolution, 3D geometric distortion effects, various viewpoints,
different illumination, or results of irrelevant human intervention
(such as crop rotation in the arboreous lands)." [Benedek_2015_multilayer-markov-random-field p.1 #01a0abc6-ebfc-7e73-b59a-86e476ee3035].

## Expectations not supported

Two of the four expectations dropped off at the start of this run did not come back confirmed.

- hunt_request 01a0bf4b-c37e-74d8-94f9-c701defc8208 (ref 10.1109/tgrs.2017.2719738) expected: *Kaiser et al. report that a model trained only on OpenStreetMap-derived labels OUTPERFORMS a model trained on manually labelled, pixel-accurate ground truth of the same city.* It came back CONTRADICTED. Two verified quotes were recorded against this request with the stance refutes, and both sit in the claim section *Where the noisy labels fell short of pixel-accurate labels*, which is where to read what the text actually says.

- hunt_request 01a0bf4b-e21d-703b-9148-3f7ee95b6581 (ref 10.1016/j.isprsjprs.2015.02.006) expected: *Multilayer Markov random field change detection between aerial images of different dates handles differing illumination and sensor conditions between the two dates.* It came back UNCONFIRMED: nothing ingested has confirmed or refuted it. The full text was searched repeatedly for this claim and no passage found was judged to state it, so no use was recorded against this request. One passage from the same work is cited in the claim section *Canopy reference products and imagery that spans dates*, but it was recorded without a link to this request and does not resolve it.

Two further notes on the ledger, neither of them a required entry.

- hunt_request 01a0bf4b-b3e7-768a-b234-59398c7b9c11 (ref 10.1109/tgrs.2017.2719738) came back CONFIRMED, and its quotes carry their claims in the body.

- hunt_request 01a0bf4b-d1f1-717d-84ec-462647387690 (ref 10.1117/1.jrs.6.063567) came back CONFIRMED, but the state is coarser than the drop-off was. Its expected claim is a conjunction of two parts: that the mapping achieves canopy accuracy above 90 percent, and that it is used as a reference product. A use was recorded for the first part only. No use in this workstream was recorded for the second part, nothing in the body asserts it, and the CONFIRMED state should not be read as covering it.

## Sources

| work | key | pages cited |
|---|---|---|
| Kaiser, Wegner, Lucchi, Jaggi, Hofmann and Schindler (2017), Learning aerial image segmentation from online maps | `Kaiser_2017_learning-aerial-image-segmentation` | 1, 2, 9, 10, 13 |
| MacFaden, O'Neil-Dunne, Royar, Lu and Rundle (2012), High-resolution tree canopy mapping for New York City using LIDAR and object-based image analysis | `MacFaden_2012_high-resolution-tree-canopy` | 21 |
| Benedek, Shadaydeh, Kato, Sziranyi and Zerubia (2015), Multilayer Markov Random Field models for change detection in optical remote sensing images | `Benedek_2015_multilayer-markov-random-field` | 1 |
| Girard, Charpiat and Tarabalka (2019), Noisy Supervision for Correcting Misaligned Cadaster Maps Without Perfect Ground Truth Data | `Girard_2019_noisy-supervision-correcting-misaligned` | 1 |
