from common import coming_soon, page_header

page_header("Today", 1, "Play treasurer: take today's decisions and compare them with the autopilot.")
coming_soon(3, [
    "Cash position per currency with a 5-business-day look-ahead",
    "Decisions: invest or divest in MMFs, FX spot / forward / swap to flatten, roll or repay maturities",
    "IV buffer check against USD 50m, and the facility drawing it triggers",
    "Your decisions next to the autopilot's, with the cost difference",
])
