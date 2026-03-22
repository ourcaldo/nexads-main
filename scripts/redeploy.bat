@echo off
cd /d C:\Users\Administrator\Desktop\nexads
python scripts\deploy-runner.py redeploy >> logs\redeploy.log 2>&1
