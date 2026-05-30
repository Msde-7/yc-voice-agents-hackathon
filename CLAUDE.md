# Project Context

Critical project context lives in `PROJECT.md`. It describes all aspects of the project. Setup instructions live in `SETUP.md`. If `SETUP.md` is not yet written, you’ll need to write it for the first time.

# Information Accuracy

- When debugging a problem, make decisions based on evidence, not guesswork.  
- The current year is 2026\. Assume your knowledge of LLM/AI capabilities and models is outdated unless you refer to documentation or online resources.  
- Similarly, don't assume you know current details about any dependency (e.g. versions, capabilities) without referring to documentation.  
  - You should always identify the latest stable version before adding a dependency.  
  - You should research to *discover* suitable dependencies as well.  
- Strongly prefer popular, well-maintained projects as dependencies instead of random packages or repos that you come across \- do the extra research to ensure they fit within that category.  
- If helping the developer install a dependency, refer to its actual setup tutorial or quickstart guide.  
- Important design changes or additions should be reflected in `PROJECT.md`.  
- Use your native Fetch/Research tools/agents rather than other skills unless there is a clear advantage/reason. This should be an explicit instruction to subagents taskws with research as well.

# Development Practices

- Enforce type safety where possible.  
- Big features belong on new branches, not `main`.  
  - If the developer asks you to start work on a new feature but they aren't on a relevant branch, suggest switching to or creating one.  
- Don't push to remote or open PRs without asking the user. Committing locally to the branch at your discretion is acceptable.  
- Consult the user before adding new dependencies to solve a problem.  
- Big problems should be broken down into smaller ones \- in other words, if a function or type is achieving too many things at once, it should be broken up into helpers.  
- Every function and type should have a concise but clear purpose statement.  
- Write tests (and any necessary mock data) for every function, including helpers, to cover happy paths, edge cases, and regressions.  
  - Subagents can be used for this in order to preserve context.  
- Always attempt to verify the success of your work in some form as opposed to assuming it is correct.  
  - This could include taking screenshots or actually simulating a user flow.  
- Check for lint errors before finalizing your work.  
- Encourage the developer to use your Plan Mode (or equivalent) for large features.  
- If preferred tooling is not present on the developer's device, guide them through the installation rather than working without the optimal tools unless they cannot be installed.  
- When you implement or make changes to a feature, update related documentation and/or comments once finished.  
  - When adding new major dependencies, including WordPress plugins or tools, add the corresponding docs to the Docs section in `PROJECT.md`.  
- Ensure `.gitignore` for the most relevant languages/frameworks is in the repo and is updated as needed.  
- Use the following tools to interact with the corresponding services as you build the project (not necessarily in your code). Ask the developer before provisioning resources that cost money:  
  - Twilio CLI for interacting with Twilio: https://www.twilio.com/docs/twilio-cli  
  - Cekura MCP (https://docs.cekura.ai/mcp/overview) and/or CLI (https://docs.cekura.ai/cli-sdk/cli)  
    - Cekura [skills](https://github.com/cekura-ai/cekura-skills) should also be installed  
  - Pipecat CLI for interacting with Pipecat: https://docs.pipecat.ai/api-reference/cli/overview  
  - If the above tools are not set up in the project/system, ask for the developer’s permission and set them up yourself (this should be reflected in `SETUP.md` as well). Skills should be installed at the project level.  
- If using python, remember that it might be aliased `python` and not `python3`  
- NEVER use "prompt-and-pray" tricks like checking for keywords or asking an agent to use some deterministic output format as opposed to using the LLM provider's tool/function call or structured output APIs. They should be well documented and if they're not in `PROJECT.md` the docs are available online.

**Important**: As the project grows, write/update `SETUP.md` such that if you were looking at this project for the first time you could easily set up its components and get it working. It is agent-facing documentation and should be concise. If you are reading it for the first time, note that much of the setup could already be done if the project was worked on in a previous session.  