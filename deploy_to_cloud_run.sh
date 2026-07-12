#!/usr/bin/env bash
# Standalone Google Cloud Run Deployment Script for NaijaBoost AI
# Triggers automated multi-step Cloud Build pipeline using cloudbuild.yaml

set -euo pipefail

echo "=== 🚀 NaijaBoost AI Production Deployment Launcher ==="

# Verify gcloud CLI availability
if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: Google Cloud CLI (gcloud) is not installed or not in PATH."
    echo "Please install gcloud SDK or execute this script inside Google Cloud Shell."
    exit 1
fi

# Run deployment configuration compliance verification first
echo "-> Executing pre-deployment configuration check..."
python3 deploy_check.py

# Prompt for PROJECT_ID if not already configured in gcloud
PROJECT_ID=$(gcloud config get-value project 2>/dev/null || true)
if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" == "(unset)" ]; then
    echo "⚠️ Google Cloud Project ID is not set in active gcloud configuration."
    read -p "Enter your Google Cloud Project ID (e.g., naijaboost-ai-prod): " PROJECT_ID
    gcloud config set project "$PROJECT_ID"
fi

echo "-> Submitting build to Google Cloud Build (Project: $PROJECT_ID)..."
gcloud builds submit --config=cloudbuild.yaml .

echo "✅ Cloud Build submitted successfully!"
echo "Upon completion, your production service will be accessible via Google Cloud Run (europe-west1)."
