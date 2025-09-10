from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="public-brokerage",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="A Python library for executing trades on Public brokerage using their API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/public-brokerage",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "coverage>=7.0.0",
        ],
    },
    keywords="trading, api, brokerage, finance, stocks, options",
    project_urls={
        "Bug Reports": "https://github.com/yourusername/public-brokerage/issues",
        "Documentation": "https://github.com/yourusername/public-brokerage#readme",
        "Source": "https://github.com/yourusername/public-brokerage",
    },
)
