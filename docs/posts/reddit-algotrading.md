<!--
REDDIT · r/algotrading
Submit at: https://www.reddit.com/r/algotrading/submit
This subreddit removes promotional posts on sight. Frame as a discussion
of negative results, not a project launch.
Stay in the comments to answer methodology questions; the audience is
more technical than HN.
-->

## Title

Open-sourced a 7-factor equity scoring engine with a walk-forward gate. 4 of 6 OOS windows beat baseline; 2 lost. Discussion of the losses?

## Body

Spent 3 days building an open-source factor-scoring stack with point-in-time data (SEC EDGAR + Form 4 + Wikipedia + FMP). Two engines on the same contract: rule-based 7-factor and a gradient-boosted model trained on forward 63-day returns.

Walk-forward gate, 6 rolling 6-month OOS windows from 2021-H1 to 2023-H2, trained on all data before each window:

```
Window      RBA      MLA-7    Lift     Beat?
2021-H1    +79.0%   +55.4%   -23.6pp   no
2021-H2    +55.6%   +71.8%   +16.2pp   YES
2022-H1    -15.8%   -22.8%   -7.0pp    no
2022-H2    +34.2%   +19.8%   -14.4pp   no
2023-H1    +24.7%   +75.8%   +51.1pp   YES
2023-H2     +2.3%   +16.9%   +14.6pp   YES

Mean lift: +6.2 pp · MLA wins 3/6
```

Two questions for the sub:

1. **The 2021-H1 loss (-23pp).** RBA caught the bull leg cleanly, MLA was more conservative. My read is the model trained on 2018-2020 over-weighted the COVID drawdown profile. Anyone with experience training on rate-cycle transitions — what regularization did you find helped most?

2. **Flow factors are within noise.** Added insider_flow (Form 4 net buying) and retail_flow (Wikipedia attention z-score) on top of the classic 5. Head-to-head walk-forward: 5-factor beats 7-factor by 1.5pp on average but loses as often as it wins. Is anyone getting meaningful signal out of pageview-style attention metrics, or is it noise on US large caps specifically?

Repo (MIT, in case anyone wants to fork or run a different universe):
https://github.com/silattrader/trio-web

Methodology + losses written up in docs/algorithms/mla.md. Happy to discuss anything specific in comments.
