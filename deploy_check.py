#!/usr/bin/env python3
"""Deployment configuration validation script for NaijaBoost AI Google Cloud Run environment."""
from __future__ import annotations

import sys
from pathlib import Path


def validate_deployment_config() -> bool:
    print("=== NaijaBoost AI Cloud Deployment Configuration Check ===")
    errors: list[str] = []

    # 1. Validate Dockerfile
    dockerfile_path = Path("Dockerfile")
    if not dockerfile_path.exists():
        errors.append("Dockerfile not found in root workspace.")
    else:
        df_content = dockerfile_path.read_text(encoding="utf-8")
        if "python:3.12-slim" not in df_content:
            errors.append("Dockerfile must use 'python:3.12-slim' base image.")
        if "EXPOSE 8080" not in df_content:
            errors.append("Dockerfile must expose port 8080 ('EXPOSE 8080').")
        if "uvicorn" not in df_content or "main:app" not in df_content or "--port" not in df_content or "8080" not in df_content:
            errors.append("Dockerfile must configure uvicorn entrypoint targeting main:app on port 8080.")
        if "requirements.txt" not in df_content:
            errors.append("Dockerfile must install dependencies from requirements.txt.")
        print("✅ Dockerfile validation passed.")

    # 2. Validate .dockerignore
    dockerignore_path = Path(".dockerignore")
    if not dockerignore_path.exists():
        errors.append(".dockerignore not found in root workspace.")
    else:
        di_content = dockerignore_path.read_text(encoding="utf-8")
        required_ignores = [".venv", ".git", "__pycache__", ".pytest_cache"]
        for req in required_ignores:
            if req not in di_content:
                errors.append(f".dockerignore must exclude '{req}'.")
        print("✅ .dockerignore validation passed.")

    # 3. Validate cloudbuild.yaml
    cloudbuild_path = Path("cloudbuild.yaml")
    if not cloudbuild_path.exists():
        errors.append("cloudbuild.yaml not found in root workspace.")
    else:
        cb_content = cloudbuild_path.read_text(encoding="utf-8")
        if "gcr.io/cloud-builders/docker" not in cb_content:
            errors.append("cloudbuild.yaml must use 'gcr.io/cloud-builders/docker' for build and push.")
        if "gcr.io/$PROJECT_ID/naijaboost-ai" not in cb_content:
            errors.append("cloudbuild.yaml must target image 'gcr.io/$PROJECT_ID/naijaboost-ai'.")
        if "gcr.io/cloud-builders/gcloud" not in cb_content or "run" not in cb_content or "deploy" not in cb_content:
            errors.append("cloudbuild.yaml must configure gcloud run deploy step.")
        if "europe-west1" not in cb_content:
            errors.append("cloudbuild.yaml must target Cloud Run region 'europe-west1'.")
        if "--platform" not in cb_content or "managed" not in cb_content:
            errors.append("cloudbuild.yaml must set platform 'managed'.")
        if "--allow-unauthenticated" not in cb_content:
            errors.append("cloudbuild.yaml must include '--allow-unauthenticated' flag.")
        print("✅ cloudbuild.yaml validation passed.")

    if errors:
        print("\n❌ Deployment Validation Errors:")
        for err in errors:
            print(f"  - {err}")
        return False

    print("\n🚀 All Google Cloud Run CI/CD deployment standards satisfied.")
    return True


if __name__ == "__main__":
    success = validate_deployment_config()
    sys.exit(0 if success else 1)
