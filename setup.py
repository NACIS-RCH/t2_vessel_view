## import required functions
## run this in current dir using "pip install -e ."


from setuptools import setup, find_packages

## call setup function

setup(
    name="t2vesselview",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "SimpleITK>=2.2.0",
        "nibabel>=4.0.0",
        "pydicom>=2.4.0",
        "numpy>=1.21.0",
        "matplotlib>=3.5.0",
        "pyvista>=0.34.0",
        "tqdm>=4.65.0",
        "pyyaml>=6.0",
        "python-pptx>=0.6.21",
        "ants>=0.0.1",
        "fsl>=0.0.1",
    ],
    python_requires=">=3.8",
    author="Bonnie Alexander",
    author_email="11053443+BonnieAlexander@users.noreply.github.com",
    description="Brain MRI processing pipeline for T2 vessel visualization",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/NACIS-RCH/t2_vessel_view",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
