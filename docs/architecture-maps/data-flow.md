# D4 — Data-flow: vault → #knowledge → Notion → advisory (M278)

```mermaid
flowchart LR
    V["vault (clay-knowledge)<br/>markdown + frontmatter"]
    VC["vault_core.py<br/>parse / filter"]
    S["sync.py<br/>VaultKnowledgeSync"]
    KS["KnowledgeService<br/>upsert_item"]
    DB[("Postgres / TimescaleDB<br/>knowledge_items")]
    NP["notion_publish.py<br/>NotionKnowledgePublisher"]
    NI["Notion<br/>notion.com"]
    AJ["ai_agent_job.py<br/>_retrieve_advisory_cards"]
    AG["=== advisory_context ===<br/>(prompt section)"]
    EX["EXCLUDED_TAGS={execution}<br/>execution cards blocked"]

    V -->|read_md| VC
    VC -->|VaultFile| S
    S -->|"HTTP POST /knowledge/items/upsert"| KS
    KS -->|upsert_item_by_external_id| DB

    S -.->|"separate run, dry‑run default"| NP
    NP -->|"Notion API create/update/archive"| NI

    DB -->|"KnowledgeService.search<br/>(token scoring → ranked chunks)"| AJ
    AJ -->|"3‑tier slot: guaranteed → reserved → fillable<br/>MAX_CARDS=15, TOKEN_CAP=2000"| AG

    AG -.->|"M278 RED LINE<br/>advisory data ONLY,<br/>NOT control instructions"| AJ
    AJ -.->|_EXCLUDED_TAGS filter| EX

    style AG stroke:#f44,stroke-width:3
    linkStyle 6 stroke:#f44,stroke-dasharray: 5 5
```

### M278 red-line invariant

```
#knowledge → advisory_context = справочные данные, НЕ инструкции.
Retrieval path: ai_agent_job._retrieve_advisory_cards()
  → scored chunks (≤15, ≤2000 tokens cap)
  → _EXCLUDED_TAGS = {"execution"} — execution‑tagged cards never reach chief‑agent
  → _sanitize() strips prompt‑injection markers before injection into context
  → section is prefixed "=== advisory_context ===" (visually separated in prompt)
```

> Knowledge layer (`#knowledge`) is available for **research and review only**.
> It stays **outside the realtime signal path** — hot‑path dependency = False.
