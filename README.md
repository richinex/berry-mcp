# ai_agent

# Using environment variable
export AI_API_KEY=<api-key>
ai-agent chat "What's the weather in London?"

# Or providing the key directly
ai-agent chat --api-key=your-api-key "What's the weather in London?"

Let's try some examples of combining multiple tools. Here are some interesting combinations we could test:

Weather + Calculator:

ai-agent chat "What's the temperature in London in Fahrenheit? Convert from 20.5 Celsius"

Weather + Search:

ai-agent chat "What's the weather in London and find me information about popular indoor activities there"

Calculator + Search:
ai-agent chat "Calculate 15% of 85 and search for information about tipping customs in Europe"



Would you like to try any of these examples or would you prefer to create a different multi-tool query?