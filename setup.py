## import required functions
## run this in current dir using "pip install -e ."


from setuptools import setup, find_packages

## call setup function

setup(
    author="Bonnie Alexander",
    description="A tool for generating Vessel Maps from T2-weighted MRI",
    name="t2vesselviewcode",
    version="0.1.0",
    packages=find_packages(include=["t2vesselviewcode", "t2vesselviewcode.*"]),
)
