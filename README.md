# compute-studio-publish

Create and update models in Compute Studio:

```bash
cs-publish -n [:user]/[:owner]
```

Some models' test suites take too long to run on GitHub actions. After checking that the tests pass locally or verifying this with the model maintainer, run

```bash
cs-publish -n PSLmodels/OG-USA --skip-test
```

These commands will create or update a config file with the current timestamp and push the branch to GitHub. If a PR for a given model is already open, then this tool will push the changes to the existing PR. If the tests pass, click merge pull request to deploy the model.

**TODO:** Write technical docs.
