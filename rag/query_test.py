# retrieval/query_test.py
from rag.generator import generate_answer

if __name__ == "__main__":
    question = input("Question: ")
    answer = generate_answer(question)
    print(answer)