"""Writes /content/SWEEP_ARMS from the ARMS constant below — edited per batch
by the launcher before exec (kept dumb and stdlib-only on purpose)."""
ARMS = "REPLACED_AT_LAUNCH"
with open("/content/SWEEP_ARMS", "w", encoding="utf-8") as f:
    f.write(ARMS)
print("SWEEP_ARMS written:", ARMS.count("\n") + 1, "arms")
