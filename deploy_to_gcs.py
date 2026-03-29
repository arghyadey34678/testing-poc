#!/usr/bin/env python3
"""
Script 1: Upload resources to GCS bucket
Uploads all files from pom_testing_agent/resources/to gs://pom_testing_rag/
"""
import subprocess 
import sys
import os
# Configuration
GCS_BUCKET = "gs://pom_testing_rag/"
SOURCE_DIR="/pom_testing_agent/resources/"*
def main:
	print("=" * 60)
	print("TASK 1: Upload Resources to GCS")
	print("=" * 60)
	print(f"Source: (SOURCE_DIR)")
	print Destination: (GCS_BUCKET)*)
	print()
	# Check if source directory exists
	source_path = SOURCE_DIR.replace(/", ")
	if not os.path.exists(source_path):
	print(fError: Source directory not found: (source_path))
	sys.exit(1)
# Run goloud storage copy command
cmd=[
"goloud", "storage", "op", "-r,
SOURCE_DIR, GCS_BUCKET
]
print(f'Running command:{' '.join(cmd)}")
print()
try:
	result = subprocess.run(cmd, check=True, capture_output=True, text=True)
	print(result.stdout)
	if result.stderr:
	print(result.stderr)
	print(" Successfully uploaded files to GCS")
	return 0
except subprocess.CalledProcessError as e:
	print(f"X Error uploading to GCS:")
	print(e.stderr)
	return 1
except FileNotFoundError:
	print("Error: gcloud command not found. Please install Google Cloud SDK.")
	return 1
	
if _name_== "_main_":
	sys.exit(main())