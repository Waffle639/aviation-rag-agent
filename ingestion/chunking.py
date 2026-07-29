import os
import json


def chunk_text(text, chunk_size=1000, overlap=200):
    """
    Splits the input text into chunks of specified size with a specified overlap.

    Args:
        text (str): The input text to be chunked.
        chunk_size (int): The maximum size of each chunk.
        overlap (int): The number of overlapping characters between consecutive chunks.

    Returns:
        list: A list of text chunks.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer.")
    if overlap < 0:
        raise ValueError("overlap must be a non-negative integer.")
    if overlap >= chunk_size:
        raise ValueError("overlap must be less than chunk_size.")

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end]
        chunks.append(chunk)
        # Move the start index forward by chunk_size - overlap
        start += (chunk_size - overlap)

    return chunks


def save_chunks_to_files(chunks, plane, font):
    output_dir = f"data/processed/chunks/{plane}/{font}"
    os.makedirs(output_dir, exist_ok=True)

    for i, chunk_text in enumerate(chunks):
        chunk_id = f"{plane.lower()}_{font.lower()}_{i:03d}"
        chunk_data = {
            "texto": chunk_text,
            "metadata": {
                "aeronave": plane,
                "fuente": font,
                "chunk_id": chunk_id,
            }
        }

        chunk_filename = f"chunk_{i + 1}.json"
        chunk_path = os.path.join(output_dir, chunk_filename)
        with open(chunk_path, 'w', encoding='utf-8') as f:json.dump(chunk_data, f, ensure_ascii=False, indent=2)
            
            
# Example usage
if __name__ == "__main__":
    # Chunking the wikipedia extracts
    wiki_route = "data/raw/wiki"
    pdf_route = "data/raw/pdf_to_txt"
    
    wiki_docs = os.listdir(wiki_route)
    pdf_docs = os.listdir(pdf_route)
    
    docs = wiki_docs + pdf_docs
    
    for doc in docs:
        plane = doc.split('.txt')[0]
        doc_font = "wiki" if doc in wiki_docs else "pdf" if doc in pdf_docs else "unknown"
        txt_path = os.path.join(wiki_route if doc_font == "wiki" else pdf_route, doc)
        with open(txt_path, 'r', encoding='utf-8') as file:
            text = file.read()
            chunks = chunk_text(text, chunk_size=1000, overlap=200)
            save_chunks_to_files(chunks, plane, doc_font)
        
    
   
    