import setuptools
from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="pridepy",
    version="0.0.5",
    author="PRIDE Team",
    author_email="pride-support@ebi.ac.uk",
    description="Python Client library for PRIDE Rest API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/PRIDE-Archive/pridepy",
    keywords="PRIDE python client REST API",
    packages=setuptools.find_packages(),
    py_modules=["pridepy"],
    install_requires=[
        "requests",
        "ratelimit",
        "click",
        "pytest",
        "setuptools",
        "plotly",
        "tqdm",
        "boto3",
        "botocore",
        "httpx",
    ],
    include_package_data=True,
    package_data={
        "": ["*.txt", "*.md"],  # Include text or markdown files from any package
        "aspera": ["**/*"],  # Include all files from the aspera directory
    },
    entry_points="""
        [console_scripts]
        pridepy=pridepy:main
    """,
)
