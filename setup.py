import setuptools
import os

with open("README.md", "r") as f:
    long_description = f.read()

setuptools.setup(
    name="cs-workers",
    version=os.environ.get("TAG", "0.0.0"),
    author="Hank Doupe",
    author_email="hank@compute.studio",
    description=(
        "Build, publish, and run Compute Studio workers."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/compute-tooling/compute-studio-workers",
    packages=setuptools.find_packages(),
    install_requires=["celery", "redis", "gitpython"],
    include_package_data=True,
    entry_points={
        "console_scripts": ["cs-workers=cs_publish:main"]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Operating System :: OS Independent",
    ],
)
