# 間隔反復システム

### FSRS (Free Spaced Repetition Scheduler)

Neuronごとに安定性・難易度・次回復習日を管理する間隔反復スケジューラ。
FSRS v6はニューラルネットワークベースで、
Ankiデフォルトの SM-2 より想起予測の精度が高いです。

- グラフ伝播はFSRS状態を変えません — 影響するのは圧力だけ
- 各Neuronが独立した安定性・難易度パラメータを持つ
- グレード対応: `miss` → Again, `weak` → Hard, `fire` → Good, `strong` → Easy

### 参考文献

- Ye, J. (2024). FSRS: A modern spaced repetition algorithm. [github.com/open-spaced-repetition/fsrs4anki](https://github.com/open-spaced-repetition/fsrs4anki)
- Wozniak, P. A. & Gorzelanczyk, E. J. (1994). Optimization of repetition spacing in the practice of learning. *Acta Neurobiologiae Experimentalis*, 54, 59–62.
- Leitner, S. (1972). *So lernt man lernen*. Herder.
