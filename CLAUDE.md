The Prism Overlay Project enables users to see the stats of their opponents in Hypixel Bedwars, and track their stats and their progression.

This repository is a monorepo with these components:
- flashlight/ The cloudrun go backend
- prism/ The python client-side overlay application
- rainbow/ The vite+react webapp for stats analysis

Workflows for all components are in .github/workflows/ (flashlight-*, rainbow-*, and prism's codeql.yml, linting.yml, testing.yml).

Plans for work to be done is stored in plans/ (not tracked in git)
