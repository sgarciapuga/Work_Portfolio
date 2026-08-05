import pandas as pd

def sweep_cash(daily_balances: pd.DataFrame):
    sweeps = []

    for currency in daily_balances["currency"].unique():
        df = daily_balances[daily_balances["currency"] == currency].copy()

        deficits = df[df["closing_balance"] < 0].sort_values("closing_balance")
        surpluses = df[df["closing_balance"] > 0].sort_values("closing_balance", ascending=False)

        for _, deficit_row in deficits.iterrows():
            deficit_acc = deficit_row["account_number"]
            deficit_amt = abs(deficit_row["closing_balance"])

            for _, surplus_row in surpluses.iterrows():
                if deficit_amt == 0:
                    break

                surplus_acc = surplus_row["account_number"]
                surplus_amt = surplus_row["closing_balance"]

                if surplus_amt <= 0:
                    continue

                transfer_amt = min(surplus_amt, deficit_amt)

                sweeps.append({
                    "date": deficit_row["date"],
                    "transaction_id": f"SWEEP-{deficit_acc}-{surplus_acc}",
                    "account_number": deficit_acc,
                    "currency": currency,
                    "type": "Internal Sweep",
                    "category": "Treasury",
                    "amount": transfer_amt,
                    "description": f"Sweep from {surplus_acc}"
                })

                sweeps.append({
                    "date": surplus_row["date"],
                    "transaction_id": f"SWEEP-{surplus_acc}-{deficit_acc}",
                    "account_number": surplus_acc,
                    "currency": currency,
                    "type": "Internal Sweep",
                    "category": "Treasury",
                    "amount": -transfer_amt,
                    "description": f"Sweep to {deficit_acc}"
                })

                df.loc[df["account_number"] == deficit_acc, "closing_balance"] += transfer_amt
                df.loc[df["account_number"] == surplus_acc, "closing_balance"] -= transfer_amt

                deficit_amt -= transfer_amt

        daily_balances.loc[daily_balances["currency"] == currency, "closing_balance"] = df["closing_balance"]

    return daily_balances, pd.DataFrame(sweeps)