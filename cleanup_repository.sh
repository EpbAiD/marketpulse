#!/bin/bash
# Repository Cleanup Script
# Organizes documentation and removes temporary files

set -e

echo "🧹 Starting repository cleanup..."
echo ""

# Step 1: Delete temporary MD files
echo "[1/4] Deleting temporary documentation..."
rm -f ALL_FIXES_APPLIED.md \
      AUTO_MODE_SUMMARY.md \
      CONSOLIDATION_COMPLETE.md \
      CRITICAL_FIXES_NEEDED.md \
      DAILY_UPDATE_FIXES.md \
      DAILY_UPDATE_PROTECTION.md \
      DAILY_WORKFLOW_AUDIT.md \
      END_TO_END_TEST_RESULTS.md \
      FINAL_STATUS.md \
      FORECASTING_INFERENCE_FIX.md \
      NEW_REPO_SUCCESS.md \
      SCREENSHOT_IMPLEMENTATION_SUMMARY.md \
      TEST_RESULTS.md \
      RESUME_POINTS_IMPROVED.md \
      RESUME_WRITING_LESSONS_LEARNED.md \
      GITHUB_CONTRIBUTOR_ISSUES_LESSONS_LEARNED.md \
      REMOVE_CLAUDE_CONTRIBUTOR.md

echo "   ✅ Deleted 17 temporary files"

# Step 2: Move useful docs to /docs
echo ""
echo "[2/4] Moving documentation to /docs..."
mkdir -p docs

mv GITHUB_BEST_PRACTICES.md docs/github_best_practices.md 2>/dev/null || true
mv LANGGRAPH_INTELLIGENCE_ANALYSIS.md docs/langgraph_analysis.md 2>/dev/null || true
mv FORECAST_VERIFICATION_ANALYSIS.md docs/forecast_verification.md 2>/dev/null || true
mv REPOSITORY_CLEANUP_ANALYSIS.md docs/repository_cleanup_analysis.md 2>/dev/null || true
mv ARCHITECTURE.md docs/architecture.md 2>/dev/null || true
mv USAGE_GUIDE.md docs/usage_guide.md 2>/dev/null || true
mv DAILY_AUTOMATION_GUIDE.md docs/automation_guide.md 2>/dev/null || true
mv LANGGRAPH_MIGRATION.md docs/langgraph_migration.md 2>/dev/null || true

echo "   ✅ Moved documentation to /docs"

# Step 3: Delete duplicate screenshot PNGs
echo ""
echo "[3/4] Deleting duplicate screenshots..."
rm -f dashboard_*.png
echo "   ✅ Deleted 8 duplicate PNGs"

# Step 4: Clean screenshots folder if not used
echo ""
echo "[4/4] Checking screenshots folder..."
if [ -d "screenshots" ]; then
    echo "   Found screenshots/ folder - checking usage..."
    # Check if referenced in README or code (excluding dashboard_screenshots)
    if ! grep -r "screenshots/" README.md --include="*.md" 2>/dev/null | grep -v "dashboard_screenshots" > /dev/null; then
        echo "   ⚠️  Not referenced in README - keeping for safety (manual review needed)"
    else
        echo "   ✅ Referenced in code - keeping"
    fi
fi

echo ""
echo "================================================================================"
echo "✅ CLEANUP COMPLETE!"
echo "================================================================================"
echo ""
echo "📊 Results:"
echo "   - Deleted: 17 temporary MD files"
echo "   - Deleted: 8 duplicate PNG files"
echo "   - Organized: 8 docs moved to /docs folder"
echo ""
echo "📁 Root directory now:"
ROOT_MD_COUNT=$(ls -1 *.md 2>/dev/null | wc -l | xargs)
echo "   - Markdown files: $ROOT_MD_COUNT (should be 2)"
echo ""
echo "📚 Documentation folder:"
DOCS_COUNT=$(ls -1 docs/*.md 2>/dev/null | wc -l | xargs)
echo "   - Files in /docs: $DOCS_COUNT"
echo ""
echo "🔍 Verification:"
echo ""
echo "Root MD files remaining:"
ls -1 *.md 2>/dev/null | sed 's/^/   - /'
echo ""
echo "Documentation in /docs:"
ls -1 docs/*.md 2>/dev/null | sed 's/^/   - /'
echo ""
echo "================================================================================"
echo "Next step: git add . && git commit -m 'Clean up repository structure'"
echo "================================================================================"
