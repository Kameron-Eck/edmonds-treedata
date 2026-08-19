"""Q134/Q130: CAN normalisation rescue GRVI in the early years, or is the information gone?

The elegant test: AUC is INVARIANT UNDER ANY MONOTONE TRANSFORM. Affine gain/offset (IR-MAD),
gamma, histogram matching and quantile mapping are all monotone. So:

  high AUC, wrong threshold -> a CALIBRATION problem. Normalisation WILL fix it.
  AUC near 0.5              -> the INFORMATION IS GONE. No monotone correction can help,
                               and IR-MAD (ID 204) would be wasted effort.

This decides Q130 and Q134 together without implementing any normalisation at all.

Confound stated up front: C-CAP is 2016 vintage, so for 2000 some genuine canopy change is
scored as error. That depresses the early years somewhat. It cannot manufacture a difference
between 0.9 and 0.5, which is the scale the question turns on.
"""
import numpy as np, rasterio
from sampler import sample

CCAP = r'D:\edmonds-pipeline\Imagery\ccap_2016_edmonds.tif'
CANOPY = [9, 10, 11, 13, 16]

d = np.load('pts.npz', allow_pickle=True); X, Y = d['X'], d['Y']
crs = rasterio.open(CCAP).crs
cc, _ = sample(CCAP, X, Y, crs)
z = np.load('rg_cache.npz', allow_pickle=True)
print(f'{X.size:,} points; cached acquisitions: {len(z.files)}\n')

def auc(score, pos):
    """Rank-based AUC. Invariant to any monotone transform of `score`."""
    ok = np.isfinite(score)
    s, p = score[ok], pos[ok]
    r = np.argsort(np.argsort(s)) + 1.0
    n1 = float(p.sum()); n0 = float((~p).sum())
    if n1 < 10 or n0 < 10: return np.nan
    return (r[p].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)

print(f"{'acquisition':<22}{'AUC GRVI':>10}{'AUC green':>11}{'AUC bright':>12}"
      f"{'canopy GRVI':>13}{'other GRVI':>12}{'separation':>12}")
res = {}
for fn in z.files:
    v = z[fn]; R, G = v[:, 0].astype(np.float32), v[:, 1].astype(np.float32)
    ok = (R + G) > 0
    ccv = cc[:len(R)]
    pos = np.isin(ccv, CANOPY) & ok
    neg = (ccv != 0) & ~np.isin(ccv, CANOPY) & ok
    keep = pos | neg
    gr = np.where(ok, (G - R) / np.maximum(G + R, 1e-6), np.nan)
    a_gr = auc(np.where(keep, gr, np.nan), pos)
    a_g  = auc(np.where(keep, G, np.nan), pos)
    a_br = auc(np.where(keep, -(R + G), np.nan), pos)   # darker = canopy
    mu_p, mu_n = float(np.nanmean(gr[pos])), float(np.nanmean(gr[neg]))
    sd = float(np.nanstd(gr[keep]))
    res[fn] = a_gr
    print(f'{fn[:21]:<22}{a_gr:>10.4f}{a_g:>11.4f}{a_br:>12.4f}'
          f'{mu_p:>+13.4f}{mu_n:>+12.4f}{(mu_p-mu_n)/max(sd,1e-9):>12.3f}')

print('\nREAD: AUC is invariant to affine, gamma, histogram matching - every monotone correction.')
print('AUC ~0.5 in a year means GRVI carries NO canopy information there and IR-MAD cannot help.')
print('AUC high but a shifted mean means it is purely a CALIBRATION problem, which IS fixable.')
print('"separation" is the canopy-vs-other GRVI gap in standard deviations - a scale-free effect size.')
