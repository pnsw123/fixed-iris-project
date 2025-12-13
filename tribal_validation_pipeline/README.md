# LLM-Centric Tribal Validation Pipeline

**Automated Verification of Arabic Tribal Lineages**

This pipeline uses **Claude 3.5 Haiku** via the Anthropic Message Batches API to extract, validate, and build hierarchical tribal trees from OCR source data.

## Overview

The LLM is the "brain" at every stage - no regex parsers, no rule-based filters. All intelligence comes from the LLM.

### Pipeline Stages

| Stage | Description | Output |
|-------|-------------|--------|
| **Step 1** | Extract tribes & relationships from raw OCR | `step1_tribal_extractions.jsonl` |
| **Step 2** | Validate each relationship, classify entities | `step2_validated_relationships.jsonl` |
| **Step 3** | Build hierarchical tribal tree | `step3_tribal_tree.json` |
| **Step 4** | Verify tree against source OCR (truth check) | `step4_verified_tree.json` |

## Data Sources

- **Source**: `tribal_extraction_full/data/cleaned/` (~13,450 pages from multiple PDFs)
  - Main tribal book (`page_*.txt`)
  - tribe3, tribe4, tribes2, tribes6 PDFs (`ocr_*.txt`)

## Cost Estimate

Using **Claude 3.5 Haiku** with **Batch API** (50% discount):

```
Model: claude-3-5-haiku-20241022
Budget: $14.00

Step 1 (Extraction):  ~$10.49
Step 2 (Validation):  ~$3.20
Step 3 (Tree Build):  ~$0.18
Step 4 (Verify):      ~$0.20
────────────────────────────
TOTAL:                ~$14.06
```

> **Note**: Slightly over budget with all 13,450 pages. Consider processing in stages or reducing page count.

## Usage

### Check Cost Estimate
```bash
python3 config.py
```

### Run with Mock Client (No API Calls)
```bash
python3 run_pipeline.py --mock --limit 100
```

### Run Full Pipeline
```bash
# Set your API key
export ANTHROPIC_API_KEY="your-api-key"

# Run pipeline (will ask for confirmation if over budget)
python3 run_pipeline.py
```

### Resume from Checkpoint
The pipeline automatically resumes from the last checkpoint. State is saved after each step.

```bash
# Reset and start fresh
python3 run_pipeline.py --reset
```

## Output Files

After completion:

```
output/
├── tribal_tree_verified.json  # Final verified tribal tree
```

Checkpoints:
```
checkpoints/
├── pipeline_state.json         # Current pipeline state
├── step1_tribal_extractions.jsonl
├── step2_validated_relationships.jsonl
├── step3_tribal_tree.json
└── step4_verified_tree.json
```

## Arabic Prompts

The prompts are optimized for Arabic text using XML tags. Key features:

1. **Entity Classification**:
   - **قبيلة (TRIBE)**: بنو، بني، آل، قبيلة، عشيرة، بطن، فخذ
   - **شخص (PERSON)**: بن، ابن، أبو (individual names)

2. **Relationship Types**:
   - `LINEAGE_BLOOD` - Blood relationship (father → son)
   - `TRIBAL_BRANCH` - Tribal subdivision (tribe → subtribe)
   - `TRIBAL_MEMBERSHIP` - Person belongs to tribe
   - `ALLIANCE` - Political/tribal alliance
   - `EPONYMOUS_FOUNDER` - Founder gave name to tribe

3. **Verification Levels**:
   - `VERIFIED` - Explicitly stated in source text
   - `INFERRED` - Inferred from context
   - `UNVERIFIED` - Not found in source
   - `CONTRADICTED` - Source contradicts relationship

## Requirements

```bash
pip install anthropic
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |

## Architecture

```
┌─────────────────┐
│   OCR Source    │  13,450 pages (Arabic text)
│   (cleaned/)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Step 1: Extract │  LLM extracts tribes + relationships
│  (Batch API)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Step 2: Validate│  LLM validates each relationship
│  (Batch API)    │  Classifies: Person vs Tribe
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Step 3: Build   │  LLM builds hierarchical tree
│  Tree           │  Resolves conflicts
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Step 4: Verify  │  LLM checks tree against source
│  (Truth Check)  │  OCR is source of truth
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Final Output    │  tribal_tree_verified.json
└─────────────────┘
```
