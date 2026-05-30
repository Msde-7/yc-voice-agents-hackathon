# Gunk

We are building Gunk, a platform that helps businesses understand where AI voice agents can be implemented in their support call processes to improve efficiency.

Problem:

- Businesses receive dozens to thousands of support and customer service calls per day that take valuable time away from humans who have other work to do.  
- Many companies could (or already want to) benefit from AI automation, but don’t know how to implement it effectively

Solution:

- Gunk is a voice agent platform that can call businesses’ phone numbers, perform typical user flows, and eventually produce a report of what parts of the flow could have been handled by an AI agent and which parts are best handled by an agent.  
  - Example: A customer calling to ask some basic questions like “what are your hours?” or “are you open right now?” is a flow that could be handled by an agent. However, a customer asking about a refund might be best handled by a human, perhaps after an agent asks some preliminary questions.

Tech stack:

- Gradium for voice (it’s similar to ElevenLabs)  
- Pipecat for orchestration  
- NVIDIA Nemotron for LLM inference, hosted on AWS  
- Twilio for phone calling capabilities  
- Cekura for analysis  
- Business logic and other components will be implemented in Python

Documentation:

- Gradium docs: https://docs.gradium.ai/  
  - Pipecat integration: https://docs.gradium.ai/integrations/agent-frameworks/pipecat  
  - We have credits available  
- Pipecat   
  - Pipecat docs: https://docs.pipecat.ai/  
  - Pipecat open source repo: https://github.com/pipecat-ai/pipecat  
  - NVIDIA LLM support: https://docs.pipecat.ai/api-reference/server/services/llm/nvidia  
  - Python SDK: https://docs.pipecat.ai/api-reference/pipecat-cloud/sdk-reference/overview  
  - We have credits available for Pipecat Cloud  
- NVIDIA model API URLs \+ Credentials are available at https://github.com/pipecat-ai/yc-voice-agents-hackathon  
  - That repo also contains sample projects/agents which use Pipecat and NVIDIA  
- Twilio  
  - Twilio Programmable Voice docs: https://www.twilio.com/docs/voice  
  - Twilio CLI docs: https://www.twilio.com/docs/twilio-cli  
- Cekura  
  - Docs: https://docs.cekura.ai/documentation/  
  - Pipecat integration: https://docs.pipecat.ai/pipecat/fundamentals/evaluations/cekura  
  - Python SDK: https://docs.cekura.ai/cli-sdk/sdk  
  - We have credits available