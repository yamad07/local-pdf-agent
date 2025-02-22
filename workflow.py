import os
import base64
import json
import glob
from dataclasses import dataclass
from typing import Optional, cast
from client import anthropic_client
from anthropic.types import TextBlock


@dataclass
class AnswerEvaluation:
    """Evaluation result of an answer"""
    score: float
    reasoning: Optional[str] = None
    improvements: Optional[str] = None


@dataclass
class PdfAgentResult:
    """Result of PDF agent processing"""
    answer: str
    evaluation: AnswerEvaluation
    source_pdf: Optional[str] = None


def read_pdf(pdf_path: str) -> tuple[str, str]:
    """Read a PDF file and return its title and base64 encoded content.
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        tuple[str, str]: Title (filename without extension) and base64 encoded content
    """
    title = os.path.splitext(os.path.basename(pdf_path))[0]
    
    with open(pdf_path, "rb") as f:
        base64_content = base64.b64encode(f.read()).decode("utf-8")
    
    return title, base64_content


def ask_question(title: str, content: str, question: str) -> str:
    """Ask a question about the PDF content using Claude.
    
    Args:
        title (str): Title of the PDF
        content (str): Base64 encoded PDF content
        question (str): Question to ask
        
    Returns:
        str: Answer text with citations
    """
    response = anthropic_client.client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": content 
                        },
                        "title": title,
                        "citations": {"enabled": True}
                    },
                    {
                        "type": "text",
                        "text": question 
                    },
                ]
            }
        ]
    )
    
    # Combine all text parts into a single answer
    answer_text = ""
    for block in response.content:
        if isinstance(block, TextBlock):
            answer_text += block.text
            # Add citation information if available
            if hasattr(block, "citations") and block.citations:
                citations_text = []
                for citation in block.citations:
                    citations_text.append(
                        f"[Citation: {citation.cited_text} ({citation.document_title}({citation.document_index}))]"
                    )
                if citations_text:
                    answer_text += f" {' '.join(citations_text)}"
    
    return answer_text


def evaluate_answer(question: str, answer: str) -> dict[str, str | float]:
    """Evaluate the quality of the answer using Claude.
    
    Args:
        question (str): Original question
        answer (str): Answer to evaluate
        
    Returns:
        dict[str, str | float]: Evaluation result containing:
            - score (float): Quality score between 0 and 1
            - reasoning (str): Explanation of the score
            - improvements (str): Suggested improvements
    """
    response = anthropic_client.client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": f"""Evaluate the quality of this answer to the given question.
Return your evaluation in JSON format with the following fields:
- score: float between 0 and 1 indicating quality
- reasoning: string explaining the score
- improvements: string suggesting improvements

Question: {question}

Answer: {answer}"""
            }
        ]
    )
    
    try:
        content_block = cast(TextBlock, response.content[0])
        evaluation = json.loads(content_block.text)
        return {
            "score": float(evaluation.get("score", 0)),
            "reasoning": str(evaluation.get("reasoning", "")),
            "improvements": str(evaluation.get("improvements", ""))
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return {
            "score": 0.0,
            "reasoning": "Failed to parse evaluation",
            "improvements": "Try reformulating the answer"
        }


def find_pdfs(folder_path: str) -> list[str]:
    """Find all PDF files in the specified folder.
    
    Args:
        folder_path (str): Path to search for PDFs
        
    Returns:
        list[str]: List of paths to PDF files
    """
    pdf_pattern = os.path.join(folder_path, "**.pdf")
    return glob.glob(pdf_pattern, recursive=True)


def sort_pdfs_by_relevance(pdf_files: list[str], question: str) -> list[str]:
    """Sort PDF files based on their relevance to the question.

    Args:
        pdf_files (list[str]): List of PDF file paths
        question (str): Question to compare against

    Returns:
        list[str]: List of PDF file paths sorted by relevance
    """
    # Create list of filenames
    file_names = [os.path.splitext(os.path.basename(f))[0] for f in pdf_files]
    file_names_str = "\n".join(f"- {name}" for name in file_names)

    response = anthropic_client.client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": f"""Sort these filenames by their relevance to the question.
Return the result in JSON format with scores.

Question: {question}

Filenames:
{file_names_str}

Use this format:
{{
    "rankings": [
        {{"file": "filename", "score": 0.9, "reason": "Why highly relevant"}},
        {{"file": "filename", "score": 0.5, "reason": "Why somewhat relevant"}},
        ...
    ]
}}"""
            }
        ]
    )

    try:
        content_block = cast(TextBlock, response.content[0])
        rankings = json.loads(content_block.text)["rankings"]
        # Create dictionary of filename to score
        scores = {item["file"]: float(item["score"]) for item in rankings}
        
        # Sort original file paths based on scores
        return sorted(
            pdf_files,
            key=lambda x: scores.get(os.path.splitext(os.path.basename(x))[0], 0.0),
            reverse=True
        )
    except (json.JSONDecodeError, KeyError, IndexError):
        # Return original list if error occurs
        return pdf_files


def pdf_agent(folder_path: str, question: str, evaluation_threshold: float = 0.8) -> PdfAgentResult:
    """Process PDFs to find the best answer to a question.
    
    Args:
        folder_path (str): Path to folder containing PDFs
        question (str): Question to answer
        
    Returns:
        PdfAgentResult: Contains answer, evaluation, and source PDF path
    """
    pdf_files = find_pdfs(folder_path)
    
    if not pdf_files:
        return PdfAgentResult(
            answer="No PDF files found in the specified folder.",
            evaluation=AnswerEvaluation(score=0.0),
            source_pdf=None
        )
    
    # Sort PDF files by relevance to the question
    sorted_pdf_files = sort_pdfs_by_relevance(pdf_files, question)
    
    best_result = PdfAgentResult(
        answer="No suitable answer found in the PDF files.",
        evaluation=AnswerEvaluation(score=0.0),
        source_pdf=None
    )
    
    for pdf_path in sorted_pdf_files:
        # Read PDF and generate answer
        title, content = read_pdf(pdf_path)
        answer = ask_question(title, content, question)

        # Evaluate answer and update if better
        evaluation_dict = evaluate_answer(question, answer)
        evaluation = AnswerEvaluation(
            score=float(evaluation_dict["score"]),
            reasoning=str(evaluation_dict.get("reasoning", "")),
            improvements=str(evaluation_dict.get("improvements", ""))
        )
        
        if evaluation.score > best_result.evaluation.score:
            best_result = PdfAgentResult(
                answer=answer,
                evaluation=evaluation,
                source_pdf=pdf_path
            )
            
            # Early exit if answer is good enough
            if evaluation.score >= evaluation_threshold:
                break
    
    return best_result