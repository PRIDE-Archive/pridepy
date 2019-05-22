from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='pride-py',
    version='0.0.1',
    author="Suresh Hewapathirana",
    author_email="hewapathirana@ebi.ac.uk",
    description="Python Client library for PRIDE Rest API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/PRIDE-Archive/pride-py",
    keywords="PRIDE python client REST API",
    packages=setuptools.find_packages(),
    py_modules=['pride-py'],
    install_requires=[
        'Click',
        'plotly',
        'requests',
        'ratelimit'
    ],
    entry_points='''
        [console_scripts]
        pridepy=pridepy:main
    ''',
)