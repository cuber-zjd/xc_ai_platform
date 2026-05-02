import os
import time
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
import logging

os.environ['LANGFUSE_PUBLIC_KEY'] = 'pk-lf-9ce120b1-ec19-47a1-b7e2-678ee36ddd62'
os.environ['LANGFUSE_SECRET_KEY'] = 'sk-lf-f274860a-ab3c-4fed-ab38-a18ef355247c'
os.environ['LANGFUSE_HOST'] = 'http://192.168.14.44:9506'

logging.basicConfig(level=logging.DEBUG)

print("Testing langfuse initialization...")
try:
    handler = CallbackHandler()
    print("handler ready:", handler)
    handler.auth_check()
    print("auth check passed")
except Exception as e:
    print("Error:", e)
