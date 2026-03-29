#!/usr/bin/env python3
"""
Script 3: Deploy Agent to Agent Engine
Deploys the POM testing agent to Google Cloud using ADK
"""
import subprocess
import sys
import os

# Configuration
PROJECT_ID = "np-sc-inventory-execution"
REGION = "us-central1"
DISPLAY_NAME = "pom_agent_v2.0"
DESCRIPTION = "POM Testing AI Agent V2 - Purchase Order Management with RAG corpus and memory bank"
AGENT_DIR = "pom_testing_agent"
VENV_PATH = "./venv-deploy/bin/activate"

def main():
    print("=" * 60)
    print(f"Display Name: {DISPLAY_NAME}")
    
    # Check if agent directory exists
    if not os.path.exists(AGENT_DIR):
        print(f"❌ Error: Agent directory not found: {AGENT_DIR}")
        return 1
    
    # Activate virtual environment and run adk deploy
    cmd = f'source {VENV_PATH} && adk deploy agent_engine --project={PROJECT_ID} --region={REGION} --display_name="{DISPLAY_NAME}" --description="{DESCRIPTION}" {AGENT_DIR}'
    
    print(f"Activating virtual environment: {VENV_PATH}")
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            executable='/bin/zsh',
            check=True,
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
            
        print()
        print("✅ Agent deployed successfully")
        print()
        print("To test the deployed agent, use:")
        print("python test_deployed_agent.py")
        return 0
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error deploying agent:")
        print(e.stdout)
        print(e.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())