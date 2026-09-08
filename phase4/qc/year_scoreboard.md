# YEAR SCOREBOARD — best arm per year at `matched_p75` — GENERATED

Regenerate: `py -3.12 qc/year_scoreboard.py --policy matched_p75`.

Every ranking here is made at ONE held operating point. At per-arm best-F1
cuts every arm is best at something, which is how one 2017 flight delivered
three ways came to look 10.09 pp apart when matched cuts put it at 1.07.

Arms are grouped by (reference, evaluation scope) and ranked only WITHIN a
group: different populations are not comparable, and `population` is printed
so a coverage gap can never be read as a skill gap. ★ = the designated
champion (pipeline/champion_arms.csv).

## 2006s

**ref `_chm2005_canopy2m_binary.tif`** · scope `sample-test` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2006s_base | 0.7232 | 0.75 | 0.255905 | 0.8108 | 752,916 | 126 | 49 (40) | `phase4/qc/curves/e860a51a8584.csv` |

**ref `ccap_2016_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| hy_e3_2006s | 0.6899 | 0.7505 | 0.425197 | 0.7957 | 14,639,108 | 116 | 585 (240) | `phase4/qc/curves/cb367abc8825.csv` |

**ref `ccap_2016_hires_lc.tif`** · scope `sample-test`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2006s_in16 | 0.7278 | 0.7526 | 0.299212 | 0.8249 | 785,426 | 122 | 49 (40) | `phase4/qc/curves/3b1fa50cef4d.csv` |
| t1_2006s_in05 | 0.7048 | 0.7518 | 0.263779 | 0.8053 | 781,330 | 132 | 49 (40) | `phase4/qc/curves/2f8304e98e0d.csv` |
| t1_2006s_base | 0.6695 | 0.7547 | 0.279527 | 0.7945 | 771,762 | 120 | 49 (40) | `phase4/qc/curves/cf5712b98e39.csv` |

**ref `ccap_2021_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| hy_e3_2006s | 0.5492 | 0.7643 | 0.484251 | 0.7567 | 13,013,120 | 101 | 585 (240) | `phase4/qc/curves/76260a965f19.csv` |

**ref `ccap_2021_hires_lc.tif`** · scope `sample-selection`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2006s_in16 | 0.611 | 0.7512 | 0.366141 | 0.7718 | 420,178 | 97 | 49 (40) | `phase4/qc/curves/c7d97323b8be.csv` |
| t1_2006s_in05 | 0.5788 | 0.7515 | 0.291338 | 0.7594 | 416,370 | 119 | 49 (40) | `phase4/qc/curves/7d09560b49b2.csv` |
| t1_2006s_base | 0.5433 | 0.7509 | 0.318897 | 0.7508 | 412,469 | 109 | 49 (40) | `phase4/qc/curves/4dbf3b28e1dc.csv` |
| t1_2006s_add05 | 0.5215 | 0.7505 | 0.413385 | 0.7477 | 410,063 | 86 | 49 (40) | `phase4/qc/curves/7ac21c5fec18.csv` |
| t1_2006s_add16 | 0.0413 | 0.7756 | 0.507874 | 0.5522 | 353,645 | 4 | 49 (40) | `phase4/qc/curves/731186aa5d4e.csv` |

**ref `ccap_2021_hires_lc.tif`** · scope `sample-test`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2006s_in16 | 0.6308 | 0.7502 | 0.425196 | 0.7844 | 725,795 | 90 | 49 (40) | `phase4/qc/curves/248fff8a9689.csv` |
| t1_2006s_in05 | 0.6073 | 0.7504 | 0.318897 | 0.7685 | 720,951 | 118 | 49 (40) | `phase4/qc/curves/711358679218.csv` |
| t1_2006s_base | 0.5847 | 0.7504 | 0.35433 | 0.7603 | 716,448 | 101 | 49 (40) | `phase4/qc/curves/d44e2f479eb6.csv` |
| hy_e3_2006s | 0.5809 | 0.7538 | 0.480314 | 0.7676 | 713,563 | 84 | 585 (240) | `phase4/qc/curves/f3f65fa1c8fd.csv` |
| t1_2006s_add05 | 0.5676 | 0.751 | 0.413385 | 0.7551 | 712,667 | 93 | 49 (40) | `phase4/qc/curves/9bf4eacc4285.csv` |
| t1_2006s_add16 | 0.0814 | 0.7866 | 0.507874 | 0.5646 | 613,046 | 5 | 49 (40) | `phase4/qc/curves/34dfa874a259.csv` |

## 2009

**ref `ccap_2021_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| trend8_2009 | 0.7424 | 0.75 | 0.452755 | 0.81 | 344,975,021 | 114 | 624 (274) | `phase4/qc/curves/6a5c3556d7d3.csv` |

## 2011s

**ref `_chm2005_canopy2m_binary.tif`** · scope `sample-test` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2011s_base | 0.7106 | 0.75 | 0.263779 | 0.8057 | 8,074,604 | 150 | 281 (70) | `phase4/qc/curves/9a544547ba45.csv` |

**ref `ccap_2016_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| hy_e3_2011s | 0.8333 | 0.7516 | 0.125984 | 0.866 | 163,466,339 | 198 | 589 (266) | `phase4/qc/curves/bf3f2d384437.csv` |

**ref `ccap_2016_hires_lc.tif`** · scope `sample-test`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2011s_in05 | 0.8023 | 0.7504 | 0.204724 | 0.8529 | 8,642,608 | 161 | 281 (70) | `phase4/qc/curves/54f7a4ab6704.csv` |
| t1_2011s_in16 | 0.7961 | 0.7577 | 0.208661 | 0.8626 | 8,559,318 | 175 | 281 (70) | `phase4/qc/curves/235759ed2768.csv` |
| t1_2011s_base | 0.7845 | 0.7506 | 0.224409 | 0.837 | 8,600,795 | 160 | 281 (70) | `phase4/qc/curves/c5ca5e1bcd8a.csv` |

**ref `ccap_2021_hires_lc.tif`** · scope `citywide`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| trend8_2011s | 0.7781 | 0.7504 | 0.185039 | 0.8292 | 150,784,329 | 176 | 589 (266) | `phase4/qc/curves/2b8ac04cee1c.csv` |
| hy_e3_2011s | 0.7699 | 0.7505 | 0.283464 | 0.827 | 150,449,992 | 156 | 589 (266) | `phase4/qc/curves/0a443d46954e.csv` |

**ref `ccap_2021_hires_lc.tif`** · scope `sample-selection`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2011s_in05 | 0.7683 | 0.7503 | 0.216535 | 0.7988 | 4,723,793 | 153 | 281 (70) | `phase4/qc/curves/179af8be78ac.csv` |
| t1_2011s_in16 | 0.7637 | 0.7519 | 0.208661 | 0.8103 | 4,709,905 | 169 | 281 (70) | `phase4/qc/curves/f325ffd8b121.csv` |
| t1_2011s_cor10 | 0.7553 | 0.7505 | 0.240157 | 0.7967 | 4,706,517 | 145 | 281 (70) | `phase4/qc/curves/aa512b99fed3.csv` |
| t1_2011s_cor05 | 0.7471 | 0.7516 | 0.251968 | 0.7962 | 4,690,590 | 139 | 281 (70) | `phase4/qc/curves/9e223c45cfdc.csv` |
| t1_2011s_base | 0.7395 | 0.7513 | 0.244094 | 0.7953 | 4,682,866 | 156 | 281 (70) | `phase4/qc/curves/156a47e69efb.csv` |
| t1_2011s_base_s2 | 0.7334 | 0.7506 | 0.279527 | 0.7895 | 4,678,472 | 168 | 281 (70) | `phase4/qc/curves/bbb3a54fa94c.csv` |
| t1_2011s_add05 | 0.7256 | 0.7507 | 0.303149 | 0.7896 | 4,668,422 | 142 | 281 (70) | `phase4/qc/curves/286e6bc03acc.csv` |
| t1_2011s_base_s3 | 0.7226 | 0.7503 | 0.318897 | 0.7868 | 4,666,392 | 129 | 281 (70) | `phase4/qc/curves/be9e51a9b4bf.csv` |
| t1_2011s_add16 | 0.7012 | 0.7515 | 0.248031 | 0.7855 | 4,634,108 | 143 | 281 (70) | `phase4/qc/curves/7cf5c388ed56.csv` |

**ref `ccap_2021_hires_lc.tif`** · scope `sample-test`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| hy_e3_2011s | 0.7501 | 0.75 | 0.31496 | 0.8322 | 8,070,528 | 143 | 589 (266) | `phase4/qc/curves/0221bc15af53.csv` |
| t1_2011s_in16 | 0.7461 | 0.7528 | 0.228346 | 0.8299 | 8,038,618 | 170 | 281 (70) | `phase4/qc/curves/07fde91988dc.csv` |
| t1_2011s_in05 | 0.7427 | 0.7511 | 0.259842 | 0.8274 | 8,045,369 | 147 | 281 (70) | `phase4/qc/curves/71aa9bc086e2.csv` |
| t1_2011s_cor10 | 0.7285 | 0.75 | 0.346456 | 0.8112 | 8,024,582 | 116 | 281 (70) | `phase4/qc/curves/9672584a4dee.csv` |
| t1_2011s_base | 0.7253 | 0.7502 | 0.362204 | 0.8123 | 8,015,604 | 125 | 281 (70) | `phase4/qc/curves/5343fd27fe0a.csv` |
| t1_2011s_cor05 | 0.7251 | 0.7503 | 0.389763 | 0.8104 | 8,015,053 | 104 | 281 (70) | `phase4/qc/curves/13f9889f6aa0.csv` |
| t1_2011s_add05 | 0.7243 | 0.75 | 0.437007 | 0.7973 | 8,015,663 | 112 | 281 (70) | `phase4/qc/curves/c73982da6bcc.csv` |
| t1_2011s_base_s2 | 0.7201 | 0.7506 | 0.370078 | 0.8202 | 8,001,592 | 138 | 281 (70) | `phase4/qc/curves/a7a167c7dcb9.csv` |
| t1_2011s_base_s3 | 0.7168 | 0.7504 | 0.452755 | 0.81 | 7,995,912 | 101 | 281 (70) | `phase4/qc/curves/0bb3a680d266.csv` |
| t1_2011s_add16 | 0.6989 | 0.7502 | 0.346456 | 0.8034 | 7,959,213 | 120 | 281 (70) | `phase4/qc/curves/d49dc8502705.csv` |

## 2013

**ref `ccap_2021_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| trend8_2013 | 0.7748 | 0.7512 | 0.153543 | 0.8116 | 1,390,014,655 | 197 | 628 (278) | `phase4/qc/curves/4f31ed3fa74a.csv` |

## 2015

**ref `ccap_2021_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| trend8_2015 | 0.71 | 0.751 | 0.169291 | 0.7746 | 1,366,533,758 | 176 | 601 (241) | `phase4/qc/curves/f733fc9f1eac.csv` |

## 2016

**ref `_chm2_canopy2m_binary.tif`** · scope `sample-test`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2016_in16 | 0.8713 | 0.7506 | 0.125984 | 0.9069 | 7,643,036 | 202 | 511 (137) | `phase4/qc/curves/f035d0766a4c.csv` |
| t1_2016_base | 0.681 | 0.757 | 0.515748 | 0.7992 | 7,222,746 | 91 | 511 (137) | `phase4/qc/curves/59d4b7bc805d.csv` |

**ref `ccap_2016_hires_lc.tif`** · scope `sample-test`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2016_in05 | 0.7874 | 0.7542 | 0.141732 | 0.8553 | 8,573,049 | 185 | 511 (137) | `phase4/qc/curves/ab2827d2676c.csv` |
| t1_2016_in16 | 0.7848 | 0.754 | 0.133858 | 0.8611 | 8,569,442 | 200 | 511 (137) | `phase4/qc/curves/ead2ab15d4f9.csv` |
| t1_2016_base | 0.7207 | 0.7577 | 0.507874 | 0.8215 | 8,394,958 | 93 | 511 (137) | `phase4/qc/curves/282ecf5ad5ae.csv` |

**ref `ccap_2021_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| trend8_2016 | 0.7855 | 0.7515 | 0.181102 | 0.8304 | 150,909,963 | 184 | 612 (293) | `phase4/qc/curves/9536536fd441.csv` |

**ref `ccap_2021_hires_lc.tif`** · scope `sample-selection`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2016_nir | 0.7575 | 0.7544 | 0.165354 | 0.7999 | 4,689,167 | 202 | 511 (137) | `phase4/qc/curves/8e4a621978c4.csv` |
| t1_2016_in05 | 0.7467 | 0.7518 | 0.15748 | 0.8018 | 4,688,742 | 178 | 511 (137) | `phase4/qc/curves/17615f0c83de.csv` |
| t1_2016_add05 | 0.7446 | 0.7501 | 0.259842 | 0.7956 | 4,694,232 | 165 | 521 (141) | `phase4/qc/curves/337d65392c53.csv` |
| t1_2016_in16 | 0.7395 | 0.753 | 0.145669 | 0.7999 | 4,673,755 | 190 | 511 (137) | `phase4/qc/curves/b15504952362.csv` |
| t1_2016_add16 | 0.7349 | 0.7505 | 0.287401 | 0.7936 | 4,680,316 | 143 | 500 (129) | `phase4/qc/curves/53bb6cd7ed59.csv` |
| t1_2016_base | 0.6355 | 0.7601 | 0.515748 | 0.7675 | 4,515,897 | 70 | 511 (137) | `phase4/qc/curves/0bb68f6dc0b8.csv` |

**ref `ccap_2021_hires_lc.tif`** · scope `sample-test`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2016_add05 | 0.7505 | 0.7502 | 0.27559 | 0.8319 | 8,071,536 | 163 | 521 (141) | `phase4/qc/curves/45303ceb6965.csv` |
| t1_2016_in05 | 0.7441 | 0.7504 | 0.173228 | 0.819 | 8,055,701 | 177 | 511 (137) | `phase4/qc/curves/0101ae007167.csv` |
| t1_2016_nir | 0.7429 | 0.7503 | 0.181102 | 0.8277 | 8,053,688 | 203 | 511 (137) | `phase4/qc/curves/46050675c240.csv` |
| t1_2016_add16 | 0.7353 | 0.7505 | 0.326771 | 0.8163 | 8,035,706 | 136 | 500 (129) | `phase4/qc/curves/924fbab80b9a.csv` |
| t1_2016_in16 | 0.7351 | 0.7521 | 0.161417 | 0.8236 | 8,021,838 | 193 | 511 (137) | `phase4/qc/curves/0c1b9e4ae7cc.csv` |
| t1_2016_base | 0.6693 | 0.7582 | 0.515748 | 0.7957 | 7,835,508 | 91 | 511 (137) | `phase4/qc/curves/44caf2abc57d.csv` |

## 2017

**ref `ccap_2021_hires_lc.tif`** · scope `citywide`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| heal_2017 | 0.7962 | 0.7529 | 0.161417 | 0.7865 | 5,580,636,711 | 99 | 650 (404) | `phase4/qc/curves/efb2813b8a46.csv` |
| of_2017 | 0.7878 | 0.7531 | 0.23622 | 0.7962 | 5,567,361,941 | 193 | 650 (404) | `phase4/qc/curves/77dd08bf8bed.csv` |

## 2017k

**ref `ccap_2021_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| of_2017k | 0.8159 | 0.75 | 0.133858 | 0.8223 | 1,406,952,724 | 182 | 632 (305) | `phase4/qc/curves/51da78ca2773.csv` |

## 2017n

**ref `ccap_2021_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| of_2017n | 0.1982 | 0.7632 | 0.480314 | 0.7012 | 11,805,490 | 63 | 582 (216) | `phase4/qc/curves/49ba3c0af71e.csv` |

## 2017s

**ref `ccap_2021_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| of_2017s | 0.7462 | 0.751 | 0.165354 | 0.8191 | 149,422,078 | 184 | 557 (212) | `phase4/qc/curves/0b157d79812c.csv` |

## 2019

**ref `ccap_2021_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| trend8_2019 | 0.752 | 0.7582 | 0.114173 | 0.8093 | 1,371,436,455 | 219 | 600 (264) | `phase4/qc/curves/fe90bb21a580.csv` |

## 2019n

**ref `ccap_2021_hires_lc.tif`** · scope `sample-selection`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2019n_nir | 0.6733 | 0.7582 | 0.503937 | 0.8031 | 1,177,454 | 93 | 235 (99) | `phase4/qc/curves/edb2f243abfd.csv` |
| t1_2019n_base | 0.6564 | 0.7609 | 0.507874 | 0.7951 | 1,169,224 | 90 | 235 (99) | `phase4/qc/curves/03f2f6f56c45.csv` |

**ref `ccap_2021_hires_lc.tif`** · scope `sample-test`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2019n_nir | 0.7146 | 0.7507 | 0.496062 | 0.8105 | 2,060,933 | 94 | 235 (99) | `phase4/qc/curves/db86a9ec08d4.csv` |
| t1_2019n_base | 0.6749 | 0.7638 | 0.507874 | 0.8038 | 2,013,332 | 92 | 235 (99) | `phase4/qc/curves/50cffc0c3217.csv` |

## 2020

**ref `ccap_2021_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| of_2020 | 0.6842 | 0.7936 | 0.070866 | 0.7488 | 4,894,691,267 | 206 | 690 (438) | `phase4/qc/curves/78c9944728d2.csv` |

**ref `ccap_2021_hires_lc.tif`** · scope `sample-selection`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2020_add16 | 0.6656 | 0.7828 | 0.110236 | 0.7801 | 164,764,746 | 149 | 637 (339) | `phase4/qc/curves/b65557fb3b0f.csv` |
| t1_2020_base | 0.66 | 0.7506 | 0.102362 | 0.7655 | 169,582,872 | 203 | 631 (343) | `phase4/qc/curves/706d2a0ddf83.csv` |
| t1_2020_add05 | 0.6496 | 0.7979 | 0.122047 | 0.8064 | 161,964,867 | 203 | 642 (338) | `phase4/qc/curves/e12a81bd20c8.csv` |
| t1_2020_in05 | 0.6279 | 0.7877 | 0.07874 | 0.7591 | 162,620,081 | 204 | 631 (343) | `phase4/qc/curves/57423be5a018.csv` |
| t1_2020_in16 | 0.6132 | 0.811 | 0.070866 | 0.7718 | 158,952,446 | 186 | 631 (343) | `phase4/qc/curves/f1fdbdaf1b5f.csv` |

**ref `ccap_2021_hires_lc.tif`** · scope `sample-test`

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| t1_2020_add16 | 0.7005 | 0.7664 | 0.110236 | 0.7739 | 289,376,644 | 149 | 637 (339) | `phase4/qc/curves/5a82948bc617.csv` |
| t1_2020_add05 | 0.6871 | 0.7889 | 0.122047 | 0.7972 | 282,309,538 | 204 | 642 (338) | `phase4/qc/curves/1f54f9e72dc3.csv` |
| t1_2020_in05 | 0.6753 | 0.7702 | 0.07874 | 0.7491 | 286,525,941 | 203 | 631 (343) | `phase4/qc/curves/9595f4c2dc6b.csv` |
| t1_2020_in16 | 0.6592 | 0.7968 | 0.070866 | 0.7693 | 278,556,372 | 187 | 631 (343) | `phase4/qc/curves/9c398cbbc467.csv` |
| t1_2020_base | 0.6402 | 0.7999 | 0.106299 | 0.7552 | 276,658,178 | 205 | 631 (343) | `phase4/qc/curves/cd1b7c272e35.csv` |

## 2021

**ref `ccap_2021_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| trend8_2021 | 0.8157 | 0.7502 | 0.106299 | 0.8391 | 1,406,539,700 | 190 | 615 (287) | `phase4/qc/curves/e1db5afaea4b.csv` |

## 2022

**ref `ccap_2021_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| of_2022 | 0.743 | 0.7511 | 0.133858 | 0.7848 | 5,178,270,225 | 170 | 660 (423) | `phase4/qc/curves/d11d69cb719f.csv` |

## 2024

**ref `ccap_2021_hires_lc.tif`** · scope `citywide` — single arm, nothing to rank against

| arm | recall | precision | thresh | pr_auc | population | eligible cuts | tiles (train) | curve |
|---|---|---|---|---|---|---|---|---|
| trend8_2024 | 0.6955 | 0.7524 | 0.055118 | 0.7449 | 5,436,883,153 | 180 | 646 (423) | `phase4/qc/curves/7155b9466840.csv` |
