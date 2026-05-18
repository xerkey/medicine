# 薬機法広告チェッカーAI 学習・評価データセット

医薬品、医療機器等の品質、有効性及び安全性の確保等に関する法律（以下、薬機法）の広告規制に基づき、AIによる広告表現チェックを行うための参照データセットおよび評価データセットです。

## ディレクトリ構成

```
.
├── reference/                      # AIに参照させる根拠データ
│   ├── laws.md                     # 薬機法および関連法令の条文（2024-2025年改正含む）
│   ├── guidelines.md               # 医薬品等適正広告基準＋業界自主基準
│   ├── cosmetic_efficacy_56.json   # 化粧品の効能効果範囲56項目
│   ├── quasi_drug_efficacy.json    # 医薬部外品の効能効果範囲
│   ├── ng_expression_patterns.jsonl # NG表現パターン集（200件）
│   ├── ok_expression_patterns.jsonl # 認められる表現パターン集（80件）
│   ├── case_studies.jsonl          # 行政処分・裁判事例（63件、実事例含む）
│   ├── category_rules.jsonl        # カテゴリ別ルール（60件）
│   └── sources.md                  # 参照した一次・二次情報源URL一覧
│
└── evaluation/                     # AI構築後の評価データ
    ├── eval_dataset.jsonl          # メイン評価データセット（150件）
    ├── boundary_cases.jsonl        # 境界値・グレーゾーン事例（60件）
    ├── edge_cases.jsonl            # 外れ値・極端事例（50件）
    └── adversarial_cases.jsonl     # 敵対的事例（巧妙な迂回表現、40件）
```

## データソースとカバレッジ

参照データは以下の一次・二次情報源を統合：
- **一次情報源**: 厚生労働省通知、薬機法条文、消費者庁ガイドライン、医療広告ガイドライン、東京都・茨城県等の薬務課資料、国民生活センター
- **業界自主基準**: 日本化粧品工業会「化粧品等の適正広告ガイドライン2020」、日本浴用剤工業会、日本ホームヘルス機器協会「家庭向け美容・健康関連機器 適正広告表示ガイド」
- **審査機関**: JARO（公益社団法人日本広告審査機構）
- **実事例**: 2024-2025年の措置命令・刑事事件・課徴金事例（インプレッション社家庭用電位治療器事件、大正製薬・ロート製薬ステマ事件、紅麹サプリ事件、コロナ後遺症健康食品事件、スマートドラッグ事件等）

詳細URL一覧は `reference/sources.md` を参照。

## 対象カテゴリ

1. **医療用医薬品**（処方薬）
2. **一般用医薬品**（OTC、第1類〜第3類）
3. **医薬部外品**（薬用化粧品、育毛剤、入浴剤など）
4. **化粧品**（基礎化粧品、メイク、ヘアケアなど）
5. **医療機器**（クラスI〜IV）
6. **健康食品・サプリメント**（特定保健用食品、機能性表示食品、いわゆる健康食品）
7. **美容医療・自由診療**
8. **再生医療等製品**

## 評価データの分類タグ

- `verdict`: `OK` / `NG` / `GRAY`
- `severity`: `low` / `medium` / `high` / `critical`
- `type`: `clear_ok` / `clear_ng` / `boundary` / `outlier` / `adversarial`
- `category`: 対象カテゴリ
- `violated_articles`: 違反する法令・基準（NG/GRAY時）

## 参考法令

- 医薬品、医療機器等の品質、有効性及び安全性の確保等に関する法律（薬機法）
- 医薬品等適正広告基準（厚生労働省）
- 健康増進法
- 不当景品類及び不当表示防止法（景表法）
- 特定商取引法

---

## チェッカー実装

`checker/` に Claude API を使った参照実装が入っています。Embedding を使わず、ルールベース（カテゴリ別ルール＋効能効果範囲を常に投入、NGキーワード逆引きインデックスで関連パターンを取得）でコンテキストを構築し、判定だけを LLM に任せるハイブリッド構成。

### アーキテクチャ

```
入力テキスト + メタデータ(category, medium, subtype)
    │
    ├─ 正規化（NFKC + 装飾文字/伏字/スペース剥がし）
    │      → 「シ★ミが消える」を「シミが消える」として扱う
    │
    ├─ 取得（rule-based / no embeddings）
    │   ├─ 該当カテゴリのルール（category_rules.jsonl から抽出、全件）
    │   ├─ 該当カテゴリの効能効果範囲（cosmetic_56 / quasi_drug）
    │   ├─ NGキーワード逆引き → ヒットしたNGパターン（severity順）
    │   ├─ 該当カテゴリのOKパターン（参考に投入）
    │   └─ 該当カテゴリの過去事例
    │
    └─ 判定（Claude Sonnet 4.6 デフォルト）
            ├─ system prompt: キャッシュ
            ├─ カテゴリ参照ブロック: キャッシュ（カテゴリ毎に再利用）
            └─ 可変ブロック: 入力ごとに変動

    → JSON: verdict / severity / violated_articles /
            matched_ng_pattern_ids / rationale / rewrite_suggestion
```

### セットアップ

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

### 単発チェック

```python
from checker import Checker

c = Checker()  # デフォルト: claude-sonnet-4-6
result = c.check("シミが消える美容液", category="化粧品")
print(result.verdict)           # "NG"
print(result.severity)          # "high"
print(result.violated_articles) # ["薬機法第66条"]
print(result.rationale)         # "化粧品では『日やけによるシミ、ソバカスを防ぐ』..."
print(result.rewrite_suggestion)# "日やけによるシミ、ソバカスを防ぐ美容液"
```

メタデータは人間が与える前提：

| 引数 | 値 |
|------|------|
| `category` | `化粧品` / `医薬部外品` / `一般用医薬品` / `医療用医薬品` / `医療機器` / `健康食品` / `美容医療` / `雑貨` 等 |
| `medium` | `Web` / `SNS` / `TV` / `紙面` / `店頭POP` / `口頭` / `メール・LINE` 等（デフォルト `Web`） |
| `subtype` | 任意の絞り込みタグ（例: `化粧品 > 美白訴求`） |

### 評価データセットでの一括評価

```bash
# まず10件だけ試す
python scripts/evaluate.py --eval-file evaluation/eval_dataset.jsonl --limit 10

# 全件（150件）
python scripts/evaluate.py --eval-file evaluation/eval_dataset.jsonl

# 境界値・敵対的・外れ値
python scripts/evaluate.py --eval-file evaluation/boundary_cases.jsonl
python scripts/evaluate.py --eval-file evaluation/adversarial_cases.jsonl
python scripts/evaluate.py --eval-file evaluation/edge_cases.jsonl

# モデルを変える（Opus 4.7 で高精度版）
python scripts/evaluate.py --eval-file evaluation/eval_dataset.jsonl --model claude-opus-4-7
```

出力: 全体精度、`type` 別精度、3×3混同行列、トークン使用量。詳細結果は `evaluation/results.jsonl` に保存。

### 設計上のポイント

- **Embedding を使わない理由**: 「シミを薄くする」(NG) と「シミを防ぐ」(OK) を埋め込みで弁別するのは困難。短文パターンが多く、`ng_keywords` フィールドへの直接マッチが効率的かつ説明可能。
- **正規化レイヤー**: 装飾文字（★・◆等）、全角スペース、中黒の挿入を `strip_for_matching` で除去し、検閲回避を検出。
- **プロンプトキャッシュ**: カテゴリ参照ブロック（~2,500トークン）にキャッシュ breakpoint を置き、同一カテゴリの連続呼び出しでキャッシュヒット。
- **LLM の役割**: キーワードヒットは「候補」として渡し、文脈判断（GRAY なのか NG なのか、メーキャップ効果が冠されているか等）を LLM に任せる。
