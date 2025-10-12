# Agent Instructions

- Use English as the sole language for all project files, commit messages, documentation, and pull request content.
- Maintain consistency with the existing coding style when modifying Django or Tailwind components.
- Always include unittest along with any changes and make sure tests pass before committing code.
- Target environment runs Python 3.12
- Use Python type hints where possible
- Production deployment is to Railway via Docker container. Deployment needs to be controllable via Env vars in an idempotent way.
- Always include the migrations from `makemigrations` in the repo when making changes to a model