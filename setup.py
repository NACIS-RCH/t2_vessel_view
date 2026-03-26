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
        "numpy>=1.24.0",
        "pandas>=1.5.0",
        "scipy>=1.10.0",
        "nibabel>=5.1.0",
        "pydicom>=2.4.3",
        "SimpleITK>=2.2.1",
        "nipype>=1.8.6",
        "antspyx>=0.5.4",
        "matplotlib>=3.7.0",
        "pyvista>=0.44.0",
        "pyvips>=2.2.0",
        "pillow>=10.0.0",
        "python-pptx>=0.6.21",
        "tqdm>=4.65.0",
        "pyyaml>=6.0",
    ],
    python_requires=">=3.8",
    author="Bonnie Alexander",
    author_email="bonnie.alexander2@rch.org.au",
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
