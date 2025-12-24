# Remove Claude from GitHub Contributors

## Problem
GitHub is showing "claude" as a contributor even though no commits in the git history have Claude as author/committer.

## Root Cause
GitHub caches contributor data aggressively. Once a user appears in the contributors list, GitHub doesn't always remove them immediately even after rewriting git history.

## Verification
Based on comprehensive checks:
- ✅ No commits have Claude as author
- ✅ No commits have Claude as committer
- ✅ No Co-Authored-By trailers found
- ✅ GitHub API shows only you as contributor
- ❌ BUT GitHub UI still shows Claude (cache issue)

## Solution: Force GitHub to Rebuild Contributors

### Option 1: Contact GitHub Support (Recommended)
GitHub support can manually clear the contributor cache:

1. Go to: https://support.github.com/contact
2. Select: "Account and Profile"
3. Message:
```
I need to remove an incorrect contributor from my repository's contributor graph.

Repository: https://github.com/EpbAiD/market-regime-forecaster
Issue: User "claude" appears in contributors list but has no commits in the repository
Evidence: GitHub API shows only me as contributor, but UI shows 2 contributors

Please manually clear the contributor cache for this repository.
```

### Option 2: Create an Empty Commit (May Help)
Sometimes an empty commit triggers GitHub to rebuild:

```bash
git commit --allow-empty -m "Trigger contributor cache rebuild"
git push origin main
```

### Option 3: Wait
GitHub's contributor cache can take up to **7 days** to refresh after major git history rewrites.

## What We've Tried
1. ✅ Removed all Claude mentions from code files
2. ✅ Cleaned git history (no Claude in commit authors/committers)
3. ✅ Verified GitHub API shows correct data
4. ❌ GitHub UI cache not refreshed yet

## Why This Happened
At some point, there was likely a commit with an email address that GitHub associated with the "claude" user account. Even after removing those commits, GitHub's UI cache persists.

## Next Steps
1. Try Option 2 (empty commit) first
2. If that doesn't work within 24 hours, contact GitHub Support (Option 1)
3. Or wait 7 days for automatic cache expiration (Option 3)

## Verification After Fix
Check: https://github.com/EpbAiD/market-regime-forecaster/graphs/contributors
Should show: Only EpbAiD (no claude)
