"""ADVERSARIAL TEST for the latent-class U2 result.

The observed fit says latent prevalence pi ~ .29 (near C-CAP) and the NDVI
reference has specificity ~.87 (it "over-calls").  The competing account:
the model and C-CAP are the correlated pair (both stand-shaped, both strict),
they out-vote the NDVI reference, and the truth is really pi ~ .378.

So: BUILD THAT WORLD and see how much model<->C-CAP dependence it takes to
reproduce what we actually observed.  If it needs implausibly strong
dependence, the observed reading survives the adversarial account.
"""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, r"G:\My Drive\treedata\.claude\worktrees\latent-class-u2\Scripts")
from phase4_qc_latent_class import fit_lca

# The world where the NDVI reference is RIGHT.
PI_TRUE = 0.378
SE = [0.70, 0.97, 0.55]      # ccap, ndvi, model
SP = [0.95, 0.97, 0.98]

# what we must reproduce to sustain the adversarial account
TARGET_PI = 0.291
TARGET_NDVI_SP = 0.873
TARGET_CALLS = [0.295, 0.378, 0.224]


def simulate(pi, se, sp, n=3_000_000, seed=0, rho=0.0, pair=(0, 2)):
    """pair = indices of the two sources made conditionally DEPENDENT:
    with probability rho, source pair[1] copies source pair[0]'s call."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < pi
    Y = np.zeros((n, 3), dtype=np.uint8)
    for j in range(3):
        Y[:, j] = rng.random(n) < np.where(z, se[j], 1 - sp[j])
    if rho > 0:
        copy = rng.random(n) < rho
        Y[copy, pair[1]] = Y[copy, pair[0]]
    pat = (Y[:, 0].astype(np.int64) << 2) | (Y[:, 1] << 1) | Y[:, 2]
    return np.bincount(pat, minlength=8).astype(float), Y.mean(axis=0)


print("WORLD: the NDVI reference is correct.  pi_true = %.3f" % PI_TRUE)
print("Question: what model<->C-CAP dependence reproduces our observed fit?\n")
print(f"{'rho':>5} {'est pi':>8} {'ndvi sp':>9} {'ccap se':>8} {'model se':>9}"
      f"   {'calls c/n/m':>22}")

for rho in (0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9):
    c, calls = simulate(PI_TRUE, SE, SP, seed=11, rho=rho, pair=(0, 2))
    f = fit_lca(c, seed=3)
    print(f"{rho:>5.1f} {f['pi']:>8.4f} {f['sp'][1]:>9.4f} {f['se'][0]:>8.4f} "
          f"{f['se'][2]:>9.4f}   {calls[0]:.3f}/{calls[1]:.3f}/{calls[2]:.3f}")

print(f"\nOBSERVED (2016 baseline): pi {TARGET_PI:.4f}  ndvi sp {TARGET_NDVI_SP:.4f}"
      f"   calls {TARGET_CALLS[0]}/{TARGET_CALLS[1]}/{TARGET_CALLS[2]}")
print("\nRead: the row whose pi and ndvi-sp BOTH match the observed line is the")
print("dependence strength the adversarial account requires.  Note also whether")
print("that row's simulated CALL RATES still match what the sources really say —")
print("if the dependence needed to move pi also breaks the call rates, the")
print("adversarial world cannot reproduce our data at any rho.")

# ---- FAIRER VERSION: hold the observed CALL RATES fixed at every rho ----
# Raising rho inflates the model's call rate, so the adversarial account must
# lower the model's TRUE sensitivity to compensate. Solve for that se_m.
print("\n\nFAIR ADVERSARIAL TEST - model call rate pinned to the observed 0.224")
print(f"{'rho':>5} {'req se_m':>9} {'est pi':>8} {'ndvi sp':>9}   verdict")
for rho in (0.0, 0.1, 0.2, 0.3, 0.5, 0.7):
    need = (0.224 - rho * 0.296) / (1 - rho)
    se_m = (need - (1 - PI_TRUE) * (1 - SP[2])) / PI_TRUE
    if not (0 < se_m < 1):
        print(f"{rho:>5.1f} {se_m:>9.3f}        --        --   IMPOSSIBLE (se out of [0,1])")
        continue
    c, calls = simulate(PI_TRUE, [SE[0], SE[1], se_m], SP, seed=11, rho=rho, pair=(0, 2))
    f = fit_lca(c, seed=3)
    hit = abs(f['pi'] - TARGET_PI) < 0.01 and abs(f['sp'][1] - TARGET_NDVI_SP) < 0.02
    print(f"{rho:>5.1f} {se_m:>9.3f} {f['pi']:>8.4f} {f['sp'][1]:>9.4f}   "
          f"{'REPRODUCES OBSERVED' if hit else 'no'}   (model calls {calls[2]:.3f})")
print("\nA required se_m far below the model's observed behaviour means the")
print("adversarial world only reproduces our numbers by making the model a")
print("far worse detector than every other instrument says it is.")
