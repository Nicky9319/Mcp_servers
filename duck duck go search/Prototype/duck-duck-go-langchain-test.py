from langchain_community.tools import DuckDuckGoSearchRun

search = DuckDuckGoSearchRun()

result = search.invoke("'Render Farm Cost Calculator: How to Estimate Your Project Costs' - Use OP's specific example (10,080 frames, 2 min/frame on CPU) as a case study showing how GPU rendering compares")
print(result)