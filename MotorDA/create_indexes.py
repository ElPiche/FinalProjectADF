"""MongoDB Index Creation Script for Anomaly Detection.

This script creates indexes for the anomaly_detection database collections
to improve query performance, especially for detection operations.

Run inside the kb-mcp or dispatcher container:
    docker exec kb-mcp python create_indexes.py
    docker exec da-dispatcher python create_indexes.py

Indexes created:
1. series_result: (kb_id, dimension) - For fast training result lookups
2. series: (metadata.kbId, metadata.dim, metadata.mode) - For series data queries
3. training_config: (kb_id) - For training config lookups
4. bucket_profiles: (_id) - Already indexed as _id, but we add for consistency
"""

import sys
from pymongo import MongoClient, ASCENDING


# MongoDB connection string
MONGO_URL = "mongodb://admin:1q2w3E%2A@mongodb:27017/?authSource=admin"
DB_NAME = "anomaly_detection"


def create_indexes():
    """Create all necessary indexes for anomaly detection performance."""
    
    print("=" * 60)
    print("MongoDB Index Creation for Anomaly Detection")
    print("=" * 60)
    
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        print("✓ Connected to MongoDB")
    except Exception as e:
        print(f"✗ Failed to connect to MongoDB: {e}")
        sys.exit(1)
    
    db = client[DB_NAME]
    indexes_created = 0
    
    # 1. series_result collection - for training result lookups during detection
    print("\n1. Creating indexes on 'series_result' collection...")
    try:
        result = db["series_result"].create_index(
            [("kb_id", ASCENDING), ("dimension", ASCENDING)],
            name="kb_id_dimension_idx",
            background=True
        )
        print(f"   ✓ Created index: {result}")
        indexes_created += 1
    except Exception as e:
        print(f"   ⚠ Index may already exist or error: {e}")
    
    # 2. series collection - for series data queries during training/detection
    print("\n2. Creating indexes on 'series' collection...")
    try:
        result = db["series"].create_index(
            [
                ("metadata.kbId", ASCENDING),
                ("metadata.dim", ASCENDING),
                ("metadata.mode", ASCENDING)
            ],
            name="metadata_kbId_dim_mode_idx",
            background=True
        )
        print(f"   ✓ Created index: {result}")
        indexes_created += 1
    except Exception as e:
        print(f"   ⚠ Index may already exist or error: {e}")
    
    # Additional timestamp index for series
    try:
        result = db["series"].create_index(
            [
                ("metadata.kbId", ASCENDING),
                ("metadata.dim", ASCENDING),
                ("timestamp", ASCENDING)
            ],
            name="metadata_kbId_dim_timestamp_idx",
            background=True
        )
        print(f"   ✓ Created index: {result}")
        indexes_created += 1
    except Exception as e:
        print(f"   ⚠ Index may already exist or error: {e}")
    
    # 3. training_config collection - for training config lookups
    print("\n3. Creating indexes on 'training_config' collection...")
    try:
        result = db["training_config"].create_index(
            [("kb_id", ASCENDING)],
            name="kb_id_idx",
            background=True
        )
        print(f"   ✓ Created index: {result}")
        indexes_created += 1
    except Exception as e:
        print(f"   ⚠ Index may already exist or error: {e}")
    
    # 4. bucket_profiles collection - _id is already indexed, but add profile_id if used
    print("\n4. Verifying indexes on 'bucket_profiles' collection...")
    try:
        # _id is always indexed, just list existing indexes
        existing_indexes = list(db["bucket_profiles"].list_indexes())
        print(f"   ✓ Existing indexes: {[idx['name'] for idx in existing_indexes]}")
    except Exception as e:
        print(f"   ⚠ Error: {e}")
    
    # Print summary
    print("\n" + "=" * 60)
    print(f"Index creation complete. Created {indexes_created} new indexes.")
    print("=" * 60)
    
    # List all indexes for verification
    print("\nFinal index summary:")
    for collection_name in ["series_result", "series", "training_config", "bucket_profiles"]:
        try:
            indexes = list(db[collection_name].list_indexes())
            print(f"\n  {collection_name}:")
            for idx in indexes:
                print(f"    - {idx['name']}: {idx.get('key', {})}")
        except Exception as e:
            print(f"\n  {collection_name}: Error listing indexes - {e}")
    
    client.close()
    print("\n✓ Done!")


if __name__ == "__main__":
    create_indexes()
