# Helix token-saving metrics

Tasks: 32 (4 repos x 7 families, ground truth by independent textual method cross-checked with AST). Reps: A n=1, L1 n=2, L2 n=3. Correctness: blind LLM judge. CI: 95% bootstrap over tasks.


## L1 vs A

| metric | A (sum over tasks) | L1 | savings | 95% CI | median per-task |
|---|---:|---:|---:|---|---:|
| fresh input | 206 | 207 | **-0.5%** | -16.5..14.4% | 0.0% |
| cache write | 917,410 | 48,858 | **94.7%** | 93.7..95.5% | 95.4% |
| cache read | 2,929,997 | 136,994 | **95.3%** | 94.1..96.5% | 96.0% |
| input+cache (all) | 3,847,613 | 186,059 | **95.2%** | 94.1..96.1% | 95.9% |
| output | 24,412 | 12,806 | **47.5%** | 30.8..59.7% | 45.6% |
| total tokens | 3,872,025 | 198,866 | **94.9%** | 93.7..95.9% | 95.6% |
| price-weighted units | 1,562,028 | 139,011 | **91.1%** | 89.1..92.8% | 92.7% |
| list cost USD | 4.50 | 0.35 | **92.2%** | 90.5..93.6% | 93.2% |
| frontier turns | 118 | 104 | **12.3%** | -3.1..26.3% | 0.0% |
| wall-clock s | 390 | 267 | **31.7%** | 18.2..43.6% | 36.1% |

Correctness: A 68.8% vs L1 75.0%. Correct answers per million tokens: 5.7 vs 120.7 (**21x**).

| family | tasks | in+cache savings | output savings | turns A->L1 | correct A/L1 |
|---|---:|---:|---:|---|---|
| callees | 4 | 96.7% | 61.1% | 3.8 -> 2.4 | 0% / 0% |
| callers | 8 | 96.8% | 63.6% | 3.6 -> 2.6 | 100% / 100% |
| coverage | 4 | 93.4% | 50.0% | 6.0 -> 5.2 | 0% / 25% |
| defparams | 4 | 95.8% | 31.5% | 2.0 -> 2.2 | 100% / 100% |
| docaudit | 4 | 95.5% | 38.6% | 2.8 -> 2.6 | 75% / 75% |
| importers | 4 | 94.1% | 48.3% | 3.0 -> 3.8 | 75% / 100% |
| testcount | 4 | 93.5% | 26.0% | 4.8 -> 4.4 | 100% / 100% |

| repo | tasks | in+cache savings | output savings | turns A->L1 | correct A/L1 |
|---|---:|---:|---:|---|---|
| click | 8 | 96.5% | 65.7% | 3.8 -> 2.6 | 62% / 75% |
| helixcontext | 8 | 93.7% | 31.6% | 3.8 -> 4.1 | 62% / 75% |
| helixengine | 8 | 93.8% | 27.4% | 3.6 -> 3.7 | 75% / 75% |
| requests | 8 | 96.6% | 59.3% | 3.6 -> 2.6 | 75% / 75% |

## L2 vs A

| metric | A (sum over tasks) | L2 | savings | 95% CI | median per-task |
|---|---:|---:|---:|---|---:|
| fresh input | 206 | 209 | **-1.6%** | -16.0..12.1% | 0.0% |
| cache write | 917,410 | 39,113 | **95.7%** | 95.1..96.4% | 96.4% |
| cache read | 2,929,997 | 164,681 | **94.4%** | 93.2..95.4% | 95.1% |
| input+cache (all) | 3,847,613 | 204,003 | **94.7%** | 93.7..95.7% | 95.3% |
| output | 24,412 | 13,359 | **45.3%** | 31.2..57.4% | 44.2% |
| total tokens | 3,872,025 | 217,361 | **94.4%** | 93.3..95.4% | 95.1% |
| price-weighted units | 1,562,028 | 132,362 | **91.5%** | 89.8..93.3% | 93.6% |
| list cost USD | 4.50 | 0.32 | **92.8%** | 91.4..94.2% | 94.5% |
| frontier turns | 118 | 105 | **11.3%** | -3.3..23.6% | 0.0% |
| wall-clock s | 390 | 298 | **23.7%** | 8.6..37.1% | 19.5% |

Correctness: A 68.8% vs L2 94.8%. Correct answers per million tokens: 5.7 vs 139.6 (**25x**).

| family | tasks | in+cache savings | output savings | turns A->L2 | correct A/L2 |
|---|---:|---:|---:|---|---|
| callees | 4 | 96.6% | 57.5% | 3.8 -> 2.4 | 0% / 92% |
| callers | 8 | 96.0% | 59.8% | 3.6 -> 2.8 | 100% / 100% |
| coverage | 4 | 91.8% | 36.7% | 6.0 -> 6.0 | 0% / 100% |
| defparams | 4 | 95.5% | 32.4% | 2.0 -> 2.2 | 100% / 100% |
| docaudit | 4 | 95.3% | 41.1% | 2.8 -> 2.6 | 75% / 67% |
| importers | 4 | 95.1% | 63.5% | 3.0 -> 3.0 | 75% / 100% |
| testcount | 4 | 93.2% | 31.1% | 4.8 -> 4.5 | 100% / 100% |

| repo | tasks | in+cache savings | output savings | turns A->L2 | correct A/L2 |
|---|---:|---:|---:|---|---|
| click | 8 | 95.5% | 59.3% | 3.8 -> 2.9 | 62% / 92% |
| helixcontext | 8 | 94.1% | 36.3% | 3.8 -> 3.5 | 62% / 100% |
| helixengine | 8 | 94.3% | 35.2% | 3.6 -> 3.4 | 75% / 100% |
| requests | 8 | 94.9% | 46.9% | 3.6 -> 3.2 | 75% / 88% |
