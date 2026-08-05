import pandas as pd
import random
from datetime import datetime
from utils.dates import is_month_end

def generate_movements(date: str, accounts_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    month_end = is_month_end(date_obj)
    counter = 1

    for _, acc in accounts_df.iterrows():
        acc_num = acc["account_number"]
        cur = acc["currency"]
        start_bal = acc["starting_balance"]

        # Interest
        if month_end:
            interest_amount = round(start_bal * random.uniform(0.0005, 0.002), 2)
            txn_id = f"TX{date.replace('-', '')}{counter:06d}"
            counter += 1
            rows.append({
                "date": date,
                "transaction_id": txn_id,
                "account_number": acc_num,
                "currency": cur,
                "type": "Interest",
                "category": "Income",
                "amount": interest_amount,
                "description": "Month-end interest"
            })

        # Charges
        if random.random() < 0.10:
            charge_amount = round(random.uniform(-2000, -200), 2)
            txn_id = f"TX{date.replace('-', '')}{counter:06d}"
            counter += 1
            rows.append({
                "date": date,
                "transaction_id": txn_id,
                "account_number": acc_num,
                "currency": cur,
                "type": "Charges",
                "category": "Fees",
                "amount": charge_amount,
                "description": "Bank charges"
            })

        # Deposit
        deposit_amount = round(random.uniform(1000, 50000), 2)
        txn_id = f"TX{date.replace('-', '')}{counter:06d}"
        counter += 1
        rows.append({
            "date": date,
            "transaction_id": txn_id,
            "account_number": acc_num,
            "currency": cur,
            "type": "Deposit",
            "category": "Transactions",
            "amount": deposit_amount,
            "description": "Deposit movement"
        })

        # Withdraw
        withdraw_amount = round(random.uniform(-50000, -1000), 2)
        txn_id = f"TX{date.replace('-', '')}{counter:06d}"
        counter += 1
        rows.append({
            "date": date,
            "transaction_id": txn_id,
            "account_number": acc_num,
            "currency": cur,
            "type": "Withdraw",
            "category": "Transactions",
            "amount": withdraw_amount,
            "description": "Withdraw movement"
        })

    return pd.DataFrame(rows)
