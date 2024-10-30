from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain.vectorstores import DeepLake
import os
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts import MessagesPlaceholder
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import (
    create_history_aware_retriever,
    create_retrieval_chain,
)
from langchain_core.messages import HumanMessage, AIMessage
from datetime import date
from storage import CompanyDetailsStorage, Details



load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")



class Output:
    def __init__(self, db):
        
        self.db = db
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.retriever = self.db.as_retriever()
        self.retriever.search_kwargs['fetch_k'] = 100
        self.retriever.search_kwargs['k'] = 10
        self.chat_history = []

        self.prompt_search_query = ChatPromptTemplate.from_messages([
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "{input}"),
            ("user", "Given the above conversation, generate a search query to look up to get information relevant to the conversation"),
        ])
        
        self.retriever_chain = create_history_aware_retriever(self.llm, self.retriever, self.prompt_search_query)


        self.system_message = '''   
            You are a Donna and  AI receptionist for the company: {company} which provides services {services}/
            Here is the short description of the company: {short_description}.
            Your job is to help users understand and interact with our company’s services and products. Your primary role is to answer questions based on the information extracted from our knowledge base, which includes policies, product details, and customer support procedures.
            \n
            On the contrary, if user wants to schedule a meeting, just ask for user's name, availability date, availability time and any any reason/requirement/description for the appointment. Make sure to ask one question at a time. Once they have provided all details kindly reply that their meeting has been scheduled. If they miss out providing any of the details, follow up with the missing details.
            \n
            For the context of the conversation, you can use this {context}.

            If no question is asked, offer a brief overview of our company’s services and suggest possible questions related to our offerings, support, and general inquiries. If you don't know the answer, ask the user to be more specific. If the question is not related to our services, request a relevant question.

            When asked for specific policies or procedures, provide exact information as it appears in our knowledge base; do not generate or summarize details on your own.

            Your goals are to:

            - Answer questions related to our company’s services and products.
            - Provide relevant details, policies, and procedures as needed.
            - Offer guidance on navigating our services and accessing support.
            - Assist with common inquiries about service offerings, account management, and procedures.
            - Keep the answers concise and informative, avoiding unnecessary details or jargon.
            
            Behavior Guidelines:

            - Be helpful, friendly, and concise.
            - Provide accurate information and explanations when requested.
            - Focus solely on the information available in the knowledge base context.
            - If a question is anything not relevant simply ask questions relevant to the company.
            - Use simple language to ensure clarity, avoiding technical jargon unless necessary.
            - Keep the answers as concise as posible.
            \n
            Again, if user wants to schedule a meeting, just ask for user's name, availability date and time and any reason/requirement/description for the appointment. And kindly reply that their meeting has been scheduled. If they have not provided any of the details, follow up and ask for the relevant missing details with regards to appointment.
        
        '''

        self.prompt_get_answer = ChatPromptTemplate.from_messages([
            ("system", self.system_message),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "User : {input}, company: {company}, services: {services}, short_description: {short_description}"),
            ("user", "Given the above conversation, generate an answer to the user's question."),
            
        ])

        self. document_chain= create_stuff_documents_chain(self.llm, self.prompt_get_answer)
        self.retrieval_chain = create_retrieval_chain(self.retriever_chain, self.document_chain)
        
    #def chat(self, question, chat_history):
    def chat(self, question):
        
        print("Entered chat function")
        print("-------------------")
        print("Question inside function:",question)
        print("-------------------")
        print("Chat History inside function:",self.chat_history)


        company_details = self.get_company_info()

        company_name = company_details.company_name
        short_description = company_details.short_description
        services = company_details.services


        response = self.retrieval_chain.invoke(
            {"input": question, "chat_history": self.chat_history, "company": company_name, "services": services, "short_description": short_description}
        )
        print("-------------------")
        print( "Context:",response['context'])
        print("-------------------")

        
        self.chat_history.append(HumanMessage(question))
        self.chat_history.append(AIMessage(response['answer']))

        self.chat_history = self.chat_history[-6:]

        json_response = {
            "response": response['answer'],
            "chat_history": self.chat_history
        }
        return json_response["response"]
    
    def update_chat_history(self, self_message):
        self.chat_history.append(AIMessage(self_message))
        self.chat_history = self.chat_history[-6:]
        print("-------------------")
        print("Chat History after broadcast message:",self.chat_history)

    def get_company_info(self):
        storage = CompanyDetailsStorage()
        try:
            details = storage.load_details()
            return details
        except FileNotFoundError:
            logger.error("Company details haven't been processed yet. Run the main script first.")
            return None
        except Exception as e:
            logger.error(f"Error loading company details: {e}")
            return None
    

if __name__ == "__main__":
    
    company_details = output.get_company_info()
    if company_details:

        print(f"Company Name: {company_details.company_name}")
        print(f"Services: {company_details.services}")