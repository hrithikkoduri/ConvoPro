from langchain.vectorstores import DeepLake
from langchain_openai import OpenAIEmbeddings
from langchain.docstore.document import Document
import os
from dotenv import load_dotenv
from langchain.text_splitter import SpacyTextSplitter
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from pydantic import BaseModel
import json


load_dotenv()

activeloop_token  = os.getenv("ACTIVELOOP_TOKEN")
openai_api_key = os.getenv("OPENAI_API_KEY")

class Details(BaseModel):
    company_name: str
    short_description: str
    services: str
    summary: str

class CompanyDetailsStorage:
    def __init__(self, storage_path="company_details.json"):
        self.storage_path = storage_path

    def save_details(self, details: Details):
        """Save company details to a JSON file"""
        with open(self.storage_path, 'w') as f:
            json.dump(details.model_dump(), f, indent=2)

    def load_details(self) -> Details:
        """Load company details from the JSON file"""
        if not os.path.exists(self.storage_path):
            raise FileNotFoundError("Company details have not been stored yet")
        
        with open(self.storage_path, 'r') as f:
            data = json.load(f)
        return Details(**data)

class VectorStore:
    def __init__(self):
        self.embedding = OpenAIEmbeddings(model="text-embedding-3-large")
        self.activeloop_org = "<YOUR_ACTIVELOOP_ORG>"
        self.activeloop_dataset = "<YOUR_ACTIVELOOP_DATASET>"
        self.dataset_path = f"hub://{self.activeloop_org}/{self.activeloop_dataset}"
        self.docs = [] 
        self.storage = CompanyDetailsStorage()

    def text_to_docs(self, text):
        text_splitter = SpacyTextSplitter(chunk_size=100, chunk_overlap=10)
        splitted_text = text_splitter.split_text(text)
        docs = [Document(page_content=chunk) for chunk in splitted_text]
        return docs

    def main(self):
        with open('example_knowledge_base.txt', 'r') as file:
            text = file.read()  
            print(text) 

            self.get_company_details(text)

            self.docs = self.text_to_docs(text)

            self.load_db()

            self.db.add_documents(self.docs)

            return self.db
    
    def load_db(self):
        self.db = DeepLake(dataset_path = self.dataset_path, embedding=self.embedding)
        print("Loaded Vector Store!")
        return self.db
    
    def get_company_details(self, text):
        template = """  
            You are an AI assitant who is an expert in analyzing text data. You will be provided with a text which contain Q&A pairs 
            which typicall represent a conversation between a user and a a customer service agent. Your task is to extract: 
            - company name
            - short description of 2 sentences what company does
            - services offered
            - summarize the text and extract relevant, information regarding the company name, services offered and any other relevant information. Make the summary as detailed as and descriptive with as much information as possible.

            This information will be used to create a chatbot which can answer questions based on the information provided in the text and help users schedule appointments later.

            The text is as follows:
            {text}

            Please summarize the text and provide the provide the relevant information as mentioned above.
        """
        prompt = PromptTemplate(
            template=template,
            input_variables = ["text"],
            )
        
        formatted_prompt = prompt.invoke({"text": text})

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        structured_llm = llm.with_structured_output(Details)

        company_details = structured_llm.invoke(formatted_prompt)

        self.storage.save_details(company_details)

        print(f"DETAILS: {company_details}\n\n-----\n\n")
        
        print(f"\nConmpany Name: {company_details.company_name}\n")

        print(f"\nShort Description: {company_details.short_description}\n")
        print(f"\nServices: {company_details.services}\n")
        print(f"\nSummary: {company_details.summary}\n")



if __name__ == "__main__":
    vector_store = VectorStore()  
    vector_store.main()
