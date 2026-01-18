#!/bin/bash
# Commit WORKFLOW_LOG.md to GitHub for real-time monitoring
# This runs in the background and periodically pushes the log file

if [ -f "WORKFLOW_LOG.md" ]; then
    git config --local user.email "github-actions[bot]@users.noreply.github.com"
    git config --local user.name "GitHub Actions Bot"

    git add WORKFLOW_LOG.md

    if ! git diff --staged --quiet; then
        git commit -m "📝 Update workflow log [$(date +'%H:%M:%S')]" --no-verify
        git pull --rebase origin main --no-verify || true  # Handle conflicts
        git push origin main --no-verify || echo "Push failed, will retry"
        echo "✓ Log committed at $(date +'%H:%M:%S')"
    fi
fi
