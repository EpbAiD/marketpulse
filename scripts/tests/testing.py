#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Safe Parallelism Test for macOS (2 Workers)
-------------------------------------------
✅ Confirms that CPU processes run truly in parallel
✅ Avoids fork() + MPS crash by importing torch inside each process
"""

import os
import time
import platform
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed

print("===========================================================")
print("🧠 Safe Parallel Training Test (2 Workers, CPU, macOS-safe)")
print("===========================================================")

# Do NOT set fork — keep default spawn
if platform.system() == "Darwin":
    print("⚙️ Using safe 'spawn' start method for macOS (prevents MPS crash)")

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"


def train_worker(worker_id):
    import torch
    from torch import nn
    import pytorch_lightning as pl

    start_time = time.time()
    print(f"🚀 [Worker {worker_id}] Starting training...")

    # --- define model inside worker ---
    class TinyRegressor(pl.LightningModule):
        def __init__(self):
            super().__init__()
            self.model = nn.Linear(1, 1)

        def forward(self, x):
            return self.model(x)

        def training_step(self, batch, batch_idx):
            x, y = batch
            y_hat = self(x)
            loss = nn.functional.mse_loss(y_hat, y)
            self.log("train_loss", loss)
            return loss

        def configure_optimizers(self):
            return torch.optim.Adam(self.parameters(), lr=0.01)

    # --- data ---
    X = torch.randn(100, 1)
    y = 2 * X + 0.1 * torch.randn(100, 1)
    dataset = torch.utils.data.TensorDataset(X, y)
    loader = torch.utils.data.DataLoader(dataset, batch_size=16, shuffle=True)

    # --- train ---
    trainer = pl.Trainer(
        max_epochs=5,
        accelerator="cpu",
        enable_checkpointing=False,
        logger=False,
        enable_model_summary=False,
    )
    model = TinyRegressor()
    trainer.fit(model, loader)

    elapsed = time.time() - start_time
    print(f"✅ [Worker {worker_id}] Done in {elapsed:.2f}s")
    return elapsed


if __name__ == "__main__":
    start_all = time.time()
    with ProcessPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(train_worker, i) for i in range(2)]
        for fut in as_completed(futures):
            fut.result()

    total = time.time() - start_all
    print(f"🕒 Total elapsed time: {total:.2f}s")
    print("✅ Test complete (should be ~half the sequential runtime).")