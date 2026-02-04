# MarketPulse: Multi-Agent Regime Intelligence Platform

[![Daily Forecast](https://github.com/EpbAiD/marketpulse/actions/workflows/daily-forecast.yml/badge.svg)](https://github.com/EpbAiD/marketpulse/actions/workflows/daily-forecast.yml)

Autonomous market regime forecasting system that predicts regime changes 10 trading days ahead using neural ensembles and LangGraph orchestration.

📚 **[Full Documentation](docs/MARKETPULSE_COMPLETE_TECHNICAL_DOCUMENTATION.md)** | [Architecture](docs/architecture.md) | [Usage Guide](docs/usage_guide.md)

---

## ⚡ Quick Start

```bash
# Daily automation (inference → log → screenshot → git push)
./daily_update.sh

# Manual inference
python run_daily_update.py

# View dashboard
streamlit run dashboard/app.py
```

---

## 🎯 What It Does

Forecasts market regimes (Bull, Bear, Transitional) 10 trading days in advance using 22 macroeconomic indicators:
- VIX volatility indices, treasury yields, credit spreads
- Equity indices (S&P 500, NASDAQ), commodities (Gold, Oil, Copper)
- Dollar strength (DXY, UUP)

**Architecture:**
- Neural ensemble (NBEATSx, NHITS, PatchTST) for feature forecasting
- Hidden Markov Models for regime clustering
- Random Forest classification (98.4% accuracy on 5,464 historical days)
- LangGraph multi-agent orchestration
- BigQuery data warehouse

**Use Case:** Portfolio managers get 10 trading-day advance warning for regime shifts, enabling proactive allocation adjustments.

---

## 📊 Performance

| Metric | Value |
|--------|-------|
| **Classification Accuracy** | 98.4% on 15 years of data |
| **Forecast Error (SMAPE)** | 3.38% average across features |
| **Regime Distribution** | Bull 22% / Bear 20% / Transitional 58% |
| **Daily Inference Time** | <50 seconds |
| **Training Time** | ~75-90 minutes (full pipeline) |
| **Auto-Retraining** | Intelligent model age detection |

---

## 🤖 Daily Automation

One command runs complete pipeline:

```bash
./daily_update.sh
```

**What happens:**
1. Forecasts 18 features × 10 trading days (ensemble predictions)
2. Engineers 294 features → selects 31 optimal
3. Predicts regimes using Random Forest
4. Filters to trading days only (excludes weekends/holidays)
5. Validates forecasts (SMAPE)
6. Logs predictions to `DAILY_PREDICTIONS.md`
7. Captures dashboard screenshot
8. Commits and pushes to GitHub

**Cron job setup (6 AM daily):**
```bash
0 6 * * * cd /path/to/RFP && ./daily_update.sh >> logs/daily_automation.log 2>&1
```

---

## 📊 Dashboard

Interactive Streamlit dashboard showing:
- Current regime + 10-day forecast
- Regime probabilities and confidence
- Markov transition matrices
- Regime-specific allocation strategies
- Historical performance by regime

![Dashboard Overview](assets/dashboard.png)

```bash
streamlit run dashboard/app.py
# Opens at http://localhost:8501
```

---

## 🏗️ System Architecture

### Multi-Agent Pipeline (LangGraph)

**Training Workflow:**
```
Data Fetch → Feature Engineering → Feature Selection → Clustering → Classification → Train Forecasters
```

**Inference Workflow (Daily):**
```
Forecast Raw Features → Engineer → Predict Regimes → Alert Detection → Validation → Monitoring
```

**Auto-Detection:** System checks model age and decides:
- Models < 30 days → Run INFERENCE (~40s)
- Models > 30 days → Run RETRAIN (full pipeline)

### Feature Engineering
- 294 engineered features from 22 raw indicators
- Rolling statistics, technical indicators, macro ratios
- PCA + mRMR selection → 31 optimal features

### Models
- **Forecasting**: NBEATSx, NHITS, PatchTST (ensemble per feature)
- **Clustering**: Hidden Markov Models (3 regimes)
- **Classification**: Random Forest (98.4% accuracy)

### Storage
- **Production**: BigQuery (10 tables, 155K rows)
- **Development**: Local parquet files
- Factory pattern: `storage = get_storage(use_bigquery=True)`

---

## 🔧 Key Technical Implementations

**1. NeuralForecast Bundle Loading**
Training saves models as `nf_bundle_v1/` directories. Inference loads complete bundles using `NeuralForecast.load()`.

**2. Ensemble Weight Conversion**
Converts weight lists `[0.098, 0.097, ...]` to dictionaries `{'nbeats': 0.369, 'nhits': 0.363, 'patchtst': 0.267}`.

**3. LangGraph State Management**
Converts numpy types to native Python (`int()`, `float()`, `str()`) for msgpack serialization.

---

## 💻 Tech Stack

| Category | Technologies |
|----------|-------------|
| **ML/Forecasting** | Python, PyTorch, NeuralForecast (NBEATSx, NHITS, PatchTST), scikit-learn |
| **Orchestration** | LangGraph (multi-agent state machine) |
| **Data Storage** | BigQuery, Pandas, Parquet |
| **Cloud Infrastructure** | GitHub Actions, Google Cloud Run |
| **Visualization** | Streamlit, Plotly |
| **Data Sources** | Yahoo Finance, FRED (Federal Reserve) |

---

## 📁 Repository Structure

```
├── data_agent/              # Data fetching, engineering, feature selection
│   └── storage/             # BigQuery and local storage backends
├── clustering_agent/        # HMM regime clustering (3 states)
├── classification_agent/    # Random Forest regime classifier
├── forecasting_agent/       # Neural ensemble forecasters (22 models)
├── orchestrator/            # LangGraph workflows and state management
│   └── intelligent_model_checker.py  # Auto-detect stale models
├── cloud_run/               # GPU training infrastructure
├── dashboard/               # Streamlit visualization
├── configs/                 # YAML configurations
│   ├── features_config.yaml # Forecast horizons and ensembles
│   └── bigquery_config.yaml # Data warehouse setup
├── .github/workflows/       # CI/CD automation
│   └── daily-forecast.yml   # Scheduled daily predictions
└── docs/                    # Technical documentation
```

---

## 📊 Sample Results

**Allocation Framework (5,464 historical days):**

| Regime | Frequency | Sample Strategy |
|--------|-----------|-----------------|
| Bull Market | 22% | 70% Equity / 20% Tech / 10% Cash |
| Bear Market | 20% | 30% Equity / 70% Bonds |
| Transitional | 58% | 60% Equity / 40% Bonds |

Run `python backtest_strategy.py` for regime distribution analysis.

---

## 🏗️ Hybrid Cloud Architecture

The system uses a hybrid architecture for optimal resource utilization:

| Component | Platform | Purpose |
|-----------|----------|---------|
| Data Fetching | GitHub Actions | API calls, lightweight processing |
| Feature Engineering | GitHub Actions | Pandas transformations |
| Model Training | Google Cloud Run | GPU-accelerated neural network training |
| Inference | GitHub Actions | Load pre-trained models, fast prediction |
| Monitoring | GitHub Actions | Validation, alerts, performance tracking |

**Daily Schedule:** Runs automatically at 6 AM EST via GitHub Actions.

---

## 👤 Author

**Eeshan Bhanap**

---

## 📄 License

This project is for educational and research purposes.

---

## 🙏 Acknowledgments

- Market regime research inspired by Bridgewater Associates and AQR Capital
- Data sources: Yahoo Finance, FRED (Federal Reserve Economic Data)
- ML frameworks: NeuralForecast (Nixtla), LangGraph (LangChain)
