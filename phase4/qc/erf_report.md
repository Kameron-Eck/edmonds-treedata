# Effective receptive field — the deployed model

Model: `resnet101` U-Net, decoder(1024, 512, 256, 128, 64), in_channels=3, tile 512x512.
Checkpoint: `sem_best_2020.pt`
Input: 16 real tiles from 2009__rgb3_nodeb

Method: |d(centre output pixel) / d(input)| accumulated and normalised (RepLKNet's measurement).

## How much of the tile actually influences one prediction

| share of influence | pixels | % of tile area | equivalent square side |
|---|---|---|---|
| 20% | 2,285 | **0.87%** | 48 px |
| 50% | 11,170 | **4.26%** | 106 px |
| 90% | 61,702 | **23.54%** | 248 px |
| 99% | 125,698 | **47.95%** | 355 px |

## Centred-box view

| share | smallest centred square holding it |
|---|---|
| 50% | 117 px |
| 90% | 283 px |
| 99% | 391 px |

## Verdict

- 50% of the influence sits in ~4.3% of the tile area (~106 px square of 512). Reach is **well short** of the tile.
- This is ParseNet's VOC regime, where adding an image-level global branch was worth **+2.57 mIoU**. Global context is genuinely missing.
- The cheap form is a global-average-pool branch, NOT large-rate atrous taps: at output stride 32 the bottleneck is 16x16, and DeepLabv3 states rates approaching feature-map size "degenerate to a simple 1x1 filter".

## What that reach means on the ground

The same ERF in pixels is a different context window in metres at each tier.

| GSD | 50% influence within |
|---|---|
| 5.0 cm | 5.3 m |
| 10.0 cm | 10.6 m |
| 30.5 cm | 32.2 m |
| 60.0 cm | 63.4 m |
| 100.0 cm | 105.7 m |

**Do not read this table as settling the question.** Loos et al. 2024 varied theoretical RF at constant parameter count and found the required receptive field tracks OBJECT SIZE IN PIXELS, not metric context — under which a 6 px crown at 100 cm is already well covered and the deficit would sit at the FINE end instead. This measures reach; it does not prove reach is the binding constraint.
