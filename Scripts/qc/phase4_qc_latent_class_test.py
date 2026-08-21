"""Synthetic recovery test for fit_lca: known truth -> can EM find it?

Also tests the two failure modes that decide whether the estimator is usable:
  * label switching (the mirror solution)
  * conditionally DEPENDENT sources (what happens when the assumption breaks)
"""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase4_qc_latent_class import fit_lca, PATTERN


def simulate(pi, se, sp, n=4_000_000, seed=0, rho=0.0):
    """Generate pattern counts. rho>0 correlates sources 1 (ndvi) and 2 (model)
    by making the model copy the ndvi call with probability rho."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < pi
    Y = np.zeros((n, 3), dtype=np.uint8)
    for j in range(3):
        p = np.where(z, se[j], 1 - sp[j])
        Y[:, j] = rng.random(n) < p
    if rho > 0:
        copy = rng.random(n) < rho
        Y[copy, 2] = Y[copy, 1]
    pat = (Y[:, 0].astype(np.int64) << 2) | (Y[:, 1] << 1) | Y[:, 2]
    return np.bincount(pat, minlength=8).astype(float)


def show(tag, truth, f):
    pi_t, se_t, sp_t = truth
    print(f"\n{tag}")
    print(f"  pi   truth {pi_t:.3f}   est {f['pi']:.4f}   err {f['pi']-pi_t:+.4f}")
    for j in range(3):
        print(f"  src{j} se {se_t[j]:.3f}->{f['se'][j]:.4f} ({f['se'][j]-se_t[j]:+.4f})"
              f"   sp {sp_t[j]:.3f}->{f['sp'][j]:.4f} ({f['sp'][j]-sp_t[j]:+.4f})")
    print(f"  flags boundary={f['boundary']} weak={f['weak']}")


# 1. clean recovery, parameters in our plausible range
pi, se, sp = 0.35, [0.75, 0.88, 0.70], [0.92, 0.85, 0.97]
c = simulate(pi, se, sp, seed=1)
f = fit_lca(c, seed=7)
show("TEST 1 — conditionally independent, should recover truth", (pi, se, sp), f)
ok1 = abs(f["pi"] - pi) < 0.01 and max(abs(f["se"][j] - se[j]) for j in range(3)) < 0.02

# 2. label-switch robustness: same data, many different seeds must agree
ests = [fit_lca(c, seed=s)["pi"] for s in range(12)]
ok2 = (max(ests) - min(ests)) < 1e-3
print(f"\nTEST 2 — label switching: pi across 12 seeds spread "
      f"{max(ests)-min(ests):.2e} -> {'STABLE' if ok2 else 'UNSTABLE'}")

# 3. just-identified claim: does the fit reproduce the table exactly?
pi_, se_, sp_ = f["pi"], f["se"], f["sp"]
l1 = pi_ * np.prod(se_ ** PATTERN * (1 - se_) ** (1 - PATTERN), axis=1)
l0 = (1 - pi_) * np.prod((1 - sp_) ** PATTERN * sp_ ** (1 - PATTERN), axis=1)
pred = (l1 + l0) * c.sum()
rel = np.abs(pred - c).max() / c.sum()
ok3 = rel < 1e-4
print(f"TEST 3 — just-identified: max cell rel. error {rel:.2e} -> "
      f"{'EXACT (as documented)' if ok3 else 'NOT exact'}")

# 4. the honest failure: correlated sources 1&2 (ndvi + model)
for rho in (0.3, 0.6):
    cd = simulate(pi, se, sp, seed=2, rho=rho)
    fd = fit_lca(cd, seed=7)
    show(f"TEST 4 — sources 1&2 correlated rho={rho} (assumption VIOLATED)",
         (pi, se, sp), fd)
    print(f"  -> src0 (ccap) sp bias {fd['sp'][0]-sp[0]:+.4f}, "
          f"se bias {fd['se'][0]-se[0]:+.4f}")

print(f"\nSUMMARY recover={ok1} stable={ok2} exact={ok3}")
