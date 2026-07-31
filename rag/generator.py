
import logging
import os

from openai import APIError, OpenAI, RateLimitError

from rag.retrival import search_context

logger = logging.getLogger(__name__)


MODEL_NAME = "gpt-4o-mini"

openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
)


def generate_answer(question):
    """
    Generates an answer to a given question based on the provided context.
    """
    chunks_context = search_context(question, top_k=5)
    
    context = "\n\n".join([
            f"[{c['plane']} - {c['font']}]: {c['texto']}"
        for c in chunks_context
    ])
    
    instructions = f"""You are an aviation technical assistant. Answer the question using ONLY the information in the context below, do not use any outside knowledge, even if you know the answer.
    Rules:
    - If the context does not contain the answer, say exactly: "I don't have that information in my sources."
    - Always cite which aircraft and source the information comes from (e.g. "According to the CessnaA330").
    - If the context has conflicting information from different sources, mention the discrepancy instead of picking one silently.
    - Be precise with numbers (speeds, weights, dimensions) — do not round or approximate values given in the context.
    """
    input = f"""
        Context:
        {context}

        Question: {question}

        Answer:
    """
    
    
    logger.info("--- GENERATION REQUEST ---")
    logger.info("Model: %s", MODEL_NAME)
    logger.info("Instructions: %s", instructions)
    logger.info("Input: %s", input)

    try:
        response = openai_client.responses.create(
            model=MODEL_NAME,
            instructions=instructions,
            input=input,
        )
    except (RateLimitError, APIError) as e:
        logger.warning(
            "Response request failed (%s).",
            e,
        )
        raise

    logger.info("--- GENERATION RESPONSE ---")
    logger.info("Output text: %s", response.output_text)
    logger.info("--- END GENERATION ---")

    return response.output_text