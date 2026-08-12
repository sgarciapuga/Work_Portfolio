import os
from datetime import date
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

INITIAL_COLLATERAL = 1_000_000.0
BUFFER = 500_000.0
MOVE_INCREMENT = 10_000.0
MIN_MOVE = 50_000.0


def get_business_days(start_date, end_date):
    """Return US Federal holiday-aware business dates between two endpoints."""
    business_day = CustomBusinessDay(calendar=USFederalHolidayCalendar())
    return pd.date_range(start=start_date, end=end_date, freq=business_day)


def generate_mtm_report(portfolio_df=None, mtm_df=None, end_date=None, out_path=None):
    """Generate a daily MTM collateral report.

    The report outputs the following columns:
    - report_date
    - initial_margin: negative values indicate IM payable by us
    - variation_margin: positive values are favourable P&L; negative values are payable by us
    - collateral_required: negative values indicate total collateral required from us
    - collateral_posted: collateral posted today
    - excess_deficit: positive means excess collateral, negative means deficit

    Sign convention: initial margin is always negative because it is posted to the
    broker. Variation margin keeps the MTM/P&L sign: positive P&L reduces the
    collateral requirement and negative P&L increases it.

    Returns one row per business date and writes the result to ``mtm_report.csv``.
    """
    # load data if not provided
    base_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    if portfolio_df is None:
        p = os.path.join(base_dir, "FX-portfolio", "portfolio.csv")
        portfolio_df = pd.read_csv(p)
    if mtm_df is None:
        m = os.path.join(base_dir, "Mark-to-market", "mark_to_market_portfolio.csv")
        mtm_df = pd.read_csv(m)

    if end_date is None:
        business_day = CustomBusinessDay(calendar=USFederalHolidayCalendar())
        previous = pd.date_range(end=date.today(), periods=2, freq=business_day)
        end_date = previous[-2].date().isoformat()

    # business days up to previous business day
    business_days = get_business_days(portfolio_df["trade_date"].min(), end_date)
    last_day = business_days[-1]

    # ensure date types
    portfolio_df["report_date"] = pd.to_datetime(portfolio_df["report_date"])
    mtm_df["report_date"] = pd.to_datetime(mtm_df["report_date"]) if not mtm_df.empty else mtm_df

    report_dates = pd.date_range(start=business_days[0], end=last_day, freq=CustomBusinessDay(calendar=USFederalHolidayCalendar()))

    # aggregate exposure per report_date (sum of trade_size_usd across active legs)
    exposure = portfolio_df.groupby("report_date", as_index=False)["trade_size_usd"].sum()
    exposure_map = {row["report_date"].date().isoformat(): float(row["trade_size_usd"]) for _, row in exposure.iterrows()}

    # aggregate VM per report_date using mtm_df pnl
    if mtm_df is None or mtm_df.empty:
        vm_map = {}
    else:
        vm = mtm_df.groupby("report_date", as_index=False)["pnl"].sum()
        vm_map = {row["report_date"].date().isoformat(): float(row["pnl"]) for _, row in vm.iterrows()}

    rows = []
    collateral_current = 0.0
    collateral_next = 0.0

    for rd in report_dates:
        rd_str = rd.date().isoformat()
        # raw (internal) values used for collateral logic
        im_raw = 0.05 * exposure_map.get(rd_str, 0.0)
        vm_raw = vm_map.get(rd_str, 0.0)

        # collateral displayed is collateral_current (posted amount shown today)
        collateral_display = collateral_current
        # Positive P&L offsets the initial-margin obligation; negative P&L adds to it.
        total_exposure = im_raw - vm_raw
        # excess_deficit: positive => excess (collateral > exposure), negative => deficit
        # (positive is good, negative is bad)
        excess_deficit = collateral_display - total_exposure

        # Initial margin is an amount posted to the broker; VM keeps the P&L sign.
        initial_margin = round(-im_raw, 2)
        variation_margin = round(vm_raw, 2)
        rows.append({
            "report_date": rd_str,
            "initial_margin": initial_margin,
            "variation_margin": variation_margin,
            "collateral_required": round(initial_margin + variation_margin, 2),
            "collateral_posted": round(collateral_display, 2),
            "excess_deficit": round(excess_deficit, 2),
        })

        # decide collateral movement for next day (1-day lag)
        # Movements are in `MOVE_INCREMENT` chunks and at least `MIN_MOVE`.
        # Posting rule: if deficit -> post enough tomorrow to reach (total_exposure + BUFFER),
        # rounded up to MOVE_INCREMENT and at least MIN_MOVE.
        # Recall rule: if surplus above BUFFER by at least MIN_MOVE -> recall rounded down to MOVE_INCREMENT,
        # never reducing posted collateral below BUFFER.
        if excess_deficit < 0:
            # amount needed to reach target (exposure + buffer)
            target = total_exposure + BUFFER
            delta = target - collateral_display
            if delta <= 0:
                collateral_next = collateral_display
            else:
                # round up to next MOVE_INCREMENT
                moves = np.ceil(delta / MOVE_INCREMENT) * MOVE_INCREMENT
                move_amount = max(moves, MIN_MOVE)
                collateral_next = collateral_display + float(move_amount)
        else:
            # surplus = collateral - exposure
            surplus = collateral_display - total_exposure
            recall_possible = surplus - BUFFER
            if recall_possible >= MIN_MOVE:
                # round down recall to MOVE_INCREMENT
                recall = np.floor(recall_possible / MOVE_INCREMENT) * MOVE_INCREMENT
                recall_amount = max(recall, MIN_MOVE)
                new_posted = collateral_display - float(recall_amount)
                collateral_next = max(new_posted, BUFFER)
            else:
                collateral_next = collateral_display

        collateral_current = collateral_next

    df = pd.DataFrame(rows)
    out_dir = out_path or os.path.join(base_dir, "Mark-to-market")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "mtm_report.csv")
    try:
        df.to_csv(out_file, index=False)
        print(f"Wrote {len(df)} rows to {out_file}")
    except PermissionError:
        fallback = out_file + ".tmp"
        df.to_csv(fallback, index=False)
        print(f"Permission denied writing {out_file}; wrote fallback file {fallback}")
    return df


if __name__ == "__main__":
    generate_mtm_report()
