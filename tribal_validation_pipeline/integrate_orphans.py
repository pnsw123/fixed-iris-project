
import json
from pathlib import Path

# Paths
OUTPUT_DIR = Path("gemini_output")
VALIDATED_FILE = OUTPUT_DIR / "v6_validated.json"
ORPHANS_FIXED = OUTPUT_DIR / "orphans_fixed.jsonl"
FINAL_TREE_OUTPUT = OUTPUT_DIR / "tribal_tree_v6_final.json"
MERGED_OUTPUT = OUTPUT_DIR / "v6_validated_augmented.json"

def integrate_orphans():
    print("🔄 Loading datasets...")
    
    # Load original validated data
    with open(VALIDATED_FILE, 'r') as f:
        validated_data = json.load(f)
    
    entities = validated_data.get("entities", [])
    print(f"   Original count: {len(entities):,}")
    
    # Create a lookup for entities to update
    # Key: name + source_page
    entity_map = {f"{e['name']}_{e['source_page']}": e for e in entities}
    
    # Load fixed orphans
    fixed_count = 0
    with open(ORPHANS_FIXED, 'r') as f:
        for line in f:
            try:
                orphan = json.loads(line)
                if orphan.get("fix_status") == "fixed":
                    key = f"{orphan['name']}_{orphan['source_page']}"
                    
                    if key in entity_map:
                        # Update existing
                        entity_map[key].update({
                            "parent": orphan["parent"],
                            "root_tribe": orphan.get("root_tribe"),
                            "full_path": orphan.get("full_path"),
                            "type": orphan.get("type", entity_map[key].get("type")),
                            "status": "recovered_orphan"
                        })
                    else:
                        # Append new (recovered)
                        orphan["status"] = "recovered_orphan_new"
                        entity_map[key] = orphan
                    
                    fixed_count += 1
            except:
                pass
                
    print(f"   Integrated {fixed_count:,} fixed orphans.")
    
    # Convert back to list
    updated_entities = list(entity_map.values())
    print(f"   Final count: {len(updated_entities):,}")
    
    # Save augmented dataset
    with open(MERGED_OUTPUT, 'w') as f:
        json.dump({"entities": updated_entities}, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved merged dataset to {MERGED_OUTPUT}")
    
    return updated_entities

if __name__ == "__main__":
    integrate_orphans()
