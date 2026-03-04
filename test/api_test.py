import base64
from openai import AzureOpenAI

# Azure credentials
client = AzureOpenAI(
    api_key="Dn-SecretKey",
    api_version="2024-08-01-preview",
    azure_endpoint="https://mdart-mmb7bpob-eastus2.cognitiveservices.azure.com/"
)


# Convert image to base64
with open("receipt.png", "rb") as f:
    base64_image = base64.b64encode(f.read()).decode("utf-8")

response = client.chat.completions.create(
    model="gpt-4o-mini-niyaz",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Extract all bill details in JSON format"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                }
            ]
        }
    ],
    max_tokens=1000
)

print(response.choices[0].message.content)