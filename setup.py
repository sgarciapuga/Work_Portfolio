from setuptools import setup, find_packages

setup(
    name="work_portfolio",
    version="0.0.0",
    description="Work Portfolio root package",
    package_dir={"": "treasury-cashflow-simulation/src"},
    packages=find_packages(where="treasury-cashflow-simulation/src"),
    include_package_data=True,
)
