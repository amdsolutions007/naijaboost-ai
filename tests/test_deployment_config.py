"""Tests for Phase 5 Cloud CI/CD Pipeline and Google Cloud Run Containerization Configuration."""
from __future__ import annotations

from pathlib import Path
import pytest
import yaml

from deploy_check import validate_deployment_config


def test_dockerfile_compliance() -> None:
    """Verify Dockerfile base image, port binding, dependencies, and Uvicorn entrypoint."""
    dockerfile = Path("Dockerfile")
    assert dockerfile.exists(), "Dockerfile missing"

    content = dockerfile.read_text(encoding="utf-8")
    assert "python:3.12-slim" in content, "Must use python:3.12-slim base image"
    assert "EXPOSE 8080" in content, "Must expose Cloud Run default port 8080"
    assert "requirements.txt" in content, "Must copy and install requirements.txt"
    assert "uvicorn" in content and "main:app" in content and "8080" in content, "Must execute uvicorn main:app on port 8080"
    assert "useradd" in content and "USER naijaboost" in content, "Must enforce non-root user execution"


def test_dockerignore_compliance() -> None:
    """Verify .dockerignore excludes virtual environments, git directories, caches, and test DBs."""
    dockerignore = Path(".dockerignore")
    assert dockerignore.exists(), ".dockerignore missing"

    content = dockerignore.read_text(encoding="utf-8")
    for req_ignore in [".venv", ".git", "__pycache__", ".pytest_cache", "*.db-journal"]:
        assert req_ignore in content, f".dockerignore must exclude '{req_ignore}'"


def test_cloudbuild_yaml_structure_and_parameters() -> None:
    """Verify cloudbuild.yaml workflow steps, Google Cloud Registry naming, and Cloud Run deploy flags."""
    cloudbuild = Path("cloudbuild.yaml")
    assert cloudbuild.exists(), "cloudbuild.yaml missing"

    content = cloudbuild.read_text(encoding="utf-8")
    assert "gcr.io/cloud-builders/docker" in content, "Must include docker builder step"
    assert "gcr.io/$PROJECT_ID/naijaboost-ai" in content, "Must reference correct GCR image path"
    assert "gcr.io/cloud-builders/gcloud" in content, "Must include gcloud deploy builder step"
    assert "europe-west1" in content, "Must deploy to region europe-west1"
    assert "managed" in content, "Must specify platform managed"
    assert "--allow-unauthenticated" in content, "Must allow unauthenticated invocations"

    # Verify YAML parsing validity
    parsed_yaml = yaml.safe_load(content)
    assert "steps" in parsed_yaml, "cloudbuild.yaml must define build steps"
    assert len(parsed_yaml["steps"]) == 3, "Must contain exactly 3 steps (Build, Push, Deploy)"
    assert parsed_yaml["steps"][2]["args"][1] == "deploy", "Step 3 must execute gcloud run deploy"


def test_deploy_check_script_execution() -> None:
    """Verify that deploy_check.py validation function executes successfully with true return value."""
    assert validate_deployment_config() is True, "deploy_check.py validation failed"
