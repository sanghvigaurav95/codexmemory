import os
from setuptools import setup, find_packages

# Read the contents of your README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name="codexmemory",
    version="1.0.0",
    description="100x AI-Powered Semantic Code Memory with FAISS, MiniLM, and Tree-Sitter AST Parsing",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Gaurav Sanghvi",
    url="https://github.com/sanghvigaurav95/codexmemory",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Intended Audience :: Developers",
    ],
    install_requires=[
        "sentence-transformers",
        "faiss-cpu",
        "tiktoken",
        "numpy",
        "watchdog",
        "mcp[cli]",
        "tree-sitter",
        "tree-sitter-python",
        "tree-sitter-javascript",
        "tree-sitter-typescript",
        "tree-sitter-java",
        "tree-sitter-cpp",
        "tree-sitter-go",
        "tree-sitter-rust",
        "tree-sitter-ruby",

    ],
    entry_points={
        "console_scripts": [
            "codexmemory-install=tools.install_mcp:main",
        ],
    },
)
