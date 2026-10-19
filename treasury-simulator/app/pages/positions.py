from common import coming_soon, page_header

page_header("Positions", 1, "Every open treasury position, valued daily.")
coming_soon(3, [
    "MMF holdings and accrued interest (paid on BD2 of the next month)",
    "IC loans (MMF + 50 bp) and IC deposits (MMF - 10 bp)",
    "Facility drawings: secured line and RCF, 1m / 3m, interest at maturity",
    "FX deal blotter with undiscounted MTM; maturity ladder",
])
