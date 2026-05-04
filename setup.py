from setuptools import setup, find_packages

setup(
    name="cc-config",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "cc-config=cc_config.cli:main",
        ],
    },
)
