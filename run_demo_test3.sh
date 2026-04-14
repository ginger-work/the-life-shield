#!/bin/bash
cd /Users/ginger/.openclaw/workspace/the-life-shield
source .venv/bin/activate
export APP_ENV=test
export SECRET_KEY=thelifeshield-demo-key-2026
export DATABASE_URL=sqlite:///./demo.db
export PYTHONPATH=/Users/ginger/.openclaw/workspace/the-life-shield
python3 /tmp/test_demo.py 2>&1 | tail -40
