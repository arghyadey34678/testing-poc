#!/usr/bin/env python3

# Deploy POM Testing AI Agent to Google Cloud Run
# This script builds the Docker image and deploys it to Cloud Run with proper configuration

import subprocess
import sys
import os
from datetime import datetime

# Configuration
PROJECT_ID = "np-sc-inventory-execution"
SERVICE_NAME = "pom-management-agent"
REGION = "us-central1"
SERVICE_ACCOUNT = "ai-pom-po@np-sc-inventory-execution.iam.gserviceaccount.com"
IMAGE_NAME = f"gcr.io/{PROJECT_ID}/{SERVICE_NAME}"
MEMORY = "2Gi"
CPU = "2"
MAX_INSTANCES = "10"
MIN_INSTANCES = "0"
TIMEOUT = "300"
CONCURRENCY = "80"

def run_command(cmd, description):
    """Run a shell command and handle errors"""
    print(f"\n{'=' * 60}")
    print(f"{description}")
    print(f"{'-' * 60}")
    print(f"Command: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    print()

    try:
        result = subprocess.run(
            cmd,
            shell=isinstance(cmd, str),
            check=True,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {description} failed")
        if e.stdout:
            print(e.stdout)
        if e.stderr:
            print(e.stderr)
        return False

def check_gcloud_auth():
    """Verify gcloud authentication"""
    print("Checking gcloud authentication...")
    try:
        result = subprocess.run(
            ["gcloud", "auth", "list"],
            capture_output=True,
            text=True,
            check=True,
        )
        if "ACTIVE" in result.stdout:
            print("✅ gcloud authentication verified")
            return True
        else:
            print("❌ No active gcloud authentication found")
            print("Run: gcloud auth login")
            return False
    except Exception as e:
        print(f"❌ Error checking authentication: {e}")
        return False

def build_docker_image():
    """Build Docker image using Cloud Build"""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    image_tag = f"{IMAGE_NAME}:{timestamp}"
    image_latest = f"{IMAGE_NAME}:latest"

    cmd = [
        "gcloud", "builds", "submit",
        "--tag", image_tag,
        "--project", PROJECT_ID,
        "--timeout", "20m",
        "--machine-type", "e2-highcpu-8",
        "--disk-size", "100",
        "."
    ]

    if not run_command(cmd, f"Building Docker image: {image_tag}"):
        return None

    # Tag as latest
    tag_cmd = [
        "gcloud", "container", "images", "add-tag",
        image_tag, image_latest,
        "--project", PROJECT_ID,
        "--quiet"
    ]
    
    if run_command(tag_cmd, "Tagging image as latest"):
        return image_latest
    return image_tag

def deploy_to_cloudrun(image):
    """Deploy to Cloud Run"""
    cmd = [
        "gcloud", "run", "deploy", SERVICE_NAME,
        "--image", image,
        "--platform", "managed",
        "--region", REGION,
        "--project", PROJECT_ID,
        "--service-account", SERVICE_ACCOUNT,
        "--memory", MEMORY,
        "--cpu", CPU,
        "--timeout", TIMEOUT,
        "--concurrency", CONCURRENCY,
        "--max-instances", MAX_INSTANCES,
        "--min-instances", MIN_INSTANCES,
        "--port", "8080",
        "--allow-unauthenticated",
        f"--set-env-vars", f"PROJECT_ID={PROJECT_ID},ENVIRONMENT=production",
        "--quiet"
    ]

    return run_command(cmd, f"Deploying to Cloud Run: {SERVICE_NAME}")

def get_service_url():
    """Get the deployed service URL"""
    try:
        result = subprocess.run(
            [
                "gcloud", "run", "services", "describe", SERVICE_NAME,
                "--region", REGION,
                "--project", PROJECT_ID,
                "--format", "value(status.url)"
            ],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"⚠️ Could not retrieve service URL: {e}")
        return None

def main():
    print("=" * 60)
    print("POM Testing AI Agent - Cloud Run Deployment")
    print("=" * 60)
    print(f"Project: {PROJECT_ID}")
    print(f"Service: {SERVICE_NAME}")
    print(f"Region: {REGION}")
    print(f"Service Account: {SERVICE_ACCOUNT}")
    print(f"Image: {IMAGE_NAME}")
    print("-" * 60)
    print()

    # Step 1: Check authentication
    if not check_gcloud_auth():
        print("❌ Deployment aborted: Authentication required")
        return 1

    # Step 2: Build Docker image
    print("\n📦 Starting Docker image build...")
    image = build_docker_image()
    if not image:
        print("❌ Deployment aborted: Image build failed")
        return 1

    # Step 3: Deploy to Cloud Run
    print(f"\n✅ Docker image built successfully: {image}")
    print("\n🚀 Starting Cloud Run deployment...")
    if not deploy_to_cloudrun(image):
        print("❌ Deployment failed")
        return 1

    # Step 4: Get service URL
    service_url = get_service_url()

    print("\n" + "=" * 60)
    print("✅ DEPLOYMENT SUCCESSFUL")
    print("=" * 60)
    print(f"Service Name: {SERVICE_NAME}")
    print(f"Region: {REGION}")
    if service_url:
        print(f"Service URL: {service_url}")
        print(f"\nTest the service:")
        print(f"curl {service_url}/health")
    print("\nView logs:")
    print(f"gcloud run logs read {SERVICE_NAME} --region={REGION} --project={PROJECT_ID}")
    print("\nView service details:")
    print(f"gcloud run services describe {SERVICE_NAME} --region={REGION} --project={PROJECT_ID}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())