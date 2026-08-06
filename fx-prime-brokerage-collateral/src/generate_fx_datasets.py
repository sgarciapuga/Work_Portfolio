import argparse
import os
from pathlib import Path

from generate_limits import generate_limits
from generate_mtm_for_portfolio import generate_mtm_for_portfolio
from generate_mtm_report import generate_mtm_report
from generate_fx_portfolio import generate_fx_portfolio


# The generated FX datasets are intended to run up to yesterday COB by default.
def run_all(out_dir=None):
    base = Path(out_dir) if out_dir else Path(__file__).resolve().parent.parent / "data"
    limits_dir = base / "Limits"
    mtm_dir = base / "Mark-to-market"
    fx_portfolio_dir = base / "FX-portfolio"
    limits_dir.mkdir(parents=True, exist_ok=True)
    mtm_dir.mkdir(parents=True, exist_ok=True)
    fx_portfolio_dir.mkdir(parents=True, exist_ok=True)

    df_fx_portfolio = generate_fx_portfolio()
    df_mtm_portfolio = generate_mtm_for_portfolio(df_fx_portfolio)
    df_limits = generate_limits(portfolio_df=df_fx_portfolio)
    df_mtm_report = generate_mtm_report(portfolio_df=df_fx_portfolio, mtm_df=df_mtm_portfolio)

    limits_file = limits_dir / "limits.csv"
    mtm_portfolio_file = mtm_dir / "mark_to_market_portfolio.csv"
    mtm_report_file = mtm_dir / "mtm_report.csv"
    fx_portfolio_file = fx_portfolio_dir / "portfolio.csv"

    df_limits.to_csv(limits_file, index=False)
    if df_mtm_portfolio is not None and not df_mtm_portfolio.empty:
        df_mtm_portfolio.to_csv(mtm_portfolio_file, index=False)
    if df_mtm_report is not None:
        df_mtm_report.to_csv(mtm_report_file, index=False)
    df_fx_portfolio.to_csv(fx_portfolio_file, index=False)

    print(f"Wrote limits -> {limits_file}")
    print(f"Wrote mark-to-market portfolio -> {mtm_portfolio_file}")
    print(f"Wrote mark-to-market report -> {mtm_report_file}")
    print(f"Wrote FX portfolio -> {fx_portfolio_file}")


def main():
    p = argparse.ArgumentParser(description="Generate synthetic FX prime brokerage collateral datasets")
    p.add_argument("--out", help="Output base directory (defaults to repo fx-prime-brokerage-collateral/data)")
    args = p.parse_args()
    run_all(args.out)


if __name__ == "__main__":
    main()
