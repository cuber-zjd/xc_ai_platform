import os
import sys
import logging

# Ensure env vars are set
os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-lf-9ce120b1-ec19-47a1-b7e2-678ee36ddd62"
os.environ["LANGFUSE_SECRET_KEY"] = "sk-lf-f274860a-ab3c-4fed-ab38-a18ef355247c"
os.environ["LANGFUSE_HOST"] = "http://192.168.14.44:9506"
os.environ["LANGFUSE_DEBUG"] = "True"

logging.basicConfig(level=logging.DEBUG)

print("Testing langfuse trace generation...")
from langfuse.decorators import observe, langfuse_context

@observe()
def my_test_function():
    print("Executing test function")
    return "test_success"

if __name__ == "__main__":
    my_test_function()
    print("Flushing...")
    langfuse_context.flush()
    print("Done flushing.")
