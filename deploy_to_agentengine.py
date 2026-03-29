#l/usr/bin/env python3
Script 3: Deploy Agent to Agent EngineDeploys the POM testing agent to Google Cloud using ADK
import subprocess import sys import os
# Configuration
PROJECT_ID = "np-sc-inventory-execution"
REGION = "us-central1"
DISPLAY_NAME = "pom_agent_v2.0"
DESCRIPTION = "POM Testing Al Agent V2 - Purchase Order Management with RAG corpus and memory bank"
AGENT_DIR = "pom_testing_agent"
VENV_PATH = "./venv-deploy/bin/activate"
det main(:
print("=" * 60)
print(f"Display Name: (DISPLAY_NAME)")
# Check if agent directory exists
if not os.path.exists(AGENT_DIR):
print(f" X Error: Agent directory not found: (AGENT_DIR)")
return 1
# Activate virtual environment and run adk deploy
cma = fsource VEN_PATH) &d adk deploy agent_engine --project-{PROJECT_ID) --region=(REGION) --
display_name-"(DISPLAY_NAME)" --description=" (DESCRIPTION)" [AGENT_DIR)'
print(f"Activating virtual environment: (VENV_PATH)")
result = subprocess.run
cmd,
shell= True,
executable=/bin/zsh, check=True, capture_output-True, text=True
print(result.stdout)
if result.stderr:
print(result.stderr)
printo print
Agent deployed successfully")
print
print"To test the deployed agent, use:")
print(f"python test deployed_agent.py")
return 0
except subprocess.CalledProcessError as e:
print(f" Error deploying agent:")
print(e.stdout)
print(e.stderr)
return 1
if _name_=="main_" sys.exit(main()