# Helix token-saving metrics

Tasks: 28 (4 repos x 7 families, ground truth by independent textual method cross-checked with AST). Reps: A n=1, L1 n=2, L2 n=3. Correctness: blind LLM judge. CI: 95% bootstrap over tasks.


## L1 vs A

| metric | A (sum over tasks) | L1 | savings | 95% CI | median per-task |
|---|---:|---:|---:|---|---:|
| fresh input | 186 | 169 | **9.1%** | -3.7..20.0% | 0.0% |
| cache write | 788,695 | 39,513 | **95.0%** | 94.1..95.8% | 95.8% |
| cache read | 2,657,787 | 100,917 | **96.2%** | 95.5..96.8% | 95.9% |
| input+cache (all) | 3,446,668 | 140,599 | **95.9%** | 95.4..96.5% | 96.1% |
| output | 20,996 | 10,048 | **52.1%** | 41.8..60.2% | 50.3% |
| total tokens | 3,467,664 | 150,647 | **95.7%** | 95.0..96.3% | 95.9% |
| price-weighted units | 1,356,813 | 109,892 | **91.9%** | 90.7..93.1% | 92.8% |
| list cost USD | 3.90 | 0.27 | **93.1%** | 92.2..94.1% | 93.6% |
| frontier turns | 106 | 86 | **18.9%** | 4.5..31.4% | 8.3% |
| wall-clock s | 370 | 232 | **37.4%** | 28.5..45.4% | 35.1% |

Correctness: A 92.9% vs L1 83.9%. Correct answers per million tokens: 7.5 vs 156.0 (**21x**).

| family | tasks | in+cache savings | output savings | turns A->L1 | correct A/L1 |
|---|---:|---:|---:|---|---|
| callees | 4 | 97.3% | 68.4% | 4.2 -> 2.5 | 75% / 25% |
| callers | 7 | 96.0% | 47.3% | 3.3 -> 3.1 | 100% / 100% |
| coverage | 4 | 95.3% | 57.0% | 6.2 -> 4.2 | 100% / 62% |
| defparams | 4 | 96.2% | 52.3% | 2.5 -> 2.2 | 100% / 100% |
| docaudit | 2 | 94.8% | 43.9% | 2.0 -> 2.5 | 100% / 100% |
| importers | 3 | 95.9% | 43.8% | 3.0 -> 2.8 | 100% / 100% |
| testcount | 4 | 95.5% | 38.0% | 4.5 -> 3.8 | 75% / 100% |

| repo | tasks | in+cache savings | output savings | turns A->L1 | correct A/L1 |
|---|---:|---:|---:|---|---|
| click | 7 | 95.8% | 49.1% | 3.6 -> 3.0 | 100% / 86% |
| helixcontext | 7 | 96.2% | 57.6% | 3.9 -> 3.1 | 86% / 79% |
| helixengine | 7 | 95.3% | 46.0% | 3.7 -> 3.2 | 86% / 100% |
| requests | 7 | 96.3% | 55.9% | 4.0 -> 3.0 | 100% / 71% |

## L2 vs A

| metric | A (sum over tasks) | L2 | savings | 95% CI | median per-task |
|---|---:|---:|---:|---|---:|
| fresh input | 186 | 182 | **2.2%** | -13.4..14.2% | 0.0% |
| cache write | 788,695 | 33,630 | **95.7%** | 95.0..96.5% | 96.6% |
| cache read | 2,657,787 | 143,174 | **94.6%** | 93.3..95.7% | 95.2% |
| input+cache (all) | 3,446,668 | 176,987 | **94.9%** | 93.8..95.8% | 95.6% |
| output | 20,996 | 12,428 | **40.8%** | 26.8..52.2% | 47.5% |
| total tokens | 3,467,664 | 189,415 | **94.5%** | 93.3..95.5% | 95.4% |
| price-weighted units | 1,356,813 | 118,677 | **91.3%** | 89.3..93.2% | 93.5% |
| list cost USD | 3.90 | 0.29 | **92.6%** | 90.8..94.2% | 94.6% |
| frontier turns | 106 | 91 | **14.2%** | 0.4..25.9% | 19.5% |
| wall-clock s | 370 | 252 | **31.9%** | 19.5..42.6% | 32.6% |

Correctness: A 92.9% vs L2 95.2%. Correct answers per million tokens: 7.5 vs 140.8 (**19x**).

| family | tasks | in+cache savings | output savings | turns A->L2 | correct A/L2 |
|---|---:|---:|---:|---|---|
| callees | 4 | 96.8% | 66.9% | 4.2 -> 2.5 | 75% / 83% |
| callers | 7 | 96.2% | 55.5% | 3.3 -> 2.7 | 100% / 100% |
| coverage | 4 | 92.2% | 32.5% | 6.2 -> 5.5 | 100% / 83% |
| defparams | 4 | 95.6% | 50.2% | 2.5 -> 2.3 | 100% / 100% |
| docaudit | 2 | 94.1% | 41.7% | 2.0 -> 2.5 | 100% / 100% |
| importers | 3 | 94.9% | 42.0% | 3.0 -> 3.1 | 100% / 100% |
| testcount | 4 | 94.4% | 19.4% | 4.5 -> 4.1 | 75% / 100% |

| repo | tasks | in+cache savings | output savings | turns A->L2 | correct A/L2 |
|---|---:|---:|---:|---|---|
| click | 7 | 94.9% | 41.9% | 3.6 -> 3.3 | 100% / 90% |
| helixcontext | 7 | 93.9% | 29.8% | 3.9 -> 3.6 | 86% / 100% |
| helixengine | 7 | 95.2% | 47.5% | 3.7 -> 3.0 | 86% / 100% |
| requests | 7 | 95.4% | 43.4% | 4.0 -> 3.0 | 100% / 90% |
