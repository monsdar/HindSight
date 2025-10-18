# Agent Instructions

- Use English as the sole language for all project files, commit messages, documentation, and pull request content.
- Maintain consistency with the existing coding style when modifying Django or Tailwind components.
- Always include unittest along with any changes and make sure tests pass before committing code.
- Target environment runs Python 3.12
- Use Python type hints where possible
- Production deployment is to Railway via Docker container. Deployment needs to be controllable via Env vars in an idempotent way.
- Always include the migrations from `makemigrations` in the repo when making changes to a model
- When using the BallDontLie NBA API make sure to optimize calls, as the free tier only allows for up to 5 calls per minute. Therefore for endpoints that use pushing use a large enough per_page parameter, the maximum allowed value is 100.
- In case you get a task that isn't applicable with your available data report that and cancel the task instead of trying to guess what a solution could look like. E.g. when asked to resolve merge conflicts in a PR do not continue when you have no access to the latest main branch to see the conflicts.
- Ensure to keep concerns separated: The prediction app is a generic foundation to provide all kinds of prediction events. This is extended but the NBA package, that adds NBA specific predictions. In the future this should be extended by other packages like German Bundesliga, Olympics, political elections etc. Therefore it's important to not mix any specific prediction implementations into the foundation.