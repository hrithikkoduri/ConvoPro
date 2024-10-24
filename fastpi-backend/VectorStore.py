from langchain.vectorstores import DeepLake
from langchain_openai import OpenAIEmbeddings
from langchain.docstore.document import Document
import os
from dotenv import load_dotenv
from langchain.text_splitter import SpacyTextSplitter

load_dotenv()

activeloop_token  = os.getenv("ACTIVELOOP_TOKEN")
openai_api_key = os.getenv("OPENAI_API_KEY")


class VectorStore:
    def __init__(self):
        self.embedding = OpenAIEmbeddings(model="text-embedding-3-large")
        self.activeloop_org = "hrithikkoduri18"
        self.activeloop_dataset = "whizbot_test2"
        self.dataset_path = f"hub://{self.activeloop_org}/{self.activeloop_dataset}"
        self.db = DeepLake(dataset_path=self.dataset_path, embedding=self.embedding)
        self.docs = [] 

    def text_to_docs(self, text):
        text_splitter = SpacyTextSplitter(chunk_size=200, chunk_overlap=10)
        splitted_text = text_splitter.split_text(text)
        docs = [Document(page_content=chunk) for chunk in splitted_text]
        return docs

    def main(self):
        with open('example_knowledge_base.txt', 'r') as file:
            text = file.read()  
            print(text) 

            self.docs = self.text_to_docs(text)

            self.db.add_documents(self.docs)

            return self.db
    
    def load_db(self):
        self.db = DeepLake(dataset_path = self.dataset_path, embedding=self.embedding)
        print("Loaded Vector Store!")
        return self.db


if __name__ == "__main__":
    vector_store = VectorStore()  
    vector_store.main() 
