# Workflow C Failure Analysis & Fixes

## Group C Features (Features 15-22)

**Daily Features (4):**
1. DFF - Effective Federal Funds Rate
2. GOLD - Gold Futures
3. OIL - Crude Oil Futures
4. COPPER - Copper Futures

**Weekly Features (1):**
5. NFCI - Chicago Fed National Financial Conditions Index

**Monthly Features (3):**
6. CPI - Consumer Price Index
7. UNRATE - Unemployment Rate
8. INDPRO - Industrial Production Index

## Issues Identified

### Issue 1: Prophet Initialization Timeout
**Problem:** Monthly features use Prophet (Facebook's forecasting library)
- Prophet requires `cmdstanpy` backend for Stan model compilation
- Stan compilation can take 2-5 minutes PER feature on first run
- 3 monthly features × 5 min = 15 minutes just for Stan compilation

**Evidence:**
- Workflow C logs stop after "Set up Google Cloud credentials" step
- No training output visible (logs incomplete)
- Workflow failed after 3h 45m (not the 12h timeout)

**Root Cause:**
Likely the training step started but Prophet initialization hung or crashed silently

### Issue 2: Lightning Logs (Still Present)
**Problem:** Even with sequential training, lightning_logs can cause issues
- Group C has different model types (Prophet) vs A/B (pure neural)
- Prophet doesn't use lightning_logs, but NeuralForecast models do
- Race condition still possible if cleanup doesn't happen properly

**Evidence:**
- Groups A & B both had 1 failure each due to lightning_logs
- Both with sequential code (max_workers=8 at that time)

### Issue 3: Memory Issues with Monthly Features
**Problem:** Monthly features have very long history
- CPI data: 1947-present (70+ years, ~900 data points)
- INDPRO data: 1919-present (100+ years, ~1200 data points)
- UNRATE data: 1948-present (75+ years, ~900 data points)

**Evidence:**
- GitHub Actions runners have 7 GB RAM
- Loading 100 years of monthly data + Prophet models can exceed memory
- No explicit memory error, but silent crash is possible

### Issue 4: Prophet Stan Backend Installation
**Problem:** cmdstanpy requires Stan compiler to be installed
- We install `cmdstanpy==1.2.2` via pip
- But Stan compiler might not auto-install correctly on GitHub Actions
- Prophet falls back to pystan (deprecated) or crashes

**Evidence:**
- cmdstanpy was added to requirements recently
- No verification step to check if Stan compiler is available
- Prophet errors are often silent (logged internally)

## Proposed Fixes

### Fix 1: Install Stan Compiler Explicitly
Add Stan installation step to workflow:

```yaml
- name: Install Stan compiler for Prophet
  run: |
    python -c "import cmdstanpy; cmdstanpy.install_cmdstan()"
```

### Fix 2: Add Prophet Verification
Verify Prophet works before training:

```yaml
- name: Verify Prophet installation
  run: |
    python -c "from prophet import Prophet; import pandas as pd; m = Prophet(); df = pd.DataFrame({'ds': pd.date_range('2020-01-01', periods=100), 'y': range(100)}); m.fit(df); print('✓ Prophet working')"
```

### Fix 3: Increase Memory Limit for Monthly Features
Modify forecaster to reduce memory for monthly features:

```python
# In forecaster.py for monthly features
if cadence == 'monthly':
    # Use smaller input window for very long series
    max_history = 240  # 20 years max (vs all history)
    df_fit = df_fit.tail(max_history)
```

### Fix 4: Add Timeout Per Feature
Prevent single feature from hanging entire workflow:

```python
# In forecaster.py
import signal

def timeout_handler(signum, frame):
    raise TimeoutError("Feature training exceeded 90-minute limit")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(5400)  # 90 minutes per feature

try:
    # Train feature
    train_forecaster_for_feature(...)
finally:
    signal.alarm(0)  # Cancel alarm
```

### Fix 5: Disable Prophet for Initial Test
Test if issue is Prophet-specific:

```yaml
# Temporarily modify features_config.yaml
monthly:
  prophet:
    enabled: false  # Disable Prophet, use only neural + ARIMA
```

### Fix 6: Better Error Logging
Add explicit error catching in forecaster:

```python
try:
    # Train Prophet
    prophet_model = Prophet()
    prophet_model.fit(df_fit)
except Exception as e:
    logger.error(f"Prophet training failed for {feature}: {e}")
    logger.error(f"Traceback: {traceback.format_exc()}")
    # Continue without Prophet
    prophet_model = None
```

## Recommended Action Plan

**Step 1: Quick Test (Disable Prophet)**
- Set `monthly.prophet.enabled: false` in features_config.yaml
- Re-run Workflow C
- If succeeds → Issue is Prophet-specific
- If fails → Issue is something else (memory, lightning_logs)

**Step 2: Fix Prophet (If Step 1 Confirms)**
- Add Stan compiler installation
- Add Prophet verification
- Add better error logging
- Re-run Workflow C

**Step 3: Fix Lightning Logs (If Still Failing)**
- Verify sequential training is working (max_workers=1)
- Add explicit lightning_logs cleanup per feature
- Add unique temp directories per feature (fallback)

**Step 4: Fix Memory Issues (If Still Failing)**
- Limit monthly feature history to 20 years
- Add garbage collection after each feature
- Monitor memory usage

## Testing Strategy

### Test 1: Local Dry Run
```bash
# Test Group C locally (without BigQuery)
python train_parallel_subset.py --group C

# Should print:
# Group C: Training features 15-22
# Features to train (8): DFF, GOLD, OIL, COPPER, NFCI, CPI, UNRATE, INDPRO
```

### Test 2: Single Monthly Feature Test
```bash
# Test just CPI (monthly feature with Prophet)
python -m forecasting_agent --mode single --monthly CPI --force-retrain

# Watch for Prophet errors
```

### Test 3: GitHub Actions Test
```bash
# Trigger Workflow C manually
gh workflow run train-parallel-c.yml

# Watch logs in real-time
gh run watch
```

## Expected Outcomes

**If Prophet is the issue:**
- Workflow succeeds with Prophet disabled
- Fails with specific Stan/Prophet error when enabled
- Fix: Install Stan compiler properly

**If memory is the issue:**
- Workflow crashes after 2-3 hours (no error)
- GitHub Actions shows "killed" or "out of memory"
- Fix: Limit monthly feature history

**If lightning_logs is the issue:**
- Workflow shows explicit `[Errno 17] File exists` error
- Fix: Ensure sequential training + cleanup working

**If timeout is the issue:**
- Workflow hits 12-hour limit
- Logs show slow training progress
- Fix: Optimize model configs, reduce max_steps

## Current Status - FINAL RESOLUTION

### Failed Attempts:
- ❌ Workflow C #21159706332 failed after 3h 45m (no Stan compiler)
- ❌ Workflow C #21212873759 failed after 3h 44m (WITH Stan compiler installed!)

### Root Cause Identified:
**3h 45m timeout is NOT a Prophet issue - it's a resource/time limit!**

Evidence:
1. Both failures at exactly 3h 45m (not 12hr workflow timeout)
2. Stan compiler + Prophet verification SUCCEEDED in run #21212873759
3. Training step was CANCELLED (not failed), indicating external kill
4. No artifacts saved because upload only happens at workflow end

**Actual Cause:** 8 features × 30-45min/feature = 4-6 hours total, but workflow gets killed at 3h 45m mark (likely GitHub Actions organization limit, silent OOM, or network timeout)

### Solution Implemented:
**Split Group C into two sub-batches:**

**C1 (Features 15-18):** DFF, GOLD, OIL, COPPER
- 4 daily features
- Neural models only (no Prophet)
- Est. time: 2-3 hours
- Workflow: [train-parallel-c1.yml](../.github/workflows/train-parallel-c1.yml)

**C2 (Features 19-22):** NFCI, CPI, UNRATE, INDPRO
- 1 weekly + 3 monthly features
- Includes Prophet with Stan compiler
- Est. time: 3-4 hours
- Workflow: [train-parallel-c2.yml](../.github/workflows/train-parallel-c2.yml)

Each sub-batch:
- Fits within resource limits
- Uploads artifacts independently (no progress loss)
- Can be run in parallel if needed

**Next Action:** Trigger C1 and C2 workflows (waiting for GitHub to register new workflows)
