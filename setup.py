from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="ingesta",
    version="0.1.0",
    author="jcolefoto",
    author_email="",
    description="Media ingestion tool with Shotput Pro-style verification and Pluralize-style audio sync",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jcolefoto/ingesta",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Multimedia :: Video",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "ingesta=ingesta.cli:main",
            "ingest=ingesta.cli:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
