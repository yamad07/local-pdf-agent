import os
from workflow import pdf_agent
from mcp.server import FastMCP
from typing import Dict, Any

# Create an MCP server
mcp = FastMCP("LocalPDFAgent")

# Add an addition tool
@mcp.tool()
def local_pdf_citation(question: str) -> Dict[str, Any]:
    """Generate answers with citations from local PDF files.

    Args:
        question (str): Question about the PDF content

    Returns:
        dict: Response containing:
            - answer (str): Answer with citations
            - evaluation (dict): Answer evaluation
                - score (float): Quality score (0-1)
                - reasoning (str): Explanation of the score
                - improvements (str): Suggested improvements
            - source_pdf (str): Path to the source PDF file
    """
    result = pdf_agent(os.environ["PDF_FOLDER_PATH"], question)
    return {
        "answer": result.answer,
        "evaluation": {
            "score": result.evaluation.score,
            "reasoning": result.evaluation.reasoning,
            "improvements": result.evaluation.improvements
        },
        "source_pdf": result.source_pdf
    }

if __name__ == "__main__":
    mcp.run()