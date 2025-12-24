import pandas as pd
import glob, os, json

#METRIC_DIR = "outputs/forecasting/metrics"
#metrics = []
#for path in glob.glob(os.path.join(METRIC_DIR, "*_metrics.json")):
#    with open(path) as f:
#        data = json.load(f)
#        data["feature"] = os.path.basename(path).replace("_metrics.json", "")
#        metrics.append(data)

#df = pd.DataFrame(metrics).sort_values("R2")
#print(df[["feature", "MAE", "RMSE", "R2"]])

import pandas as pd
df = pd.read_parquet("/Users/eeshanbhanap/Desktop/RFP/outputs/fetched/cleaned/VIX3M.parquet")
print(df.head())
print(df.columns)
print(df.index)