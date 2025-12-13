# Tribal Genealogy Extraction - Change Log

This file tracks learnings, discoveries, and decisions made during the extraction pipeline development.

---

## 2025-12-04: Project Setup

### Initial Planning
- **Strategy approved**: 6-stage pipeline (PDF extraction → normalization → pattern extraction → hierarchy builder → validation → review)
- **Timeline**: 8-10 weeks for MVP
- **Target accuracy**: 99%+ (85-90% automated + 15-20% manual review)

### Key Decisions
1. **Data migration**: Create new `tribal_hierarchy.json` first, validate, then replace `tribe_brain.json`
2. **Extraction strategy**: 2-layer approach (regex 85-90% + LLM fallback for ambiguous cases)
3. **Development approach**: Test-Driven Development (write tests before implementation)

### Technical Discoveries
- PDFs are **native digital text** (not scanned) - good for extraction
- RTL encoding requires `pdfplumber` with `char_dir_render="rtl"`
- ~70% of entries contain multi-level hierarchies (2-7 levels)
- Pattern: "من X، من Y، من Z" appears 287 times in 10-page sample

---

## Next: Weeks 1-2 (Stages 1-2)
- [ ] PDF extraction with RTL handling
- [ ] Arabic normalization (alef variants, diacritics, ya)
- [ ] Test on 5-10 page samples

---

## Learnings Template

### [Date]: [Stage/Component]
**Problem**: [What issue did you encounter?]
**Solution**: [How did you solve it?]
**Impact**: [What changed as a result?]
**Code**: [Link to relevant code/commit if applicable]

---
