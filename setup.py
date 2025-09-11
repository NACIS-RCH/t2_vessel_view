## import required functions
## run this in current dir using "pip install -e ."


from setuptools import setup, find_packages

## call setup function

setup(
    name="t2vesselview",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "t2vesselviewcode": [
            "assets/templates/adult/*.nii.gz",
            "assets/templates/pediatric/*.nii.gz",
        ]
    },
    install_requires=[
        "numpy>=1.19.2",
        "nibabel>=3.2.1",
        "SimpleITK>=2.1.1",
        "pandas>=1.3.0",
        "nipype>=1.8.6",
        "ants>=0.0.1",
    ],
    python_requires=">=3.8",
    author="Bonnie Alexander",
    author_email="11053443+BonnieAlexander@users.noreply.github.com",
    description="A package for visualising cortical surface vessels on T2 brain MRI",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/NACIS-RCH/t2_vessel_view",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    # Add system requirements
    setup_requires=["setuptools>=42", "wheel"],
    # Add FSL as a system requirement in the package metadata
    project_urls={
        "Documentation": "https://github.com/NACIS-RCH/t2_vessel_view#readme",
        "Source": "https://github.com/NACIS-RCH/t2_vessel_view",
        "Tracker": "https://github.com/NACIS-RCH/t2_vessel_view/issues",
    },
)
